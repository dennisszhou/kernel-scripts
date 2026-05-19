# kforge and kbake CLI Design

Date: 2026-05-19

Status: approved

## Problem

The repository is being refactored from several shell entrypoints into a real
Python project. The command surface has two different operating contexts:

- shared artifact commands create and maintain reusable local assets, such as
  the Docker builder image, rootfs image, initramfs, and local tool config
- kernel-checkout commands operate on a Linux source tree, such as applying a
  config fragment, running kernel `make`, opening a builder shell, and booting
  the resulting image

Putting both contexts under one deep command tree makes the hot path verbose.
Putting everything at top level makes names like `build` ambiguous. The design
needs a command model that carries the context in the command name without
keeping old aliases or spreading behavior across one large file.

## Goal

Create one Python package that installs two CLIs:

- `kforge` owns shared artifacts and local setup
- `kbake` owns kernel-checkout actions

The final shape should be short for daily kernel work, explicit when run from
outside a kernel checkout, and structured enough that future commands have an
obvious owner.

## Constraints

- The tool must work on macOS Apple Silicon and Linux where practical.
- The main local boot target is arm64 QEMU.
- Docker remains the builder and rootfs construction boundary.
- The default config path is
  `~/.config/kernel-workflow/config.toml`.
- The Python package requires Python 3.11 or newer so TOML parsing can use the
  stdlib `tomllib` module without adding a runtime dependency.
- The user has a root disk at `~/workplace-imgs/kernel/rootfs.img`.
- `make` should only provide `make install`, because the memorable action is
  installing the editable CLI package.
- Avoid runtime dependencies unless there is a concrete reason. The current
  problem is process orchestration and TOML parsing is covered by Python 3.11,
  so Python stdlib plus `uv` project metadata is sufficient.

## Non-goals

- Do not keep `kbuild`, `kboot`, `kbuild-shell`, or shell-script aliases as
  compatibility wrappers in the first cleaned-up version.
- Do not read or migrate the legacy shell-style config at
  `~/.config/kernel-scripts/config`; this refactor switches to the TOML config
  at `~/.config/kernel-workflow/config.toml`.
- Do not make Makefile targets a second workflow surface.
- Do not implement a general kernel test harness, benchmark runner, or VM
  lifecycle manager.
- Do not solve cross-architecture kernel builds beyond preserving explicit
  `ARCH=...` and pass-through make arguments.
- Do not expose rootfs image sizing until there is real pressure.

## End State

- `kforge` and `kbake` are the only operational CLIs.
- `bin/kforge` and `bin/kbake` are tiny source-tree launchers for a clone.
- `pyproject.toml` exposes both installed console scripts.
- `make install` runs `uv tool install --force -e .`.
- Rootfs artifacts are generated outside the repository by default, under
  `images.dir`.
- Generated rootfs artifacts and Python build/cache directories are ignored.
- The README documents current behavior only; old command names are absent.

## Proposed Approach

Use two CLIs from one package.

`kforge` manages reusable artifacts and setup:

```text
kforge config init
kforge config show
kforge builder build
kforge rootfs build
kforge initramfs build
```

`kbake` operates on a Linux kernel checkout:

```text
kbake apply-config
kbake make [make arguments...]
kbake build [make arguments...]
kbake shell
kbake boot
```

Daily inside-checkout workflow:

```sh
cd ~/workplace/percpu
kbake apply-config
kbake build
kbake boot
```

Explicit outside-checkout workflow:

```sh
kbake -C ~/workplace/percpu apply-config
kbake -C ~/workplace/percpu build
kbake -C ~/workplace/percpu boot
```

The `-C` flag follows the Git model: resolve the kernel checkout as if `kbake`
had been started in that directory. Checkout resolution order is exactly:

1. `-C PATH`
2. the current directory, only when it looks like a Linux checkout
3. configured `kernel.src`

If none of those resolves to a Linux checkout, the command fails with a message
that names the missing context. `kernel.src` is an explicit configured default,
not a hardcoded fallback to `~/workplace/percpu`.

`kbake make ...` is the exact escape hatch for arbitrary kernel `make`
invocations. For `kbake make` and `kbake build`, all `kbake` options must
appear before the subcommand; arguments after the subcommand are passed to
kernel `make`.

`kbake build` is the common kernel build command. It accepts remaining
arguments as kernel `make` arguments:

```sh
kbake build
kbake build V=1
kbake build modules
kbake build ARCH=arm64 -j8 Image
```

When no user-provided `ARCH=...` or `-j...` argument is present, `kbake build`
adds the configured default architecture and default job count. User-provided
make arguments win by presence; `kbake` does not expose separate `--arch` or
`--jobs` flags for build.

`kbake build` does not apply or regenerate `.config` automatically. If
`.config` is missing, it fails with a message pointing to `kbake apply-config`
or `kbake make defconfig`.

`kbake apply-config` copies the configured fragment to `.config` and runs
`olddefconfig`. The name is intentionally specific; it is not general tool
configuration.

`kbake boot` accepts mutually exclusive root selectors:

```sh
kbake boot --rootfs
kbake boot --rootfs /path/to/rootfs.img
kbake boot --initramfs
kbake boot --initramfs /path/to/rootfs.cpio.gz
```

When a selector is provided with a path, that path is used. When a selector is
provided without a path, `kbake boot` uses the configured path for that selected
kind and fails if the selected config value is empty. When no selector is
provided, configured `images.rootfs` takes precedence over configured
`images.initramfs`; if only one is configured, that one is used.

## Data Model / API Shape

`Config`
:   Source-of-truth settings loaded from one shared TOML config file and CLI
    overrides. `--config PATH` selects the config file for one invocation; the
    default is `~/.config/kernel-workflow/config.toml`. Setting precedence is
    command-line option > selected config file > default. Individual settings
    do not have environment-variable overrides in the first cleaned-up version.
    `kforge` owns config mutation; `kbake` reads config.

`ProjectPaths`
:   Resolved repository paths for `kernel-builder.Dockerfile`, tracked kconfig
    fragments, packaged rootfs scripts, and source-tree launchers.

`KernelCheckout`
:   A resolved Linux source tree plus architecture, `.config` path, and derived
    image path. `kbake` commands must resolve exactly one checkout before
    planning Docker or QEMU work.

`BuilderImage`
:   Docker image tag and Dockerfile path. It is shared by `kforge builder` and
    `kbake` Docker-backed commands.

`RootArtifact`
:   A disk image or initramfs artifact with kind, path, and default output
    filename. `kforge` creates these artifacts; `kbake boot` consumes them.

`DockerRunSpec`
:   A testable command plan for Docker invocations. Command modules build a
    spec; a runner executes it.

`QemuPlan`
:   A testable command plan for accelerator choice, CPU model, kernel image,
    root artifact, memory, CPU count, and kernel append string.

`Runner`
:   Thin subprocess boundary. Tests can assert command plans without launching
    Docker or QEMU.

## Source Topology / Project Structure

The package should be split by command ownership and execution boundary:

```text
bin/kforge
bin/kbake
pyproject.toml
uv.lock
Makefile
README.md
docs/designs/kbake-cli.md
src/kbake/__init__.py
src/kbake/forge_cli.py
src/kbake/kernel_cli.py
src/kbake/config.py
src/kbake/paths.py
src/kbake/runner.py
src/kbake/docker.py
src/kbake/qemu.py
src/kbake/forge/__init__.py
src/kbake/forge/builder.py
src/kbake/forge/images.py
src/kbake/kernel/__init__.py
src/kbake/kernel/checkout.py
src/kbake/kernel/kbuild.py
src/kbake/kernel/shell.py
src/kbake/kernel/boot.py
src/kbake/assets/kernel-builder.Dockerfile
src/kbake/assets/kconfig.arm64.minimal
src/kbake/assets/rootfs-image.sh
src/kbake/assets/rootfs-initramfs.sh
tests/
```

Ownership:

- `forge_cli.py` owns parser construction and dispatch for `kforge` only.
- `kernel_cli.py` owns parser construction and dispatch for `kbake` only.
- `config.py` owns config parsing, precedence, and resolved defaults.
- `paths.py` owns repository path discovery and common path helpers.
- `runner.py` owns subprocess execution and dry-run plumbing.
- `docker.py` owns reusable Docker command planning.
- `qemu.py` owns QEMU accelerator and argument planning.
- `forge/builder.py` owns Docker builder-image creation.
- `forge/images.py` owns rootfs and initramfs artifact creation.
- `kernel/checkout.py` owns Linux checkout detection and `-C` resolution.
- `kernel/kbuild.py` owns kernel make planning, build, and apply-config.
- `kernel/shell.py` owns interactive builder shells for a checkout.
- `kernel/boot.py` owns boot orchestration from checkout image to QEMU plan.
- `assets/` owns package data: the builder Dockerfile, tracked kconfig
  fragments, and shell payloads that run inside the builder container.

Packaged assets should be real files, not large Python string constants. That
keeps Dockerfile, kconfig, and shell syntax reviewable and lets tests or syntax
checks target the assets directly.

`ProjectPaths` resolves assets through Python package resources, not by
assuming the current working directory is this repository. During editable
development, the resources point at files in this checkout. During an installed
tool run, the resources are read from the installed package. When Docker needs
a filesystem path, the asset resolver materializes the resource into a
temporary build context and passes that path to Docker. This keeps
`kforge builder build` working from any directory.

The Docker build context contains only the packaged builder assets needed for
the image build. The rootfs shell payloads are mounted into containers as
read-only files when `kforge rootfs build` or `kforge initramfs build` runs.

## Config File Format

`kforge` and `kbake` share one TOML config file. Sharing is intentional because
`kforge` creates artifacts that `kbake` consumes, and both commands need the
same builder image, image directory, kernel defaults, and boot defaults.

The default config path is:

```text
~/.config/kernel-workflow/config.toml
```

Both CLIs accept `--config PATH` as a global option before the subcommand. This
selects a different TOML file for that invocation only:

```sh
kforge --config ./kernel-workflow.toml config show
kbake --config ./kernel-workflow.toml -C ~/workplace/percpu boot --dry-run
```

There is no config-path environment variable in the first cleaned-up version.
Legacy `KBAKE_CONFIG`, `KERNEL_SCRIPTS_CONFIG`, and shell-style config files are
not read by this cleaned-up CLI.

The file format is TOML. It is parsed as data, never sourced as shell. Path
values may use `~`; expansion happens only for settings documented as paths.

Example:

```toml
version = 1

[images]
dir = "~/workplace-imgs/kernel"
rootfs = "~/workplace-imgs/kernel/rootfs.img"
initramfs = "~/workplace-imgs/kernel/rootfs.cpio.gz"

[builder]
image = "kernel-builder"

[kernel]
src = "~/workplace/percpu"
arch = "arm64"
kconfig = "builtin:arm64-minimal"

[boot]
kernel_image = ""
memory = "2G"
cpus = 4
append = ""

[qemu]
binary = "qemu-system-aarch64"
cpu = ""
```

Recognized tables and keys:

- `images.dir`: default directory for generated root artifacts
- `images.rootfs`: default disk image path for `kbake boot`
- `images.initramfs`: default initramfs path for `kbake boot`
- `builder.image`: Docker image tag used by `kforge` and `kbake`
- `kernel.src`: optional default checkout for `kbake`; used after `-C` and
  current-directory checkout detection
- `kernel.arch`: default kernel architecture for `apply-config` and `build`
- `kernel.kconfig`: config fragment path or builtin fragment name
- `boot.kernel_image`: explicit kernel image path for `kbake boot`
- `boot.memory`, `boot.cpus`, `boot.append`: boot defaults
- `qemu.binary`, `qemu.cpu`: QEMU defaults. `qemu.binary` may be an
  executable name or an explicit path; the default is `qemu-system-aarch64`,
  resolved by normal `PATH` lookup at execution time.

Config path precedence is:

1. `--config PATH`
2. default `~/.config/kernel-workflow/config.toml`

Setting precedence is:

1. command-line option
2. selected config file
3. built-in default

`kforge config show` prints the resolved values and whether each value came
from a command-line option, config file, or default.

## Invariants

- There are exactly two operational CLIs: `kforge` and `kbake`.
- `kforge` never mutates a kernel checkout.
- `kbake` never builds shared rootfs or builder-image artifacts.
- Makefile does not duplicate operational commands.
- Kernel commands resolve exactly one checkout through `-C`, current working
  directory detection, or configured `kernel.src` before planning Docker or
  QEMU work.
- Commands that create rootfs artifacts write to `images.dir` unless an explicit
  output path or directory is provided.
- Boot chooses exactly one root source: disk image or initramfs. Command-line
  selectors are mutually exclusive. Without a selector, configured
  `images.rootfs` wins over configured `images.initramfs` when both are set.
- Boot fails loudly when the kernel image or root artifact is missing.
- Docker and QEMU commands are planned separately from execution so dry-run and
  tests can prove behavior without external side effects.
- Config parsing never silently invents multiple sources of truth for the same
  setting; setting precedence is explicit, and the config-file path is selected
  only by `--config PATH` or the default path.

## Operational Contracts

- `kforge builder build` builds the local Docker builder image from the tracked
  Dockerfile.
- `kforge rootfs build` may require privileged Docker because it formats and
  mounts an ext4 image inside the container.
- `kforge initramfs build` creates a disposable initramfs artifact without
  privileged Docker.
- `kbake make`, `kbake build`, and `kbake apply-config` run Docker as the host
  UID/GID so kernel build artifacts are not root-owned.
- `kbake shell` opens an interactive Docker shell mounted on the resolved
  checkout.
- `kbake boot` prints the selected checkout, accelerator, kernel image, root
  artifact, memory, and CPU count before executing QEMU.
- `--dry-run` should be available for commands whose primary behavior is an
  external process plan, at minimum `kbake boot` and preferably Docker-backed
  commands too.

## Alternatives Considered

`One CLI with top-level verbs`
:   Short, but names like `build` and `config` become ambiguous because shared
    artifacts and kernel checkouts both have build/config operations.

`One CLI with a kernel group`
:   Explicit, but `kbake kernel build` and `kbake kernel boot` are too verbose
    for the daily path.

`One CLI with short groups such as src/img`
:   Compact, but the group names are jargon and still require remembering the
    mode model.

`Two CLIs from one package`
:   Chosen. The command name carries the operating context: `kforge` prepares
    shared artifacts, and `kbake` works on a kernel checkout.

`Rust`
:   Good for a polished single binary later, but it adds build and distribution
    work before the command model is settled. The current tool mostly parses
    config and launches Docker/QEMU, so Python is the simpler project shape.

`Shell scripts plus Makefile`
:   Small at first, but the workflow already needs config precedence, context
    detection, dry-run planning, and tests. Shell would keep pushing complex
    state into quoting-heavy scripts.

## Migration / Rollout

1. Keep the existing working tree as draft implementation material only.
2. Reshape the Python package to match the source topology above.
3. Add `kforge` and `kbake` console scripts in `pyproject.toml`.
4. Move rootfs shell payloads into package assets.
5. Move shared artifact behavior under `kforge`.
6. Move checkout behavior under `kbake`.
7. Keep only `make install` in the Makefile.
8. Remove old shell entrypoints and the tracked generated `rootfs.cpio.gz`.
9. Update README examples after the CLI shape is implemented.

## Validation Strategy

- Unit tests for config parsing and precedence.
- Unit tests for checkout detection and `-C` resolution.
- Unit tests for Docker command planning.
- Unit tests for QEMU accelerator/root selection and append-string planning.
- CLI tests for both parser surfaces and dry-run output.
- Shell syntax checks for packaged rootfs assets.
- Manual smoke checks, when needed:
  - `kforge builder build`
  - `kforge rootfs build`
  - `cd ~/workplace/percpu && kbake boot --dry-run`
  - `kbake -C ~/workplace/percpu boot --dry-run`

Full Docker image builds and QEMU boots are integration checks, not mandatory
for every edit, but they should run before considering the refactor complete.

## Risks

- The current draft implementation already has some code in place. It should
  be treated as provisional and reshaped against this design, not preserved just
  because it exists.
- Editable install assumes the checkout remains available. That is acceptable
  for this local workflow, but a non-editable distribution would need package
  data handling for Dockerfile, kconfigs, and rootfs assets.
- Privileged Docker for rootfs construction remains a sharp edge and should be
  visible in command help and docs.

## Open Questions

None.

## Design Exit Criteria

- The two-CLI split is accepted or revised.
- The source topology owners are accepted or revised.
- The current draft implementation is either reshaped to this design or
  intentionally replaced.

## Recommended Next Step

After this design is approved, turn it into a commit-by-commit execution plan.

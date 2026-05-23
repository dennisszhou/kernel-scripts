# kernel-scripts

Local helpers for a Linux kernel build, rootfs, and QEMU boot loop.

The `kernel-scripts` Python package installs two operational CLIs:

- `kforge` manages shared local artifacts and config.
- `kbake` operates on a Linux kernel checkout.

Run them directly from this checkout, through `uv`, or after editable install:

```sh
bin/kforge --help
bin/kbake --help
uv run kforge --help
uv run kbake --help
make install
```

After `make install`, `uv tool install --force -e .` owns the installed
commands. Because the install is editable, changes in this checkout are
reflected without reinstalling.

## Quick Start

Create machine-local defaults:

```sh
kforge config init --image-dir ~/workplace-imgs/kernel
kforge config show
```

Build the container image and root disk:

```sh
kforge builder build
kforge rootfs build
```

Build and boot a kernel checkout:

```sh
cd ~/workplace/percpu
kbake apply-config
kbake build
kbake boot
```

From outside a checkout, pass `-C`:

```sh
kbake -C ~/workplace/percpu build
kbake -C ~/workplace/percpu boot --dry-run
```

## Config

The default config path is:

```text
~/.config/kernel-workflow/config.toml
```

Use `--config PATH` before the subcommand to select a different config file for
one invocation. There is no config-path environment variable.

The config format is TOML:

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

[boot]
memory = "2G"
cpus = 4
append = ""

[qemu]
cpu = ""
```

Path values may use `~`. Shell variables inside config values are not expanded.
When `kernel.kconfig` or `qemu.binary` is omitted, each default is derived from
`kernel.arch`.
Show resolved values and their sources with:

```sh
kforge config show
```

## kforge

Build the Docker image used for kernel and rootfs work:

```sh
kforge builder build
kforge builder build --builder-image kernel-builder
```

Build root artifacts:

```sh
kforge rootfs build
kforge rootfs build --path /tmp/rootfs.img
kforge initramfs build
kforge initramfs build --path /tmp/rootfs.cpio.gz
```

`kforge rootfs build` uses privileged Docker because it formats and mounts an
ext4 image in the container. Use `--dry-run` on Docker-backed commands to print
the planned command without running Docker.

Builder and rootfs Docker commands use `--platform` derived from
`kernel.arch`, so generated userland matches the configured target architecture
when Docker supports that platform.

## kbake

`kbake` resolves a Linux checkout in this order:

1. `-C PATH`
2. the current directory, when it looks like a Linux checkout
3. configured `kernel.src`

Apply the configured kconfig fragment:

```sh
kbake apply-config
kbake -C ~/workplace/percpu apply-config
```

Run arbitrary kernel `make` arguments inside the builder:

```sh
kbake make ARCH=arm64 olddefconfig
kbake make ARCH=arm64 -j8 Image
```

Run the common build command:

```sh
kbake build
kbake build V=1
kbake build modules
```

`kbake build` adds the target's Linux `ARCH` value and host job count unless
the make arguments already include `ARCH=...` or a jobs argument. It does not
generate a missing `.config`; run `kbake apply-config` or
`kbake make defconfig` first.

Kernel `make` runs inside Docker as the host UID/GID. `kbake` mounts a temporary
passwd/group view for that Docker run so tools inside the container resolve the
invoking user name instead of seeing only an unknown numeric UID.

`kernel.arch` is the target architecture. `kforge config init` writes the
normalized local host architecture, currently `arm64` or `x86_64`. The target
drives derived defaults:

- `arm64`: Linux `ARCH=arm64`, kernel image `arch/arm64/boot/Image`,
  QEMU binary `qemu-system-aarch64`, QEMU machine `virt`
- `x86_64`: Linux `ARCH=x86`, kernel image `arch/x86/boot/bzImage`,
  QEMU binary `qemu-system-x86_64`, QEMU machine `q35`

Set `kernel.arch` in config to build and boot a different target. For example,
setting `kernel.arch = "x86_64"` on Apple Silicon plans x86_64 Docker
platforms and boots with `qemu-system-x86_64` under TCG emulation.
After changing `kernel.arch`, rerun `kforge builder build` so the local builder
image exists for the new Docker platform.

Open a builder shell:

```sh
kbake shell
kbake shell --root
```

Boot QEMU:

```sh
kbake boot
kbake boot --rootfs /tmp/rootfs.img
kbake boot --initramfs /tmp/rootfs.cpio.gz
kbake boot --append "debug initcall_debug"
kbake boot --dry-run
```

When no root selector is provided, configured `images.rootfs` wins over
configured `images.initramfs`. `--rootfs` or `--initramfs` without a path uses
the configured value for that selected root kind.

`qemu.binary` defaults from `kernel.arch` and is resolved by normal `PATH`
lookup. Set `qemu.binary` in config or pass `--qemu PATH` for nonstandard QEMU
installs.

When the target architecture matches the host, `kbake boot` uses HVF on macOS
or KVM on Linux with `/dev/kvm`. When the target differs from the host, it falls
back to TCG emulation.

## Tests

Run the test suite with:

```sh
python3 -m unittest discover -s tests -v
```

# kernel-scripts

Local helpers for an arm64 Linux kernel build, rootfs, and QEMU boot loop.

The Python package installs two operational CLIs:

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
kconfig = "builtin:arm64-minimal"

[boot]
memory = "2G"
cpus = 4
append = ""

[qemu]
binary = "qemu-system-aarch64"
cpu = ""
```

Path values may use `~`. Shell variables inside config values are not expanded.
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

`kbake build` adds the configured `ARCH` and host job count unless the make
arguments already include `ARCH=...` or a jobs argument. It does not generate a
missing `.config`; run `kbake apply-config` or `kbake make defconfig` first.

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

`qemu.binary` defaults to `qemu-system-aarch64`, resolved by normal `PATH`
lookup. Set `qemu.binary` in config or pass `--qemu PATH` for nonstandard QEMU
installs.

On Apple Silicon, `kbake boot` uses HVF. On Linux arm64 with `/dev/kvm`, it uses
KVM. Otherwise it falls back to TCG.

## Tests

Run the test suite with:

```sh
python3 -m unittest discover -s tests -v
```

from __future__ import annotations

import platform
from pathlib import Path

from kbake.config import Config
from kbake.kernel.checkout import KernelCheckout
from kbake.qemu import QemuPlan, RootArtifact, append_string, detect_accel
from kbake.qemu import require_existing


class BootError(ValueError):
    """Raised when boot inputs cannot produce one QEMU plan."""


def select_kernel(config: Config, checkout: KernelCheckout) -> Path:
    if config.boot_kernel_image.value is not None:
        return config.boot_kernel_image.value
    return checkout.image_path


def select_root(
    config: Config,
    *,
    rootfs: str | bool | None,
    initramfs: str | bool | None,
) -> RootArtifact:
    if rootfs is not None and initramfs is not None:
        raise BootError("--rootfs and --initramfs are mutually exclusive")
    if rootfs is not None:
        return RootArtifact("rootfs", _selected_path(rootfs, config.images_rootfs.value))
    if initramfs is not None:
        return RootArtifact(
            "initramfs",
            _selected_path(initramfs, config.images_initramfs.value),
        )
    if config.images_rootfs.source != "default":
        return RootArtifact("rootfs", config.images_rootfs.value)
    if config.images_initramfs.source != "default":
        return RootArtifact("initramfs", config.images_initramfs.value)
    return RootArtifact("rootfs", config.images_rootfs.value)


def boot_plan(
    config: Config,
    checkout: KernelCheckout,
    *,
    rootfs: str | bool | None,
    initramfs: str | bool | None,
    system: str | None = None,
    machine: str | None = None,
    has_kvm: bool | None = None,
) -> QemuPlan:
    root = select_root(config, rootfs=rootfs, initramfs=initramfs)
    kernel = select_kernel(config, checkout)
    require_existing((("kernel image", kernel), (root.kind, root.path)))
    accel = detect_accel(
        system=system or platform.system(),
        machine=machine or platform.machine(),
        has_kvm=Path("/dev/kvm").exists() if has_kvm is None else has_kvm,
        target_arch=config.kernel_arch.value,
        qemu_cpu=config.qemu_cpu.value,
    )
    return QemuPlan(
        binary=config.qemu_binary.value,
        target_arch=config.kernel_arch.value,
        kernel=kernel,
        root=root,
        accel=accel,
        memory=config.boot_memory.value,
        cpus=config.boot_cpus.value,
        append=append_string(
            root,
            config.boot_append.value,
            target_arch=config.kernel_arch.value,
        ),
    )


def _selected_path(value: str | bool, configured: Path) -> Path:
    if value is True:
        return configured
    return Path(value).expanduser()

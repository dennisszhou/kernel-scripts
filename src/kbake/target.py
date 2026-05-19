from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path


class TargetError(ValueError):
    """Raised when a target architecture is not supported."""


@dataclass(frozen=True)
class TargetSpec:
    arch: str
    make_arch: str
    kernel_arch_dir: str
    kernel_image_name: str
    docker_platform: str
    qemu_binary: str
    qemu_machine: str
    tcg_cpu: str
    serial_console: str
    earlycon: str
    builtin_kconfig: str
    builtin_kconfig_asset: str

    def kernel_image_path(self, checkout: Path) -> Path:
        return (
            checkout
            / "arch"
            / self.kernel_arch_dir
            / "boot"
            / self.kernel_image_name
        )


_TARGETS = {
    "arm64": TargetSpec(
        arch="arm64",
        make_arch="arm64",
        kernel_arch_dir="arm64",
        kernel_image_name="Image",
        docker_platform="linux/arm64",
        qemu_binary="qemu-system-aarch64",
        qemu_machine="virt",
        tcg_cpu="cortex-a72",
        serial_console="ttyAMA0",
        earlycon="pl011,0x09000000",
        builtin_kconfig="builtin:arm64-minimal",
        builtin_kconfig_asset="kconfig.arm64.minimal",
    ),
    "x86_64": TargetSpec(
        arch="x86_64",
        make_arch="x86",
        kernel_arch_dir="x86",
        kernel_image_name="bzImage",
        docker_platform="linux/amd64",
        qemu_binary="qemu-system-x86_64",
        qemu_machine="q35",
        tcg_cpu="qemu64",
        serial_console="ttyS0",
        earlycon="",
        builtin_kconfig="builtin:x86_64-minimal",
        builtin_kconfig_asset="kconfig.x86_64.minimal",
    ),
}

_ALIASES = {
    "aarch64": "arm64",
    "arm64": "arm64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86": "x86_64",
    "x86_64": "x86_64",
}


def normalize_target_arch(value: str) -> str:
    key = value.strip().lower()
    if not key:
        raise TargetError("target architecture must not be empty")
    if key in _ALIASES:
        return _ALIASES[key]
    raise TargetError(
        f"unsupported target architecture: {value}; expected arm64 or x86_64"
    )


def host_target_arch(*, machine: str | None = None) -> str:
    return normalize_target_arch(machine or platform.machine())


def target_spec(arch: str) -> TargetSpec:
    return _TARGETS[normalize_target_arch(arch)]


def default_builtin_kconfig(arch: str) -> str:
    return target_spec(arch).builtin_kconfig


def default_qemu_binary(arch: str) -> str:
    return target_spec(arch).qemu_binary


def builtin_kconfig_asset(name: str) -> str | None:
    for target in _TARGETS.values():
        if target.builtin_kconfig == name:
            return target.builtin_kconfig_asset
    return None

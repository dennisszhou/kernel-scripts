from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from kbake.runner import Arg, format_command
from kbake.target import normalize_target_arch, target_spec


@dataclass(frozen=True)
class AccelPlan:
    args: tuple[str, ...]
    cpu: str
    label: str


@dataclass(frozen=True)
class RootArtifact:
    kind: str
    path: Path


@dataclass(frozen=True)
class QemuPlan:
    binary: str
    target_arch: str
    kernel: Path
    root: RootArtifact
    accel: AccelPlan
    memory: str
    cpus: int
    append: str

    def argv(self) -> tuple[Arg, ...]:
        target = target_spec(self.target_arch)
        args: list[Arg] = [
            self.binary,
            "-M",
            target.qemu_machine,
            "-cpu",
            self.accel.cpu,
            *self.accel.args,
            "-kernel",
            self.kernel,
            "-m",
            self.memory,
            "-smp",
            str(self.cpus),
            "-nographic",
            "-no-reboot",
            "-net",
            "nic,model=virtio",
            "-net",
            "user",
        ]
        if self.root.kind == "rootfs":
            args.extend(["-drive", f"file={self.root.path},format=raw,if=virtio"])
        else:
            args.extend(["-initrd", self.root.path])
        args.extend(["-append", self.append])
        return tuple(args)

    def shell_command(self) -> str:
        return format_command(self.argv())


def detect_accel(
    *,
    system: str,
    machine: str,
    has_kvm: bool,
    target_arch: str,
    qemu_cpu: str,
) -> AccelPlan:
    target = target_spec(target_arch)
    host_arch = _normalize_host_arch(machine)
    can_accelerate = host_arch == target.arch

    if system == "Darwin":
        if can_accelerate:
            return AccelPlan(("-accel", "hvf"), qemu_cpu or "host", "hvf")
        return AccelPlan(("-accel", "tcg"), qemu_cpu or target.tcg_cpu, "tcg")

    if system == "Linux":
        if has_kvm and can_accelerate:
            return AccelPlan(("-accel", "kvm"), qemu_cpu or "host", "kvm")
        return AccelPlan(("-accel", "tcg"), qemu_cpu or target.tcg_cpu, "tcg")

    return AccelPlan(("-accel", "tcg"), qemu_cpu or target.tcg_cpu, "tcg")


def append_string(root: RootArtifact, extra: str, *, target_arch: str) -> str:
    target = target_spec(target_arch)
    parts = [f"console={target.serial_console}"]
    if target.earlycon:
        parts.append(f"earlycon={target.earlycon}")
    if root.kind == "rootfs":
        parts.extend(["root=/dev/vda", "rw"])
    parts.append("panic=1")
    if extra:
        parts.append(extra)
    return " ".join(parts)


def require_existing(paths: Sequence[tuple[str, Path]]) -> None:
    for label, path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")


def _normalize_host_arch(machine: str) -> str:
    try:
        return normalize_target_arch(machine)
    except ValueError:
        return machine

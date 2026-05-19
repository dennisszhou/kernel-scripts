from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from kbake.runner import Arg, format_command


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
    kernel: Path
    root: RootArtifact
    accel: AccelPlan
    memory: str
    cpus: int
    append: str

    def argv(self) -> tuple[Arg, ...]:
        args: list[Arg] = [
            self.binary,
            "-M",
            "virt",
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
    qemu_cpu: str,
) -> AccelPlan:
    if system == "Darwin":
        if machine == "arm64":
            return AccelPlan(("-accel", "hvf"), qemu_cpu or "host", "hvf")
        return AccelPlan(("-accel", "tcg"), qemu_cpu or "cortex-a72", "tcg")

    if system == "Linux":
        if has_kvm and machine in {"aarch64", "arm64"}:
            return AccelPlan(("-accel", "kvm"), qemu_cpu or "host", "kvm")
        return AccelPlan(("-accel", "tcg"), qemu_cpu or "cortex-a72", "tcg")

    return AccelPlan(("-accel", "tcg"), qemu_cpu or "cortex-a72", "tcg")


def append_string(root: RootArtifact, extra: str) -> str:
    parts = ["console=ttyAMA0", "earlycon=pl011,0x09000000"]
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

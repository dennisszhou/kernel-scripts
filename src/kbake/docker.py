from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from kbake.runner import Arg, format_command


@dataclass(frozen=True)
class DockerVolume:
    host: Path
    container: str
    read_only: bool = False

    def argument(self) -> str:
        suffix = ":ro" if self.read_only else ""
        return f"{self.host}:{self.container}{suffix}"


@dataclass(frozen=True)
class DockerBuildSpec:
    image: str
    dockerfile: Path
    context: Path

    def argv(self) -> tuple[Arg, ...]:
        return (
            "docker",
            "build",
            "-t",
            self.image,
            "-f",
            self.dockerfile,
            self.context,
        )

    def shell_command(self) -> str:
        return format_command(self.argv())


@dataclass(frozen=True)
class DockerRunSpec:
    image: str
    command: tuple[str, ...]
    volumes: tuple[DockerVolume, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    privileged: bool = False
    user: str | None = None
    tty: bool = False

    def argv(self) -> tuple[Arg, ...]:
        args: list[Arg] = ["docker", "run", "--rm"]
        if self.tty:
            args.extend(["-it"])
        if self.privileged:
            args.append("--privileged")
        if self.user:
            args.extend(["--user", self.user])
        for volume in self.volumes:
            args.extend(["-v", volume.argument()])
        for name, value in sorted(self.env.items()):
            args.extend(["-e", f"{name}={value}"])
        args.append(self.image)
        args.extend(self.command)
        return tuple(args)

    def shell_command(self) -> str:
        return format_command(self.argv())


def host_user() -> str:
    return f"{os.getuid()}:{os.getgid()}"


def wants_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()

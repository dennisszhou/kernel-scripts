from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


Arg = str | Path


class RunError(RuntimeError):
    """Raised when a command cannot be executed."""


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int


def argv_strings(argv: Sequence[Arg]) -> tuple[str, ...]:
    return tuple(str(arg) for arg in argv)


def format_command(argv: Sequence[Arg]) -> str:
    return shlex.join(argv_strings(argv))


class Runner:
    def run(self, argv: Sequence[Arg], *, cwd: Path | None = None) -> CommandResult:
        command = argv_strings(argv)
        try:
            completed = subprocess.run(command, cwd=cwd, check=False)
        except FileNotFoundError as exc:
            raise RunError(f"missing executable: {command[0]}") from exc
        return CommandResult(command, completed.returncode)

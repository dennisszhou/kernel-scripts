from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.kernel_cli import run_cli
from kbake.runner import CommandResult, RunError


def make_checkout(root: Path, *, with_config: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("", encoding="utf-8")
    (root / "Kconfig").write_text("", encoding="utf-8")
    (root / "arch" / "arm64" / "boot").mkdir(parents=True)
    if with_config:
        (root / ".config").write_text("CONFIG_TEST=y\n", encoding="utf-8")
    return root


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, argv: object, *, cwd: Path | None = None) -> CommandResult:
        del cwd
        command = tuple(str(arg) for arg in argv)  # type: ignore[union-attr]
        self.commands.append(command)
        return CommandResult(command, 0)


class MissingRunner:
    def run(self, argv: object, *, cwd: Path | None = None) -> CommandResult:
        del argv, cwd
        raise RunError("missing executable: docker")


class KernelCliTests(unittest.TestCase):
    def test_apply_config_copies_builtin_fragment_and_runs_olddefconfig(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")
            runner = RecordingRunner()

            code = run_cli(["-C", str(checkout), "apply-config"], runner=runner)

            config_text = (checkout / ".config").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("CONFIG_ARM64=y", config_text)
        self.assertEqual(runner.commands[0][-2:], ("ARCH=arm64", "olddefconfig"))

    def test_make_passes_remainder_to_kernel_make(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")
            runner = RecordingRunner()

            code = run_cli(
                ["-C", str(checkout), "make", "ARCH=arm64", "olddefconfig"],
                runner=runner,
            )

        self.assertEqual(code, 0)
        self.assertEqual(runner.commands[0][-3:], ("make", "ARCH=arm64", "olddefconfig"))

    def test_runner_error_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = run_cli(
                    ["-C", str(checkout), "make"],
                    runner=MissingRunner(),
                )

        self.assertEqual(code, 2)
        self.assertIn("missing executable: docker", stderr.getvalue())

    def test_build_dry_run_requires_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = run_cli(
                    ["-C", str(checkout), "build", "--dry-run"],
                    runner=RecordingRunner(),
                )

        self.assertEqual(code, 2)
        self.assertIn("kbake apply-config", stderr.getvalue())

    def test_build_dry_run_adds_default_arch_and_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux", with_config=True)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = run_cli(
                    ["-C", str(checkout), "build", "--dry-run", "Image"],
                    runner=RecordingRunner(),
                )

        self.assertEqual(code, 0)
        self.assertIn("ARCH=arm64", stdout.getvalue())
        self.assertIn("Image", stdout.getvalue())

    def test_shell_dry_run_can_plan_root_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = run_cli(
                    ["-C", str(checkout), "shell", "--root", "--dry-run"],
                    runner=RecordingRunner(),
                )

        self.assertEqual(code, 0)
        self.assertNotIn("--user", stdout.getvalue())
        self.assertIn("/bin/bash", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

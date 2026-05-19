from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.config import load_config
from kbake.kernel.boot import boot_plan, select_root
from kbake.kernel.checkout import KernelCheckout
from kbake.kernel_cli import run_cli
from kbake.qemu import RootArtifact
from kbake.runner import CommandResult


def make_checkout(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("", encoding="utf-8")
    (root / "Kconfig").write_text("", encoding="utf-8")
    (root / "arch" / "arm64" / "boot").mkdir(parents=True)
    (root / "arch" / "arm64" / "boot" / "Image").write_text("", encoding="utf-8")
    return root


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, argv: object, *, cwd: Path | None = None) -> CommandResult:
        del cwd
        command = tuple(str(arg) for arg in argv)  # type: ignore[union-attr]
        self.commands.append(command)
        return CommandResult(command, 0)


class BootCliTests(unittest.TestCase):
    def test_select_root_prefers_configured_rootfs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                f"""
[images]
rootfs = "{Path(tmp) / "rootfs.img"}"
initramfs = "{Path(tmp) / "rootfs.cpio.gz"}"
""",
                encoding="utf-8",
            )
            config = load_config(path=config_path)

            root = select_root(config, rootfs=None, initramfs=None)

        self.assertEqual(root, RootArtifact("rootfs", Path(tmp) / "rootfs.img"))

    def test_boot_plan_uses_qemu_binary_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")
            rootfs = Path(tmp) / "rootfs.img"
            rootfs.write_text("", encoding="utf-8")
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                f"""
[images]
rootfs = "{rootfs}"

[qemu]
binary = "custom-qemu"
""",
                encoding="utf-8",
            )
            config = load_config(path=config_path)

            plan = boot_plan(
                config,
                KernelCheckout(checkout, "arm64"),
                rootfs=None,
                initramfs=None,
                system="Darwin",
                machine="arm64",
                has_kvm=False,
            )

        self.assertEqual(plan.binary, "custom-qemu")
        self.assertEqual(plan.argv()[0], "custom-qemu")

    def test_boot_dry_run_prints_qemu_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")
            rootfs = Path(tmp) / "rootfs.img"
            rootfs.write_text("", encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = run_cli(
                    [
                        "-C",
                        str(checkout),
                        "boot",
                        "--rootfs",
                        str(rootfs),
                        "--qemu",
                        "qemu-system-aarch64",
                        "--dry-run",
                    ],
                    runner=RecordingRunner(),
                )

        self.assertEqual(code, 0)
        self.assertIn("qemu-system-aarch64", stdout.getvalue())
        self.assertIn(str(rootfs), stdout.getvalue())

    def test_boot_fails_when_selected_root_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")
            missing = Path(tmp) / "missing.img"
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = run_cli(
                    ["-C", str(checkout), "boot", "--rootfs", str(missing)],
                    runner=RecordingRunner(),
                )

        self.assertEqual(code, 2)
        self.assertIn("rootfs not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

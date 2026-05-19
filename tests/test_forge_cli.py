from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.forge_cli import main


class ForgeCliTests(unittest.TestCase):
    def test_config_init_writes_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "--config",
                        str(config_path),
                        "config",
                        "init",
                        "--image-dir",
                        "~/imgs",
                    ],
                )

            contents = config_path.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("created", stdout.getvalue())
        self.assertIn("[images]", contents)
        self.assertIn('dir = "', contents)
        self.assertIn("[qemu]", contents)
        self.assertIn('binary = "qemu-system-aarch64"', contents)

    def test_config_init_force_replaces_invalid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text("[bad\n", encoding="utf-8")

            code = main(
                [
                    "--config",
                    str(config_path),
                    "config",
                    "init",
                    "--force",
                ],
            )

            contents = config_path.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn("version = 1", contents)

    def test_config_show_prints_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[builder]
image = "test-builder"
""",
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(["--config", str(config_path), "config", "show"])

        self.assertEqual(code, 0)
        self.assertIn("builder.image", stdout.getvalue())
        self.assertIn("test-builder (config)", stdout.getvalue())

    def test_builder_build_dry_run_prints_docker_command(self) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            code = main(
                [
                    "builder",
                    "build",
                    "--builder-image",
                    "test-builder",
                    "--dry-run",
                ],
            )

        self.assertEqual(code, 0)
        self.assertIn("docker build", stdout.getvalue())
        self.assertIn("test-builder", stdout.getvalue())

    def test_rootfs_build_dry_run_uses_selected_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "custom.img"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(["rootfs", "build", "--path", str(output), "--dry-run"])

        self.assertEqual(code, 0)
        self.assertIn("--privileged", stdout.getvalue())
        self.assertIn(f"{output.parent}:/out", stdout.getvalue())
        self.assertIn("ROOTFS_IMAGE_NAME=custom.img", stdout.getvalue())

    def test_initramfs_build_dry_run_uses_host_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "initramfs",
                        "build",
                        "--directory",
                        tmp,
                        "--dry-run",
                    ],
                )

        self.assertEqual(code, 0)
        self.assertIn("--user", stdout.getvalue())
        self.assertIn("ROOTFS_INITRAMFS_NAME=rootfs.cpio.gz", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

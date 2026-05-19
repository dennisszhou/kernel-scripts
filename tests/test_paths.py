from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.paths import (
    ARM64_KCONFIG,
    BUILDER_DOCKERFILE,
    ProjectPaths,
    ROOTFS_IMAGE_SCRIPT,
    ROOTFS_INITRAMFS_SCRIPT,
    X86_64_KCONFIG,
)


class ProjectPathsTests(unittest.TestCase):
    def test_reads_packaged_assets(self) -> None:
        paths = ProjectPaths()

        self.assertIn("FROM fedora", paths.read_text(BUILDER_DOCKERFILE))
        self.assertIn("CONFIG_ARM64=y", paths.read_text(ARM64_KCONFIG))
        self.assertIn("CONFIG_X86_64=y", paths.read_text(X86_64_KCONFIG))
        self.assertIn("ROOTFS_IMAGE_NAME", paths.read_text(ROOTFS_IMAGE_SCRIPT))
        self.assertIn(
            "ROOTFS_INITRAMFS_NAME",
            paths.read_text(ROOTFS_INITRAMFS_SCRIPT),
        )

    def test_materializes_asset_to_filesystem(self) -> None:
        paths = ProjectPaths()
        with tempfile.TemporaryDirectory() as tmp:
            output = paths.materialize_asset(BUILDER_DOCKERFILE, Path(tmp))

            self.assertEqual(output, Path(tmp) / BUILDER_DOCKERFILE)
            self.assertIn("FROM fedora", output.read_text(encoding="utf-8"))

    def test_rejects_unknown_asset(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown kbake asset"):
            ProjectPaths().resource("../kernel-builder.Dockerfile")


if __name__ == "__main__":
    unittest.main()

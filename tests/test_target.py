from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.target import host_target_arch, normalize_target_arch, target_spec


class TargetTests(unittest.TestCase):
    def test_normalizes_common_host_arch_aliases(self) -> None:
        self.assertEqual(normalize_target_arch("aarch64"), "arm64")
        self.assertEqual(normalize_target_arch("amd64"), "x86_64")

    def test_host_target_arch_normalizes_machine_name(self) -> None:
        self.assertEqual(host_target_arch(machine="aarch64"), "arm64")

    def test_x86_target_uses_kernel_arch_directory(self) -> None:
        spec = target_spec("x86_64")

        self.assertEqual(spec.make_arch, "x86")
        self.assertEqual(spec.docker_platform, "linux/amd64")
        self.assertEqual(
            spec.kernel_image_path(Path("/linux")),
            Path("/linux/arch/x86/boot/bzImage"),
        )


if __name__ == "__main__":
    unittest.main()

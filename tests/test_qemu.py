from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.qemu import AccelPlan, RootArtifact, QemuPlan, append_string, detect_accel


class QemuTests(unittest.TestCase):
    def test_detects_hvf_on_apple_silicon(self) -> None:
        plan = detect_accel(
            system="Darwin",
            machine="arm64",
            has_kvm=False,
            qemu_cpu="",
        )

        self.assertEqual(plan.args, ("-accel", "hvf"))
        self.assertEqual(plan.cpu, "host")

    def test_append_string_sets_disk_root(self) -> None:
        append = append_string(RootArtifact("rootfs", Path("/rootfs.img")), "debug")

        self.assertIn("root=/dev/vda", append)
        self.assertTrue(append.endswith("debug"))

    def test_qemu_plan_uses_binary_name_for_path_lookup(self) -> None:
        root = RootArtifact("rootfs", Path("/rootfs.img"))
        plan = QemuPlan(
            binary="qemu-system-aarch64",
            kernel=Path("/linux/Image"),
            root=root,
            accel=AccelPlan(("-accel", "tcg"), "cortex-a72", "tcg"),
            memory="2G",
            cpus=4,
            append=append_string(root, ""),
        )

        argv = plan.argv()

        self.assertEqual(argv[0], "qemu-system-aarch64")
        self.assertIn("-drive", argv)
        self.assertIn("file=/rootfs.img,format=raw,if=virtio", argv)


if __name__ == "__main__":
    unittest.main()

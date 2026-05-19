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
            target_arch="arm64",
            qemu_cpu="",
        )

        self.assertEqual(plan.args, ("-accel", "hvf"))
        self.assertEqual(plan.cpu, "host")

    def test_emulated_x86_uses_tcg_on_apple_silicon(self) -> None:
        plan = detect_accel(
            system="Darwin",
            machine="arm64",
            has_kvm=False,
            target_arch="x86_64",
            qemu_cpu="",
        )

        self.assertEqual(plan.args, ("-accel", "tcg"))
        self.assertEqual(plan.cpu, "qemu64")

    def test_native_x86_linux_uses_kvm_when_available(self) -> None:
        plan = detect_accel(
            system="Linux",
            machine="x86_64",
            has_kvm=True,
            target_arch="x86_64",
            qemu_cpu="",
        )

        self.assertEqual(plan.args, ("-accel", "kvm"))
        self.assertEqual(plan.cpu, "host")

    def test_append_string_sets_disk_root(self) -> None:
        append = append_string(
            RootArtifact("rootfs", Path("/rootfs.img")),
            "debug",
            target_arch="arm64",
        )

        self.assertIn("root=/dev/vda", append)
        self.assertIn("console=ttyAMA0", append)
        self.assertTrue(append.endswith("debug"))

    def test_x86_append_string_uses_serial_console(self) -> None:
        append = append_string(
            RootArtifact("initramfs", Path("/rootfs.cpio.gz")),
            "",
            target_arch="x86_64",
        )

        self.assertIn("console=ttyS0", append)
        self.assertNotIn("earlycon=", append)

    def test_qemu_plan_uses_binary_name_for_path_lookup(self) -> None:
        root = RootArtifact("rootfs", Path("/rootfs.img"))
        plan = QemuPlan(
            binary="qemu-system-aarch64",
            target_arch="arm64",
            kernel=Path("/linux/Image"),
            root=root,
            accel=AccelPlan(("-accel", "tcg"), "cortex-a72", "tcg"),
            memory="2G",
            cpus=4,
            append=append_string(root, "", target_arch="arm64"),
        )

        argv = plan.argv()

        self.assertEqual(argv[0], "qemu-system-aarch64")
        self.assertEqual(argv[2], "virt")
        self.assertIn("-drive", argv)
        self.assertIn("file=/rootfs.img,format=raw,if=virtio", argv)

    def test_x86_qemu_plan_uses_q35_machine(self) -> None:
        root = RootArtifact("rootfs", Path("/rootfs.img"))
        plan = QemuPlan(
            binary="qemu-system-x86_64",
            target_arch="x86_64",
            kernel=Path("/linux/bzImage"),
            root=root,
            accel=AccelPlan(("-accel", "tcg"), "qemu64", "tcg"),
            memory="2G",
            cpus=4,
            append=append_string(root, "", target_arch="x86_64"),
        )

        argv = plan.argv()

        self.assertEqual(argv[0], "qemu-system-x86_64")
        self.assertEqual(argv[2], "q35")


if __name__ == "__main__":
    unittest.main()

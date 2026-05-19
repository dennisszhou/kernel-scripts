from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.config import ConfigError, load_config
from kbake.target import (
    TargetError,
    default_builtin_kconfig,
    default_qemu_binary,
    host_target_arch,
)


class ConfigTests(unittest.TestCase):
    def test_missing_config_uses_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "missing.toml"

            config = load_config(path=config_path)

        self.assertEqual(config.config_path, config_path)
        self.assertEqual(config.builder_image.value, "kernel-builder")
        self.assertEqual(config.builder_image.source, "default")
        self.assertEqual(config.kernel_src.value, None)
        self.assertEqual(config.kernel_arch.value, host_target_arch())
        self.assertEqual(
            config.kernel_kconfig.value,
            default_builtin_kconfig(config.kernel_arch.value),
        )
        self.assertEqual(
            config.qemu_binary.value,
            default_qemu_binary(config.kernel_arch.value),
        )

    def test_config_values_and_origins_are_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
version = 1

[images]
dir = "~/imgs"
rootfs = "~/imgs/custom.img"

[builder]
image = "custom-builder"

[kernel]
src = "~/linux"
arch = "arm64"

[boot]
cpus = 8

[qemu]
binary = "/opt/qemu/bin/qemu-system-aarch64"
""",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"HOME": "/home/tester"}):
                config = load_config(path=config_path)

        self.assertEqual(config.images_dir.value, Path("/home/tester/imgs"))
        self.assertEqual(config.images_rootfs.value, Path("/home/tester/imgs/custom.img"))
        self.assertEqual(config.builder_image.source, "config")
        self.assertEqual(config.kernel_src.value, Path("/home/tester/linux"))
        self.assertEqual(config.boot_cpus.value, 8)
        self.assertEqual(
            config.qemu_binary.value,
            "/opt/qemu/bin/qemu-system-aarch64",
        )

    def test_target_arch_derives_qemu_and_kconfig_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[kernel]
arch = "x86_64"
""",
                encoding="utf-8",
            )

            config = load_config(path=config_path)

        self.assertEqual(config.kernel_arch.value, "x86_64")
        self.assertEqual(config.kernel_kconfig.value, "builtin:x86_64-minimal")
        self.assertEqual(config.qemu_binary.value, "qemu-system-x86_64")

    def test_explicit_target_arch_does_not_require_supported_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[kernel]
arch = "x86_64"
""",
                encoding="utf-8",
            )

            with mock.patch(
                "kbake.config.host_target_arch",
                side_effect=TargetError("unsupported target architecture: riscv64"),
            ):
                config = load_config(path=config_path)

        self.assertEqual(config.kernel_arch.value, "x86_64")

    def test_missing_target_arch_fails_on_unsupported_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "kbake.config.host_target_arch",
                side_effect=TargetError("unsupported target architecture: riscv64"),
            ):
                with self.assertRaisesRegex(ConfigError, "set kernel.arch"):
                    load_config(path=Path(tmp) / "missing.toml")

    def test_target_arch_aliases_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[kernel]
arch = "aarch64"
""",
                encoding="utf-8",
            )

            config = load_config(path=config_path)

        self.assertEqual(config.kernel_arch.value, "arm64")
        self.assertEqual(config.qemu_binary.value, "qemu-system-aarch64")

    def test_cli_overrides_win_over_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[builder]
image = "config-builder"
""",
                encoding="utf-8",
            )

            config = load_config(
                path=config_path,
                overrides={"builder.image": "cli-builder"},
            )

        self.assertEqual(config.builder_image.value, "cli-builder")
        self.assertEqual(config.builder_image.source, "cli")

    def test_path_values_do_not_expand_environment_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[images]
dir = "$WORK_ROOT/images"
""",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"WORK_ROOT": "/work"}):
                config = load_config(path=config_path)

        self.assertEqual(config.images_dir.value, Path("$WORK_ROOT/images"))

    def test_unknown_config_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[kernel]
unknown = "value"
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "kernel.unknown"):
                load_config(path=config_path)

    def test_invalid_cpu_count_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[boot]
cpus = 0
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "boot.cpus"):
                load_config(path=config_path)

    def test_unknown_target_arch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[kernel]
arch = "mips"
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "unsupported target"):
                load_config(path=config_path)


if __name__ == "__main__":
    unittest.main()

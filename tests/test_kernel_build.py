from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.config import load_config
from kbake.docker import DockerVolume
from kbake.kernel.checkout import KernelCheckout
from kbake.kernel.kbuild import (
    HostIdentity,
    build_make_args,
    ensure_config_exists,
    make_spec,
)


def load_test_config(*, arch: str = "arm64"):
    with tempfile.TemporaryDirectory() as tmp:
        return load_config(
            path=Path(tmp) / "missing.toml",
            overrides={"kernel.arch": arch},
        )


class KernelBuildTests(unittest.TestCase):
    def test_build_make_args_adds_arch_and_jobs_by_default(self) -> None:
        config = load_test_config()

        self.assertEqual(
            build_make_args(config, ["Image"], cpu_count=8),
            ["ARCH=arm64", "-j8", "Image"],
        )

    def test_build_make_args_preserves_user_arch_and_jobs(self) -> None:
        config = load_test_config()

        self.assertEqual(
            build_make_args(config, ["ARCH=arm64", "-j16", "modules"]),
            ["ARCH=arm64", "-j16", "modules"],
        )
        self.assertEqual(
            build_make_args(config, ["--jobs=12", "Image"]),
            ["ARCH=arm64", "--jobs=12", "Image"],
        )

    def test_x86_target_uses_kernel_make_arch(self) -> None:
        config = load_test_config(arch="x86_64")

        self.assertEqual(
            build_make_args(config, ["bzImage"], cpu_count=8),
            ["ARCH=x86", "-j8", "bzImage"],
        )

    def test_make_spec_runs_as_host_user_in_checkout(self) -> None:
        config = load_test_config()
        checkout = KernelCheckout(Path("/linux"), "arm64")

        argv = make_spec(config, checkout, ["ARCH=arm64", "olddefconfig"]).argv()

        self.assertIn(f"{os.getuid()}:{os.getgid()}", argv)
        self.assertIn("/linux:/src", argv)
        self.assertEqual(argv[-3:], ("make", "ARCH=arm64", "olddefconfig"))

    def test_make_spec_mounts_identity_files_when_provided(self) -> None:
        config = load_test_config()
        checkout = KernelCheckout(Path("/linux"), "arm64")
        volumes = (
            DockerVolume(Path("/tmp/passwd"), "/etc/passwd", read_only=True),
            DockerVolume(Path("/tmp/group"), "/etc/group", read_only=True),
        )

        argv = make_spec(
            config,
            checkout,
            ["ARCH=arm64", "olddefconfig"],
            identity_volumes=volumes,
        ).argv()

        self.assertIn("/tmp/passwd:/etc/passwd:ro", argv)
        self.assertIn("/tmp/group:/etc/group:ro", argv)

    def test_host_identity_writes_passwd_and_group_entries(self) -> None:
        identity = HostIdentity(user="dennis", uid=501, group="staff", gid=20)

        self.assertIn("dennis:x:501:20", identity.passwd_text())
        self.assertIn("staff:x:20:dennis", identity.group_text())

    def test_ensure_config_exists_fails_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = KernelCheckout(Path(tmp), "arm64")

            with self.assertRaisesRegex(Exception, "kbake apply-config"):
                ensure_config_exists(checkout)


if __name__ == "__main__":
    unittest.main()

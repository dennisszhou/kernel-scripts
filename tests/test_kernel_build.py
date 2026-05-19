from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.config import load_config
from kbake.kernel.checkout import KernelCheckout
from kbake.kernel.kbuild import build_make_args, ensure_config_exists, make_spec


class KernelBuildTests(unittest.TestCase):
    def test_build_make_args_adds_arch_and_jobs_by_default(self) -> None:
        config = load_config()

        self.assertEqual(
            build_make_args(config, ["Image"], cpu_count=8),
            ["ARCH=arm64", "-j8", "Image"],
        )

    def test_build_make_args_preserves_user_arch_and_jobs(self) -> None:
        config = load_config()

        self.assertEqual(
            build_make_args(config, ["ARCH=arm64", "-j16", "modules"]),
            ["ARCH=arm64", "-j16", "modules"],
        )
        self.assertEqual(
            build_make_args(config, ["--jobs=12", "Image"]),
            ["ARCH=arm64", "--jobs=12", "Image"],
        )

    def test_make_spec_runs_as_host_user_in_checkout(self) -> None:
        config = load_config()
        checkout = KernelCheckout(Path("/linux"), "arm64")

        argv = make_spec(config, checkout, ["ARCH=arm64", "olddefconfig"]).argv()

        self.assertIn(f"{os.getuid()}:{os.getgid()}", argv)
        self.assertIn("/linux:/src", argv)
        self.assertEqual(argv[-3:], ("make", "ARCH=arm64", "olddefconfig"))

    def test_ensure_config_exists_fails_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = KernelCheckout(Path(tmp), "arm64")

            with self.assertRaisesRegex(Exception, "kbake apply-config"):
                ensure_config_exists(checkout)


if __name__ == "__main__":
    unittest.main()

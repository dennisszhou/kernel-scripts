from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.config import load_config
from kbake.kernel.checkout import (
    CheckoutError,
    KernelCheckout,
    is_linux_checkout,
    resolve_checkout,
)


def make_checkout(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Makefile").write_text("", encoding="utf-8")
    (root / "Kconfig").write_text("", encoding="utf-8")
    (root / "arch" / "arm64" / "boot").mkdir(parents=True)
    return root


class KernelCheckoutTests(unittest.TestCase):
    def test_detects_linux_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = make_checkout(Path(tmp) / "linux")

            self.assertTrue(is_linux_checkout(checkout))

    def test_x86_kernel_image_path_uses_linux_arch_directory(self) -> None:
        checkout = KernelCheckout(Path("/linux"), "x86_64")

        self.assertEqual(checkout.image_path, Path("/linux/arch/x86/boot/bzImage"))

    def test_resolves_explicit_before_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            explicit = make_checkout(Path(tmp) / "explicit")
            current = make_checkout(Path(tmp) / "current")
            config = load_config()

            checkout = resolve_checkout(config, explicit=explicit, cwd=current)

        self.assertEqual(checkout.path, explicit.resolve())

    def test_resolves_current_directory_before_configured_src(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = make_checkout(Path(tmp) / "current")
            configured = make_checkout(Path(tmp) / "configured")
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                f"""
[kernel]
src = "{configured}"
""",
                encoding="utf-8",
            )
            config = load_config(path=config_path)

            checkout = resolve_checkout(config, explicit=None, cwd=current)

        self.assertEqual(checkout.path, current.resolve())

    def test_resolves_configured_src_after_non_checkout_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            configured = make_checkout(Path(tmp) / "configured")
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                f"""
[kernel]
src = "{configured}"
""",
                encoding="utf-8",
            )
            config = load_config(path=config_path)

            checkout = resolve_checkout(config, explicit=None, cwd=Path(tmp))

        self.assertEqual(checkout.path, configured.resolve())

    def test_missing_checkout_fails_without_hardcoded_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(path=Path(tmp) / "missing.toml")

            with self.assertRaisesRegex(CheckoutError, "could not find"):
                resolve_checkout(config, explicit=None, cwd=Path(tmp))


if __name__ == "__main__":
    unittest.main()

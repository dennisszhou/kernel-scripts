from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kbake.config import Config
from kbake.target import target_spec


class CheckoutError(ValueError):
    """Raised when a Linux checkout cannot be resolved."""


@dataclass(frozen=True)
class KernelCheckout:
    path: Path
    arch: str

    @property
    def config_path(self) -> Path:
        return self.path / ".config"

    @property
    def image_path(self) -> Path:
        return target_spec(self.arch).kernel_image_path(self.path)


def is_linux_checkout(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "Makefile").is_file()
        and (path / "Kconfig").is_file()
        and (path / "arch").is_dir()
    )


def resolve_checkout(
    config: Config,
    *,
    explicit: str | Path | None,
    cwd: Path | None = None,
) -> KernelCheckout:
    arch = config.kernel_arch.value
    candidates: list[tuple[str, Path]] = []
    if explicit is not None:
        candidates.append(("-C", Path(explicit).expanduser()))
    else:
        current = cwd or Path.cwd()
        candidates.append(("current directory", current))
        if config.kernel_src.value is not None:
            candidates.append(("kernel.src", config.kernel_src.value))

    for source, path in candidates:
        resolved = path.resolve()
        if is_linux_checkout(resolved):
            return KernelCheckout(resolved, arch)
        if source == "-C":
            raise CheckoutError(f"{path} is not a Linux checkout")

    raise CheckoutError(
        "could not find a Linux checkout; run from a checkout, pass -C, "
        "or configure kernel.src"
    )

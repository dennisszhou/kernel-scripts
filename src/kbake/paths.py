from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path


ASSET_PACKAGE = "kbake.assets"
BUILDER_DOCKERFILE = "kernel-builder.Dockerfile"
ARM64_KCONFIG = "kconfig.arm64.minimal"
X86_64_KCONFIG = "kconfig.x86_64.minimal"
ROOTFS_IMAGE_SCRIPT = "rootfs-image.sh"
ROOTFS_INITRAMFS_SCRIPT = "rootfs-initramfs.sh"

_ASSET_NAMES = {
    BUILDER_DOCKERFILE,
    ARM64_KCONFIG,
    X86_64_KCONFIG,
    ROOTFS_IMAGE_SCRIPT,
    ROOTFS_INITRAMFS_SCRIPT,
}


@dataclass(frozen=True)
class ProjectPaths:
    asset_package: str = ASSET_PACKAGE

    def resource(self, name: str) -> Traversable:
        self._check_asset_name(name)
        return resources.files(self.asset_package).joinpath(name)

    def read_text(self, name: str) -> str:
        return self.resource(name).read_text(encoding="utf-8")

    def materialize_asset(self, name: str, directory: Path) -> Path:
        self._check_asset_name(name)
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / name
        with self.resource(name).open("rb") as source:
            with output.open("wb") as target:
                shutil.copyfileobj(source, target)
        return output

    def _check_asset_name(self, name: str) -> None:
        if name not in _ASSET_NAMES:
            raise ValueError(f"unknown kbake asset: {name}")

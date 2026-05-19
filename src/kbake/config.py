from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Mapping, TypeVar

from kbake.target import (
    TargetError,
    default_builtin_kconfig,
    default_qemu_binary,
    host_target_arch,
    normalize_target_arch,
)


T = TypeVar("T")

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kernel-workflow" / "config.toml"
DEFAULT_IMAGE_DIR = Path.home() / "workplace-imgs" / "kernel"
DEFAULT_BUILDER_IMAGE = "kernel-builder"
DEFAULT_MEMORY = "2G"
DEFAULT_CPUS = 4

_SCHEMA: dict[str, set[str]] = {
    "images": {"dir", "rootfs", "initramfs"},
    "builder": {"image"},
    "kernel": {"src", "arch", "kconfig"},
    "boot": {"kernel_image", "memory", "cpus", "append"},
    "qemu": {"binary", "cpu"},
}


class ConfigError(ValueError):
    """Raised when the TOML config cannot be parsed as kbake config."""


@dataclass(frozen=True)
class ResolvedValue(Generic[T]):
    value: T
    source: str


@dataclass(frozen=True)
class Config:
    config_path: Path
    images_dir: ResolvedValue[Path]
    images_rootfs: ResolvedValue[Path]
    images_initramfs: ResolvedValue[Path]
    builder_image: ResolvedValue[str]
    kernel_src: ResolvedValue[Path | None]
    kernel_arch: ResolvedValue[str]
    kernel_kconfig: ResolvedValue[str]
    boot_kernel_image: ResolvedValue[Path | None]
    boot_memory: ResolvedValue[str]
    boot_cpus: ResolvedValue[int]
    boot_append: ResolvedValue[str]
    qemu_binary: ResolvedValue[str]
    qemu_cpu: ResolvedValue[str]

    def rows(self) -> list[tuple[str, ResolvedValue[object]]]:
        return [
            ("images.dir", self.images_dir),
            ("images.rootfs", self.images_rootfs),
            ("images.initramfs", self.images_initramfs),
            ("builder.image", self.builder_image),
            ("kernel.src", self.kernel_src),
            ("kernel.arch", self.kernel_arch),
            ("kernel.kconfig", self.kernel_kconfig),
            ("boot.kernel_image", self.boot_kernel_image),
            ("boot.memory", self.boot_memory),
            ("boot.cpus", self.boot_cpus),
            ("boot.append", self.boot_append),
            ("qemu.binary", self.qemu_binary),
            ("qemu.cpu", self.qemu_cpu),
        ]


def config_path(path: str | Path | None) -> Path:
    if path is None:
        return DEFAULT_CONFIG_PATH
    return _path(path)


def default_config_text(
    *,
    image_dir: str | Path = DEFAULT_IMAGE_DIR,
    target_arch: str | None = None,
) -> str:
    image_dir_path = _path(image_dir)
    arch = _normalize_arch(target_arch or _default_host_arch())
    return (
        "version = 1\n"
        "\n"
        "[images]\n"
        f'dir = "{image_dir_path}"\n'
        f'rootfs = "{image_dir_path / "rootfs.img"}"\n'
        f'initramfs = "{image_dir_path / "rootfs.cpio.gz"}"\n'
        "\n"
        "[builder]\n"
        f'image = "{DEFAULT_BUILDER_IMAGE}"\n'
        "\n"
        "[kernel]\n"
        f'arch = "{arch}"\n'
        "\n"
        "[boot]\n"
        f'memory = "{DEFAULT_MEMORY}"\n'
        f"cpus = {DEFAULT_CPUS}\n"
        'append = ""\n'
        "\n"
        "[qemu]\n"
        'cpu = ""\n'
    )


def load_config(
    *,
    path: str | Path | None = None,
    overrides: Mapping[str, object | None] | None = None,
) -> Config:
    selected_path = config_path(path)
    config_values = _read_config(selected_path)
    override_values = {key: value for key, value in (overrides or {}).items()}

    images_dir = _resolved_path(
        "images.dir",
        config_values,
        override_values,
        DEFAULT_IMAGE_DIR,
    )
    images_rootfs = _resolved_path(
        "images.rootfs",
        config_values,
        override_values,
        images_dir.value / "rootfs.img",
    )
    images_initramfs = _resolved_path(
        "images.initramfs",
        config_values,
        override_values,
        images_dir.value / "rootfs.cpio.gz",
    )

    kernel_arch = _resolved_arch(
        "kernel.arch",
        config_values,
        override_values,
        None,
    )

    return Config(
        config_path=selected_path,
        images_dir=images_dir,
        images_rootfs=images_rootfs,
        images_initramfs=images_initramfs,
        builder_image=_resolved_string(
            "builder.image",
            config_values,
            override_values,
            DEFAULT_BUILDER_IMAGE,
        ),
        kernel_src=_resolved_optional_path(
            "kernel.src",
            config_values,
            override_values,
            None,
        ),
        kernel_arch=kernel_arch,
        kernel_kconfig=_resolved_string(
            "kernel.kconfig",
            config_values,
            override_values,
            default_builtin_kconfig(kernel_arch.value),
        ),
        boot_kernel_image=_resolved_optional_path(
            "boot.kernel_image",
            config_values,
            override_values,
            None,
        ),
        boot_memory=_resolved_string(
            "boot.memory",
            config_values,
            override_values,
            DEFAULT_MEMORY,
        ),
        boot_cpus=_resolved_int(
            "boot.cpus",
            config_values,
            override_values,
            DEFAULT_CPUS,
        ),
        boot_append=_resolved_string(
            "boot.append",
            config_values,
            override_values,
            "",
        ),
        qemu_binary=_resolved_string(
            "qemu.binary",
            config_values,
            override_values,
            default_qemu_binary(kernel_arch.value),
        ),
        qemu_cpu=_resolved_string(
            "qemu.cpu",
            config_values,
            override_values,
            "",
        ),
    )


def _read_config(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML config {path}: {exc}") from exc
    return _flatten_config(data)


def _flatten_config(data: Mapping[str, Any]) -> dict[str, object]:
    flattened: dict[str, object] = {}
    for table_name, table_value in data.items():
        if table_name == "version":
            if not isinstance(table_value, int):
                raise ConfigError("config key version must be an integer")
            continue
        if table_name not in _SCHEMA:
            raise ConfigError(f"unknown config table: {table_name}")
        if not isinstance(table_value, Mapping):
            raise ConfigError(f"config table {table_name} must be a table")
        for key, value in table_value.items():
            if key not in _SCHEMA[table_name]:
                raise ConfigError(f"unknown config key: {table_name}.{key}")
            flattened[f"{table_name}.{key}"] = value
    return flattened


def _select(
    key: str,
    config_values: Mapping[str, object],
    overrides: Mapping[str, object | None],
    default: object,
) -> tuple[object, str]:
    if key in overrides and overrides[key] is not None:
        return overrides[key], "cli"
    if key in config_values:
        return config_values[key], "config"
    return default, "default"


def _resolved_string(
    key: str,
    config_values: Mapping[str, object],
    overrides: Mapping[str, object | None],
    default: str,
) -> ResolvedValue[str]:
    value, source = _select(key, config_values, overrides, default)
    if not isinstance(value, str):
        raise ConfigError(f"config key {key} must be a string")
    return ResolvedValue(value, source)


def _resolved_arch(
    key: str,
    config_values: Mapping[str, object],
    overrides: Mapping[str, object | None],
    default: str | None,
) -> ResolvedValue[str]:
    value, source = _select(key, config_values, overrides, default)
    if value is None:
        return ResolvedValue(_default_host_arch(), source)
    if not isinstance(value, str):
        raise ConfigError(f"config key {key} must be a string")
    return ResolvedValue(_normalize_arch(value), source)


def _normalize_arch(value: str) -> str:
    try:
        return normalize_target_arch(value)
    except TargetError as exc:
        raise ConfigError(str(exc)) from exc


def _default_host_arch() -> str:
    try:
        return host_target_arch()
    except TargetError as exc:
        raise ConfigError(
            f"unsupported local host architecture: {exc}; set kernel.arch"
        ) from exc


def _resolved_path(
    key: str,
    config_values: Mapping[str, object],
    overrides: Mapping[str, object | None],
    default: Path,
) -> ResolvedValue[Path]:
    value, source = _select(key, config_values, overrides, default)
    return ResolvedValue(_path(value), source)


def _resolved_optional_path(
    key: str,
    config_values: Mapping[str, object],
    overrides: Mapping[str, object | None],
    default: Path | None,
) -> ResolvedValue[Path | None]:
    value, source = _select(key, config_values, overrides, default)
    if value is None or value == "":
        return ResolvedValue(None, source)
    return ResolvedValue(_path(value), source)


def _resolved_int(
    key: str,
    config_values: Mapping[str, object],
    overrides: Mapping[str, object | None],
    default: int,
) -> ResolvedValue[int]:
    value, source = _select(key, config_values, overrides, default)
    if isinstance(value, bool):
        raise ConfigError(f"config key {key} must be an integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.isdecimal():
        number = int(value)
    else:
        raise ConfigError(f"config key {key} must be an integer")
    if number < 1:
        raise ConfigError(f"config key {key} must be positive")
    return ResolvedValue(number, source)


def _path(value: object) -> Path:
    if isinstance(value, Path):
        return value.expanduser()
    if not isinstance(value, str):
        raise ConfigError("path settings must be strings")
    if not value:
        raise ConfigError("path settings must not be empty")
    return Path(value).expanduser()

from __future__ import annotations

import getpass
import os
import shutil
import socket
from pathlib import Path
from typing import Sequence

from kbake.config import Config
from kbake.docker import DockerRunSpec, DockerVolume, host_user
from kbake.kernel.checkout import KernelCheckout
from kbake.paths import ProjectPaths
from kbake.target import builtin_kconfig_asset, target_spec


class KbuildError(ValueError):
    """Raised when a kernel build command cannot be planned."""


def normalize_remainder(items: Sequence[str]) -> list[str]:
    if items and items[0] == "--":
        return list(items[1:])
    return list(items)


def build_make_args(
    config: Config,
    user_args: Sequence[str],
    *,
    cpu_count: int | None = None,
) -> list[str]:
    args = normalize_remainder(user_args)
    target = target_spec(config.kernel_arch.value)
    planned: list[str] = []
    if not any(arg.startswith("ARCH=") for arg in args):
        planned.append(f"ARCH={target.make_arch}")
    if not _has_jobs_arg(args):
        planned.append(f"-j{cpu_count or os.cpu_count() or 4}")
    planned.extend(args)
    return planned


def make_spec(
    config: Config,
    checkout: KernelCheckout,
    make_args: Sequence[str],
    *,
    tty: bool = False,
) -> DockerRunSpec:
    return DockerRunSpec(
        image=config.builder_image.value,
        command=("make", *make_args),
        platform=target_spec(checkout.arch).docker_platform,
        volumes=(DockerVolume(checkout.path, "/src"),),
        env=kernel_make_env(),
        user=host_user(),
        tty=tty,
    )


def ensure_config_exists(checkout: KernelCheckout) -> None:
    if not checkout.config_path.is_file():
        raise KbuildError(
            f"missing {checkout.config_path}; run `kbake apply-config` "
            "or `kbake make defconfig`"
        )


def apply_config(
    config: Config,
    checkout: KernelCheckout,
    *,
    project_paths: ProjectPaths | None = None,
) -> DockerRunSpec:
    copy_kconfig_fragment(config, checkout.config_path, project_paths or ProjectPaths())
    target = target_spec(checkout.arch)
    return make_spec(config, checkout, [f"ARCH={target.make_arch}", "olddefconfig"])


def copy_kconfig_fragment(
    config: Config,
    target: Path,
    project_paths: ProjectPaths,
) -> None:
    value = config.kernel_kconfig.value
    asset = builtin_kconfig_asset(value)
    if asset is not None:
        with project_paths.resource(asset).open("rb") as source:
            with target.open("wb") as output:
                shutil.copyfileobj(source, output)
            return
    if value.startswith("builtin:"):
        raise KbuildError(f"unknown builtin kconfig fragment: {value}")
    path = Path(value).expanduser()
    if not path.is_file():
        raise KbuildError(f"missing kconfig fragment: {path}")
    shutil.copyfile(path, target)


def _has_jobs_arg(args: Sequence[str]) -> bool:
    for index, arg in enumerate(args):
        if arg.startswith("-j") and arg != "-J":
            return True
        if arg == "--jobs" or arg.startswith("--jobs="):
            return True
        if arg == "-j" and index + 1 < len(args):
            return True
    return False


def kernel_make_env(
    *,
    build_user: str | None = None,
    build_host: str | None = None,
) -> dict[str, str]:
    return {
        "HOME": "/tmp",
        "KBUILD_BUILD_USER": build_user or _host_login_name(),
        "KBUILD_BUILD_HOST": build_host or _host_name(),
    }


def _host_login_name() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return str(os.getuid())


def _host_name() -> str:
    name = socket.gethostname()
    if not name:
        return "localhost"
    return name.split(".", 1)[0]

from __future__ import annotations

import contextlib
import grp
import os
import pwd
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

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
    identity_volumes: Sequence[DockerVolume] = (),
    tty: bool = False,
) -> DockerRunSpec:
    return DockerRunSpec(
        image=config.builder_image.value,
        command=("make", *make_args),
        platform=target_spec(checkout.arch).docker_platform,
        volumes=(DockerVolume(checkout.path, "/src"), *identity_volumes),
        env={"HOME": "/tmp"},
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
    identity_volumes: Sequence[DockerVolume] = (),
    project_paths: ProjectPaths | None = None,
) -> DockerRunSpec:
    copy_kconfig_fragment(config, checkout.config_path, project_paths or ProjectPaths())
    target = target_spec(checkout.arch)
    return make_spec(
        config,
        checkout,
        [f"ARCH={target.make_arch}", "olddefconfig"],
        identity_volumes=identity_volumes,
    )


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


@contextlib.contextmanager
def host_identity_volumes() -> Iterator[tuple[DockerVolume, ...]]:
    identity = _host_identity()
    with tempfile.TemporaryDirectory(prefix="kbake-user-") as tmp:
        directory = Path(tmp)
        passwd_path = directory / "passwd"
        group_path = directory / "group"
        passwd_path.write_text(identity.passwd_text(), encoding="utf-8")
        group_path.write_text(identity.group_text(), encoding="utf-8")
        yield (
            DockerVolume(passwd_path, "/etc/passwd", read_only=True),
            DockerVolume(group_path, "/etc/group", read_only=True),
        )


@dataclass(frozen=True)
class HostIdentity:
    user: str
    uid: int
    group: str
    gid: int

    def passwd_text(self) -> str:
        lines = ["root:x:0:0:root:/root:/bin/bash"]
        if self.uid != 0:
            lines.append(
                f"{self.user}:x:{self.uid}:{self.gid}:{self.user}:/tmp:/bin/bash"
            )
        return "\n".join(lines) + "\n"

    def group_text(self) -> str:
        lines = ["root:x:0:"]
        if self.gid != 0:
            lines.append(f"{self.group}:x:{self.gid}:{self.user}")
        return "\n".join(lines) + "\n"


def _host_identity() -> HostIdentity:
    uid = os.getuid()
    gid = os.getgid()
    return HostIdentity(
        user=_passwd_name(uid),
        uid=uid,
        group=_group_name(gid),
        gid=gid,
    )


def _passwd_name(uid: int) -> str:
    try:
        return _passwd_safe_name(pwd.getpwuid(uid).pw_name, f"user{uid}")
    except KeyError:
        return f"user{uid}"


def _group_name(gid: int) -> str:
    try:
        return _passwd_safe_name(grp.getgrgid(gid).gr_name, f"group{gid}")
    except KeyError:
        return f"group{gid}"


def _passwd_safe_name(value: str, fallback: str) -> str:
    safe_chars = set("abcdefghijklmnopqrstuvwxyz")
    safe_chars.update("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    safe_chars.update("0123456789_.-")
    if value and all(char in safe_chars for char in value):
        return value
    return fallback

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kbake.config import Config
from kbake.docker import DockerRunSpec, DockerVolume, host_user
from kbake.target import target_spec


@dataclass(frozen=True)
class RootfsOutput:
    directory: Path
    filename: str


def output_path(
    config: Config,
    *,
    explicit_path: str | Path | None,
    explicit_directory: str | Path | None,
    default_filename: str,
) -> RootfsOutput:
    if explicit_path is not None and explicit_directory is not None:
        raise ValueError("path and directory are mutually exclusive")
    if explicit_path is not None:
        path = Path(explicit_path).expanduser()
        return RootfsOutput(path.parent, path.name)
    if explicit_directory is not None:
        return RootfsOutput(Path(explicit_directory).expanduser(), default_filename)
    return RootfsOutput(config.images_dir.value, default_filename)


def rootfs_image_spec(
    config: Config,
    *,
    script: Path,
    output: RootfsOutput,
) -> DockerRunSpec:
    return DockerRunSpec(
        image=config.builder_image.value,
        command=("bash", "/tmp/build-rootfs-image.sh"),
        platform=target_spec(config.kernel_arch.value).docker_platform,
        volumes=(
            DockerVolume(output.directory, "/out"),
            DockerVolume(script, "/tmp/build-rootfs-image.sh", read_only=True),
        ),
        env={
            "HOME": "/tmp",
            "ROOTFS_IMAGE_NAME": output.filename,
        },
        privileged=True,
    )


def initramfs_spec(
    config: Config,
    *,
    script: Path,
    output: RootfsOutput,
) -> DockerRunSpec:
    return DockerRunSpec(
        image=config.builder_image.value,
        command=("bash", "/tmp/build-rootfs-initramfs.sh"),
        platform=target_spec(config.kernel_arch.value).docker_platform,
        volumes=(
            DockerVolume(output.directory, "/out"),
            DockerVolume(script, "/tmp/build-rootfs-initramfs.sh", read_only=True),
        ),
        env={
            "HOME": "/tmp",
            "ROOTFS_INITRAMFS_NAME": output.filename,
        },
        user=host_user(),
    )

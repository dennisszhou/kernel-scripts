from __future__ import annotations

from pathlib import Path

from kbake.config import Config
from kbake.docker import DockerBuildSpec
from kbake.target import target_spec


def build_spec(config: Config, *, dockerfile: Path, context: Path) -> DockerBuildSpec:
    return DockerBuildSpec(
        image=config.builder_image.value,
        dockerfile=dockerfile,
        context=context,
        platform=target_spec(config.kernel_arch.value).docker_platform,
    )

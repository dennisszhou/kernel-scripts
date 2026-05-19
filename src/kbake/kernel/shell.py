from __future__ import annotations

from kbake.config import Config
from kbake.docker import DockerRunSpec, DockerVolume, host_user
from kbake.kernel.checkout import KernelCheckout


def shell_spec(
    config: Config,
    checkout: KernelCheckout,
    *,
    root: bool,
    tty: bool,
) -> DockerRunSpec:
    return DockerRunSpec(
        image=config.builder_image.value,
        command=("/bin/bash",),
        volumes=(DockerVolume(checkout.path, "/src"),),
        env={} if root else {"HOME": "/tmp"},
        user=None if root else host_user(),
        tty=tty,
    )

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kbake.docker import DockerBuildSpec, DockerRunSpec, DockerVolume, host_user


class DockerSpecTests(unittest.TestCase):
    def test_build_spec_formats_docker_build(self) -> None:
        spec = DockerBuildSpec(
            image="kernel-builder",
            dockerfile=Path("/tmp/kernel-builder.Dockerfile"),
            context=Path("/tmp/context"),
        )

        self.assertEqual(
            spec.argv(),
            (
                "docker",
                "build",
                "-t",
                "kernel-builder",
                "-f",
                Path("/tmp/kernel-builder.Dockerfile"),
                Path("/tmp/context"),
            ),
        )

    def test_run_spec_formats_privileged_volume_and_env(self) -> None:
        spec = DockerRunSpec(
            image="kernel-builder",
            command=("bash", "/tmp/build.sh"),
            volumes=(
                DockerVolume(Path("/out"), "/out"),
                DockerVolume(Path("/script.sh"), "/tmp/build.sh", read_only=True),
            ),
            env={"ROOTFS_IMAGE_NAME": "rootfs.img", "HOME": "/tmp"},
            privileged=True,
            user="1000:1000",
        )

        argv = spec.argv()

        self.assertIn("--privileged", argv)
        self.assertIn("--user", argv)
        self.assertIn("1000:1000", argv)
        self.assertIn("/out:/out", argv)
        self.assertIn("/script.sh:/tmp/build.sh:ro", argv)
        self.assertIn("HOME=/tmp", argv)
        self.assertIn("ROOTFS_IMAGE_NAME=rootfs.img", argv)

    def test_host_user_uses_process_ids(self) -> None:
        self.assertEqual(host_user(), f"{os.getuid()}:{os.getgid()}")


if __name__ == "__main__":
    unittest.main()

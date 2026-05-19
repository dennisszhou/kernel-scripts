from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from kbake.config import (
    Config,
    ConfigError,
    config_path,
    default_config_text,
    load_config,
)
from kbake.forge import builder, images
from kbake.paths import (
    BUILDER_DOCKERFILE,
    ROOTFS_IMAGE_SCRIPT,
    ROOTFS_INITRAMFS_SCRIPT,
    ProjectPaths,
)
from kbake.runner import Arg, Runner, format_command


class CliError(Exception):
    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv, runner=Runner())


def run_cli(argv: Sequence[str] | None, *, runner: Runner) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.func is cmd_config_init:
            return cmd_config_init(args, config_path(args.config), runner)
        config = load_config(path=args.config, overrides=overrides(args))
        return args.func(args, config, runner)
    except (CliError, ConfigError, ValueError) as exc:
        print(f"kforge: {exc}", file=sys.stderr)
        return getattr(exc, "code", 2)
    except KeyboardInterrupt:
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kforge",
        description="Manage shared kernel workflow artifacts.",
    )
    parser.add_argument("--config", help="TOML config path for this invocation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config = subparsers.add_parser("config", help="manage local config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_init = config_sub.add_parser("init", help="create local config")
    config_init.add_argument(
        "--image-dir",
        default="~/workplace-imgs/kernel",
        help="default directory for generated root artifacts",
    )
    config_init.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing config file",
    )
    config_init.set_defaults(func=cmd_config_init)
    config_show = config_sub.add_parser("show", help="show resolved config")
    config_show.set_defaults(func=cmd_config_show)

    builder_parser = subparsers.add_parser("builder", help="manage builder image")
    builder_sub = builder_parser.add_subparsers(
        dest="builder_command",
        required=True,
    )
    builder_build = builder_sub.add_parser("build", help="build builder image")
    add_builder_options(builder_build)
    builder_build.add_argument(
        "--dry-run",
        action="store_true",
        help="print the Docker command without running it",
    )
    builder_build.set_defaults(func=cmd_builder_build)

    rootfs = subparsers.add_parser("rootfs", help="manage disk rootfs images")
    rootfs_sub = rootfs.add_subparsers(dest="rootfs_command", required=True)
    rootfs_build = rootfs_sub.add_parser("build", help="build rootfs.img")
    add_builder_options(rootfs_build)
    add_output_options(rootfs_build, "rootfs.img")
    rootfs_build.add_argument(
        "--dry-run",
        action="store_true",
        help="print the Docker command without running it",
    )
    rootfs_build.set_defaults(func=cmd_rootfs_build)

    initramfs = subparsers.add_parser("initramfs", help="manage initramfs images")
    initramfs_sub = initramfs.add_subparsers(
        dest="initramfs_command",
        required=True,
    )
    initramfs_build = initramfs_sub.add_parser(
        "build",
        help="build rootfs.cpio.gz",
    )
    add_builder_options(initramfs_build)
    add_output_options(initramfs_build, "rootfs.cpio.gz")
    initramfs_build.add_argument(
        "--dry-run",
        action="store_true",
        help="print the Docker command without running it",
    )
    initramfs_build.set_defaults(func=cmd_initramfs_build)

    return parser


def add_builder_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--builder-image", help="Docker builder image tag")


def add_output_options(parser: argparse.ArgumentParser, filename: str) -> None:
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--path", "-o", help=f"output path for {filename}")
    output.add_argument(
        "--directory",
        "-d",
        help=f"output directory; writes {filename} inside it",
    )


def overrides(args: argparse.Namespace) -> dict[str, object | None]:
    return {
        "builder.image": getattr(args, "builder_image", None),
    }


def cmd_config_init(
    args: argparse.Namespace,
    path: Path,
    runner: Runner,
) -> int:
    del runner
    if path.exists() and not args.force:
        print(f"config already exists: {path}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        default_config_text(image_dir=args.image_dir),
        encoding="utf-8",
    )
    print(f"created {path}")
    return 0


def cmd_config_show(
    args: argparse.Namespace,
    config: Config,
    runner: Runner,
) -> int:
    del args, runner
    print(f"config.path = {config.config_path}")
    width = max(len(name) for name, _ in config.rows())
    for name, value in config.rows():
        print(f"{name:{width}} = {value.value} ({value.source})")
    return 0


def cmd_builder_build(
    args: argparse.Namespace,
    config: Config,
    runner: Runner,
) -> int:
    paths = ProjectPaths()
    with tempfile.TemporaryDirectory(prefix="kforge-builder-") as tmp:
        context = Path(tmp)
        dockerfile = paths.materialize_asset(BUILDER_DOCKERFILE, context)
        spec = builder.build_spec(config, dockerfile=dockerfile, context=context)
        return run_or_print(spec.argv(), args.dry_run, runner)


def cmd_rootfs_build(
    args: argparse.Namespace,
    config: Config,
    runner: Runner,
) -> int:
    output = images.output_path(
        config,
        explicit_path=args.path,
        explicit_directory=args.directory,
        default_filename="rootfs.img",
    )
    with tempfile.TemporaryDirectory(prefix="kforge-rootfs-") as tmp:
        script = ProjectPaths().materialize_asset(ROOTFS_IMAGE_SCRIPT, Path(tmp))
        spec = images.rootfs_image_spec(config, script=script, output=output)
        if not args.dry_run:
            output.directory.mkdir(parents=True, exist_ok=True)
        return run_or_print(spec.argv(), args.dry_run, runner)


def cmd_initramfs_build(
    args: argparse.Namespace,
    config: Config,
    runner: Runner,
) -> int:
    output = images.output_path(
        config,
        explicit_path=args.path,
        explicit_directory=args.directory,
        default_filename="rootfs.cpio.gz",
    )
    with tempfile.TemporaryDirectory(prefix="kforge-initramfs-") as tmp:
        script = ProjectPaths().materialize_asset(
            ROOTFS_INITRAMFS_SCRIPT,
            Path(tmp),
        )
        spec = images.initramfs_spec(config, script=script, output=output)
        if not args.dry_run:
            output.directory.mkdir(parents=True, exist_ok=True)
        return run_or_print(spec.argv(), args.dry_run, runner)


def run_or_print(argv: Sequence[Arg], dry_run: bool, runner: Runner) -> int:
    if dry_run:
        print(format_command(argv))
        return 0
    return runner.run(argv).returncode

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from kbake.config import Config, ConfigError, load_config
from kbake.docker import wants_tty
from kbake.kernel.checkout import CheckoutError, resolve_checkout
from kbake.kernel.kbuild import (
    KbuildError,
    apply_config,
    build_make_args,
    ensure_config_exists,
    make_spec,
    normalize_remainder,
)
from kbake.kernel.shell import shell_spec
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
        config = load_config(path=args.config, overrides=overrides(args))
        return args.func(args, config, runner)
    except (CheckoutError, CliError, ConfigError, KbuildError) as exc:
        print(f"kbake: {exc}", file=sys.stderr)
        return getattr(exc, "code", 2)
    except KeyboardInterrupt:
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kbake",
        description="Build, configure, and boot a Linux kernel checkout.",
    )
    parser.add_argument("--config", help="TOML config path for this invocation")
    parser.add_argument(
        "-C",
        dest="checkout",
        help="run as if started in this Linux checkout",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply = subparsers.add_parser("apply-config", help="apply configured kconfig")
    apply.add_argument("--builder-image", help="Docker builder image tag")
    apply.set_defaults(func=cmd_apply_config)

    make = subparsers.add_parser("make", help="run kernel make in the builder")
    make.add_argument("--builder-image", help="Docker builder image tag")
    make.add_argument("--dry-run", action="store_true", help="print Docker command")
    make.add_argument("make_args", nargs=argparse.REMAINDER)
    make.set_defaults(func=cmd_make)

    build = subparsers.add_parser("build", help="build the kernel checkout")
    build.add_argument("--builder-image", help="Docker builder image tag")
    build.add_argument("--dry-run", action="store_true", help="print Docker command")
    build.add_argument("make_args", nargs=argparse.REMAINDER)
    build.set_defaults(func=cmd_build)

    shell = subparsers.add_parser("shell", help="open a builder shell")
    shell.add_argument("--builder-image", help="Docker builder image tag")
    shell.add_argument("--root", action="store_true", help="run shell as root")
    shell.add_argument("--dry-run", action="store_true", help="print Docker command")
    shell.set_defaults(func=cmd_shell)

    return parser


def overrides(args: argparse.Namespace) -> dict[str, object | None]:
    return {
        "builder.image": getattr(args, "builder_image", None),
    }


def cmd_apply_config(
    args: argparse.Namespace,
    config: Config,
    runner: Runner,
) -> int:
    checkout = resolve_checkout(config, explicit=args.checkout)
    spec = apply_config(config, checkout)
    return runner.run(spec.argv()).returncode


def cmd_make(
    args: argparse.Namespace,
    config: Config,
    runner: Runner,
) -> int:
    checkout = resolve_checkout(config, explicit=args.checkout)
    spec = make_spec(
        config,
        checkout,
        normalize_remainder(args.make_args),
        tty=wants_tty(),
    )
    return run_or_print(spec.argv(), args.dry_run, runner)


def cmd_build(
    args: argparse.Namespace,
    config: Config,
    runner: Runner,
) -> int:
    checkout = resolve_checkout(config, explicit=args.checkout)
    ensure_config_exists(checkout)
    spec = make_spec(
        config,
        checkout,
        build_make_args(config, args.make_args),
        tty=wants_tty(),
    )
    return run_or_print(spec.argv(), args.dry_run, runner)


def cmd_shell(
    args: argparse.Namespace,
    config: Config,
    runner: Runner,
) -> int:
    checkout = resolve_checkout(config, explicit=args.checkout)
    spec = shell_spec(config, checkout, root=args.root, tty=True)
    return run_or_print(spec.argv(), args.dry_run, runner)


def run_or_print(argv: Sequence[Arg], dry_run: bool, runner: Runner) -> int:
    if dry_run:
        print(format_command(argv))
        return 0
    return runner.run(argv).returncode

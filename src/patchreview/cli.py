from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from patchreview.git_range import (
    EmptyGitRangeError,
    GitRangeError,
    GitRangeReviewBuilder,
)
from patchreview.review import (
    ReviewBuilder,
    ReviewEntry,
    read_patch_list,
    write_review_script,
)


EditorRunner = Callable[[Sequence[str]], int]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw_argv:
        separator = raw_argv.index("--")
        parser_argv = raw_argv[:separator]
        nvim_args = raw_argv[separator + 1 :]
    else:
        parser_argv = raw_argv
        nvim_args = []

    parser = argparse.ArgumentParser(
        description="Review an ordered patch directory or Git range in Neovim",
        epilog="Pass additional Neovim arguments after --.",
    )
    parser.add_argument(
        "patch_dir",
        nargs="?",
        help="directory containing patch files",
    )
    parser.add_argument(
        "--base",
        help="review commits from BASE..HEAD instead of a patch directory",
    )
    parser.add_argument(
        "--pattern",
        default="*.patch",
        help="glob for patch files when no series file exists",
    )
    args = parser.parse_args(parser_argv)
    args.nvim_args = nvim_args
    return args


def build_review_entries(
    args: argparse.Namespace,
    source: Path,
    temp_root: Path,
) -> list[ReviewEntry]:
    if args.base is not None:
        if args.patch_dir is not None:
            raise GitRangeError("patch_dir cannot be used with --base")
        return GitRangeReviewBuilder.from_base(source, args.base, temp_root).build()

    if args.patch_dir is None:
        raise FileNotFoundError("patch_dir is required unless --base is provided")

    patch_dir = Path(args.patch_dir).resolve()
    if not patch_dir.is_dir():
        raise FileNotFoundError(f"missing patch directory: {patch_dir}")

    patch_paths = read_patch_list(patch_dir, args.pattern)
    if not patch_paths:
        raise EmptyGitRangeError(f"no patches found in {patch_dir}")

    return ReviewBuilder(source, patch_paths, temp_root).build()


def run_cli(
    argv: list[str] | None = None,
    *,
    cwd: Path | None = None,
    editor_runner: EditorRunner | None = None,
) -> int:
    args = parse_args(argv)
    nvim_args = args.nvim_args

    source = Path.cwd() if cwd is None else cwd
    run_editor = subprocess.call if editor_runner is None else editor_runner
    temp_root = Path(tempfile.mkdtemp(prefix="patchreview-", dir="/tmp"))
    try:
        try:
            review_entries = build_review_entries(args, source, temp_root)
        except EmptyGitRangeError as exc:
            print(exc, file=sys.stderr)
            return 1
        except (FileNotFoundError, GitRangeError, RuntimeError, ValueError) as exc:
            print(exc, file=sys.stderr)
            return 2
        script_path = write_review_script(temp_root, review_entries)
        return run_editor(["nvim", "-S", str(script_path), *nvim_args])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())

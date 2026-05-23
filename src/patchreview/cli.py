from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from patchreview.review import ReviewBuilder, read_patch_list, write_review_script


EditorRunner = Callable[[Sequence[str]], int]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review an ordered patch directory in Neovim"
    )
    parser.add_argument("patch_dir", help="directory containing patch files")
    parser.add_argument(
        "--pattern",
        default="*.patch",
        help="glob for patch files when no series file exists",
    )
    parser.add_argument(
        "nvim_args",
        nargs=argparse.REMAINDER,
        help="additional Neovim arguments after --",
    )
    return parser.parse_args(argv)


def run_cli(
    argv: list[str] | None = None,
    *,
    cwd: Path | None = None,
    editor_runner: EditorRunner | None = None,
) -> int:
    args = parse_args(argv)
    nvim_args = args.nvim_args
    if nvim_args and nvim_args[0] == "--":
        nvim_args = nvim_args[1:]

    patch_dir = Path(args.patch_dir).resolve()
    if not patch_dir.is_dir():
        print(f"missing patch directory: {patch_dir}", file=sys.stderr)
        return 2

    try:
        patch_paths = read_patch_list(patch_dir, args.pattern)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    if not patch_paths:
        print(f"no patches found in {patch_dir}", file=sys.stderr)
        return 1

    source = Path.cwd() if cwd is None else cwd
    run_editor = subprocess.call if editor_runner is None else editor_runner
    temp_root = Path(tempfile.mkdtemp(prefix="patchreview-", dir="/tmp"))
    try:
        try:
            review_entries = ReviewBuilder(source, patch_paths, temp_root).build()
        except (RuntimeError, ValueError) as exc:
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

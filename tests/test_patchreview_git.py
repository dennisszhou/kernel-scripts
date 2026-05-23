from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from patchreview.cli import run_cli
from patchreview.git_range import GitRangeReviewBuilder


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def init_repo(repo: Path) -> None:
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Patch Reviewer")
    git(repo, "config", "user.email", "patchreview@example.com")


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_linear_repo(repo: Path) -> str:
    init_repo(repo)
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    base = commit_all(repo, "base")

    (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
    (repo / "added.txt").write_text("added\n", encoding="utf-8")
    commit_all(repo, "first change")

    (repo / "tracked.txt").write_text("two\n", encoding="utf-8")
    (repo / "added.txt").unlink()
    commit_all(repo, "second change")

    return base


class PatchReviewGitTests(unittest.TestCase):
    def test_base_mode_builds_ordered_commit_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            base = make_linear_repo(repo)
            temp_root = Path(tmp) / "review"

            entries = GitRangeReviewBuilder.from_base(repo, base, temp_root).build()

            by_change = {(entry.patch_no, entry.rel_path): entry for entry in entries}
            self.assertEqual([entry.patch_no for entry in entries], [1, 1, 2, 2])
            self.assertEqual(
                by_change[(1, "tracked.txt")].before.read_text(encoding="utf-8"),
                "base\n",
            )
            self.assertEqual(
                by_change[(1, "tracked.txt")].after.read_text(encoding="utf-8"),
                "one\n",
            )
            self.assertEqual(
                by_change[(1, "added.txt")].before.read_text(encoding="utf-8"),
                "",
            )
            self.assertEqual(
                by_change[(1, "added.txt")].after.read_text(encoding="utf-8"),
                "added\n",
            )
            self.assertEqual(
                by_change[(2, "added.txt")].before.read_text(encoding="utf-8"),
                "added\n",
            )
            self.assertEqual(
                by_change[(2, "added.txt")].after.read_text(encoding="utf-8"),
                "",
            )

    def test_cli_base_mode_invokes_editor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            base = make_linear_repo(repo)
            calls: list[list[str]] = []

            def editor(command: object) -> int:
                argv = [str(arg) for arg in command]  # type: ignore[union-attr]
                calls.append(argv)
                script = Path(argv[2]).read_text(encoding="utf-8")
                self.assertIn("first change", script)
                self.assertIn("second change", script)
                return 0

            code = run_cli(
                ["--base", base, "--", "--clean"],
                cwd=repo,
                editor_runner=editor,
            )

            self.assertEqual(code, 0)
            self.assertEqual(calls[0][0:2], ["nvim", "-S"])
            self.assertEqual(calls[0][-1], "--clean")

    def test_base_mode_reports_empty_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            base = make_linear_repo(repo)
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = run_cli(["--base", "HEAD"], cwd=repo, editor_runner=lambda _: 0)

            self.assertEqual(code, 1)
            self.assertIn("no commits found", stderr.getvalue())
            self.assertNotIn(base, stderr.getvalue())

    def test_base_mode_reports_invalid_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            make_linear_repo(repo)
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = run_cli(
                    ["--base", "does-not-exist"],
                    cwd=repo,
                    editor_runner=lambda _: 0,
                )

            self.assertEqual(code, 2)
            self.assertIn("invalid base commit does-not-exist", stderr.getvalue())

    def test_base_mode_rejects_non_ancestor_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            init_repo(repo)
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            commit_all(repo, "base")
            git(repo, "checkout", "--orphan", "other")
            (repo / "base.txt").unlink()
            (repo / "other.txt").write_text("other\n", encoding="utf-8")
            other = commit_all(repo, "other")
            git(repo, "checkout", "main")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = run_cli(["--base", other], cwd=repo, editor_runner=lambda _: 0)

            self.assertEqual(code, 2)
            self.assertIn("base commit is not an ancestor", stderr.getvalue())

    def test_base_mode_rejects_merge_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            init_repo(repo)
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            base = commit_all(repo, "base")
            git(repo, "checkout", "-b", "side")
            (repo / "side.txt").write_text("side\n", encoding="utf-8")
            commit_all(repo, "side change")
            git(repo, "checkout", "main")
            (repo / "main.txt").write_text("main\n", encoding="utf-8")
            commit_all(repo, "main change")
            git(repo, "merge", "--no-ff", "side", "-m", "merge side")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = run_cli(["--base", base], cwd=repo, editor_runner=lambda _: 0)

            self.assertEqual(code, 2)
            self.assertIn("merge commits are not supported", stderr.getvalue())
            self.assertIn("merge side", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

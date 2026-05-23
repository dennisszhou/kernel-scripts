from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from patchreview.cli import run_cli
from patchreview.review import ReviewBuilder, read_patch_list, touched_files


def write_patch(path: Path, rel_path: str, before: str, after: str) -> None:
    path.write_text(
        f"""diff --git a/{rel_path} b/{rel_path}
--- a/{rel_path}
+++ b/{rel_path}
@@ -1 +1 @@
-{before}
+{after}
""",
        encoding="utf-8",
    )


class PatchReviewTests(unittest.TestCase):
    def test_read_patch_list_uses_series_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patch_dir = Path(tmp)
            first = patch_dir / "0001-first.patch"
            second = patch_dir / "0002-second.patch"
            first.write_text("", encoding="utf-8")
            second.write_text("", encoding="utf-8")
            (patch_dir / "series").write_text(
                "# comment\n0002-second.patch\n\n0001-first.patch -p1\n",
                encoding="utf-8",
            )

            patches = read_patch_list(patch_dir, "*.patch")

            self.assertEqual(patches, [second, first])

    def test_touched_files_reads_git_diff_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patch = Path(tmp) / "change.patch"
            patch.write_text(
                'diff --git "a/file with space.txt" "b/file with space.txt"\n',
                encoding="utf-8",
            )

            self.assertEqual(touched_files(patch), ["file with space.txt"])

    def test_review_builder_generates_snapshots_for_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            patch_dir = root / "patches"
            temp_root = root / "review"
            source.mkdir()
            patch_dir.mkdir()
            (source / "file.txt").write_text("old\n", encoding="utf-8")
            patch = patch_dir / "0001-change.patch"
            write_patch(patch, "file.txt", "old", "new")

            entries = ReviewBuilder(source, [patch], temp_root).build()

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].rel_path, "file.txt")
            self.assertEqual(entries[0].before.read_text(encoding="utf-8"), "old\n")
            self.assertEqual(entries[0].after.read_text(encoding="utf-8"), "new\n")

    def test_cli_reports_missing_patch_directory(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(stderr):
            code = run_cli([str(Path(tmp) / "missing")])

        self.assertEqual(code, 2)
        self.assertIn("missing patch directory", stderr.getvalue())

    def test_cli_invokes_editor_with_generated_review_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            patch_dir = root / "patches"
            source.mkdir()
            patch_dir.mkdir()
            (source / "file.txt").write_text("old\n", encoding="utf-8")
            write_patch(patch_dir / "0001-change.patch", "file.txt", "old", "new")
            calls: list[list[str]] = []

            def editor(command: object) -> int:
                argv = [str(arg) for arg in command]  # type: ignore[union-attr]
                calls.append(argv)
                script_path = Path(argv[2])
                self.assertTrue(script_path.exists())
                self.assertIn("0001-change.patch", script_path.read_text())
                return 0

            code = run_cli(
                [str(patch_dir), "--", "--clean"],
                cwd=source,
                editor_runner=editor,
            )

            self.assertEqual(code, 0)
            self.assertEqual(calls[0][0:2], ["nvim", "-S"])
            self.assertEqual(calls[0][-1], "--clean")


if __name__ == "__main__":
    unittest.main()

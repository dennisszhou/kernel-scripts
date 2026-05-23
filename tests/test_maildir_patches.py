from __future__ import annotations

import contextlib
import io
import mailbox
import sys
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from maildir_patches.cli import run_cli


def run_cmd(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = run_cli(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def add_message(maildir: Path, subject: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message.set_content("patch body\n")

    box = mailbox.Maildir(str(maildir), factory=None, create=False)
    try:
        box.add(message)
        box.flush()
    finally:
        box.close()


class MaildirPatchesTests(unittest.TestCase):
    def test_init_creates_maildir_subdirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            maildir = Path(tmp) / "staging"

            code, stdout, stderr = run_cmd(["init", "--maildir", str(maildir)])

            self.assertEqual(code, 0, stderr)
            self.assertIn("Initialized Maildir", stdout)
            self.assertTrue((maildir / "cur").is_dir())
            self.assertTrue((maildir / "new").is_dir())
            self.assertTrue((maildir / "tmp").is_dir())

    def test_clear_resets_maildir_subdirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            maildir = Path(tmp) / "staging"
            self.assertEqual(run_cmd(["init", "--maildir", str(maildir)])[0], 0)
            (maildir / "cur" / "message").write_text("body", encoding="utf-8")

            code, stdout, stderr = run_cmd(["clear", "--maildir", str(maildir)])

            self.assertEqual(code, 0, stderr)
            self.assertIn("Reset Maildir", stdout)
            self.assertEqual(list((maildir / "cur").iterdir()), [])
            self.assertTrue((maildir / "new").is_dir())
            self.assertTrue((maildir / "tmp").is_dir())

    def test_series_writes_numbered_patches_and_series_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            maildir = Path(tmp) / "staging"
            outdir = Path(tmp) / "patches"
            self.assertEqual(run_cmd(["init", "--maildir", str(maildir)])[0], 0)
            add_message(maildir, "[PATCH 2/2] second thing")
            add_message(maildir, "[PATCH 1/2] first thing")

            code, stdout, stderr = run_cmd(
                ["series", "--maildir", str(maildir), "--outdir", str(outdir)]
            )

            self.assertEqual(code, 0, stderr)
            self.assertIn("Wrote 2 patches", stdout)
            self.assertEqual(
                (outdir / "series").read_text(encoding="utf-8"),
                "0001-first_thing.patch\n0002-second_thing.patch\n",
            )
            self.assertIn(
                b"Subject: [PATCH 1/2] first thing",
                (outdir / "0001-first_thing.patch").read_bytes(),
            )
            self.assertIn(
                b"Subject: [PATCH 2/2] second thing",
                (outdir / "0002-second_thing.patch").read_bytes(),
            )

    def test_init_refuses_existing_non_maildir_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "staging"
            target.mkdir()
            (target / "unrelated").write_text("data", encoding="utf-8")

            code, _, stderr = run_cmd(["init", "--maildir", str(target)])

            self.assertEqual(code, 2)
            self.assertIn("refusing to use non-Maildir tree", stderr)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from patchreview.review import Layout, ReviewEntry


class GitRangeError(Exception):
    """Raised when a Git range cannot be converted into review entries."""


class EmptyGitRangeError(GitRangeError):
    """Raised when the selected range contains no commits."""


@dataclass(frozen=True)
class FileChange:
    before_path: str | None
    after_path: str | None

    @property
    def label_path(self) -> str:
        if self.before_path is not None and self.after_path is not None:
            if self.before_path != self.after_path:
                return f"{self.before_path} -> {self.after_path}"
            return self.after_path
        if self.after_path is not None:
            return self.after_path
        if self.before_path is not None:
            return self.before_path
        raise AssertionError("file change has no paths")


@dataclass(frozen=True)
class CommitReview:
    sha: str
    title: str
    changes: list[FileChange]


def git_stdout(cwd: Path, args: list[str], *, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        if not message:
            message = f"git {' '.join(args)} failed with exit {result.returncode}"
        raise GitRangeError(message)
    return result.stdout


def git_text(cwd: Path, args: list[str], *, check: bool = True) -> str:
    return git_stdout(cwd, args, check=check).decode(
        "utf-8", errors="replace"
    ).strip()


def resolve_repo(cwd: Path) -> Path:
    return Path(git_text(cwd, ["rev-parse", "--show-toplevel"]))


def resolve_commit(repo: Path, ref: str) -> str:
    try:
        return git_text(repo, ["rev-parse", "--verify", f"{ref}^{{commit}}"])
    except GitRangeError as exc:
        raise GitRangeError(f"invalid base commit {ref}: {exc}") from exc


def ensure_base_is_ancestor(repo: Path, base: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, "HEAD"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        return
    if result.returncode == 1:
        raise GitRangeError(f"base commit is not an ancestor of HEAD: {base}")
    message = result.stderr.decode("utf-8", errors="replace").strip()
    raise GitRangeError(message or "failed to check base ancestry")


def commit_title(repo: Path, commit: str) -> str:
    return git_text(repo, ["log", "-1", "--format=%h %s", commit])


def commits_in_range(repo: Path, base: str) -> list[str]:
    output = git_text(repo, ["rev-list", "--reverse", f"{base}..HEAD"])
    if not output:
        raise EmptyGitRangeError(f"no commits found in {base}..HEAD")
    return output.splitlines()


def reject_merge_commits(repo: Path, base: str) -> None:
    output = git_text(
        repo,
        ["rev-list", "--min-parents=2", "--reverse", f"{base}..HEAD"],
    )
    if not output:
        return
    first_merge = output.splitlines()[0]
    raise GitRangeError(
        "merge commits are not supported in patchreview ranges: "
        f"{commit_title(repo, first_merge)}"
    )


def parse_diff_name_status(raw_output: bytes) -> list[FileChange]:
    if not raw_output:
        return []
    fields = raw_output.decode("utf-8", errors="surrogateescape").split("\0")
    if fields and fields[-1] == "":
        fields.pop()

    changes: list[FileChange] = []
    idx = 0
    while idx < len(fields):
        status = fields[idx]
        idx += 1
        if not status:
            continue
        kind = status[0]
        if kind in {"R", "C"}:
            before_path = fields[idx]
            after_path = fields[idx + 1]
            idx += 2
            changes.append(FileChange(before_path, after_path))
            continue

        path = fields[idx]
        idx += 1
        if kind == "A":
            changes.append(FileChange(None, path))
        elif kind == "D":
            changes.append(FileChange(path, None))
        else:
            changes.append(FileChange(path, path))

    return sorted(changes, key=lambda change: change.label_path)


def commit_changes(repo: Path, commit: str) -> list[FileChange]:
    raw_output = git_stdout(
        repo,
        [
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-z",
            f"{commit}^",
            commit,
        ],
    )
    return parse_diff_name_status(raw_output)


def read_blob(repo: Path, commit: str, path: str | None) -> bytes | None:
    if path is None:
        return None
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    return None


def safe_snapshot_name(value: str) -> str:
    return value.replace("/", ":")


class GitRangeReviewBuilder:
    def __init__(self, repo: Path, base: str, temp_root: Path) -> None:
        self.repo = repo
        self.base = base
        self.layout = Layout.create(repo, temp_root)

    @classmethod
    def from_base(
        cls,
        cwd: Path,
        base_ref: str,
        temp_root: Path,
    ) -> "GitRangeReviewBuilder":
        repo = resolve_repo(cwd)
        base = resolve_commit(repo, base_ref)
        ensure_base_is_ancestor(repo, base)
        reject_merge_commits(repo, base)
        return cls(repo, base, temp_root)

    def build(self) -> list[ReviewEntry]:
        commits = [
            CommitReview(
                commit,
                commit_title(self.repo, commit),
                commit_changes(self.repo, commit),
            )
            for commit in commits_in_range(self.repo, self.base)
        ]
        self.layout.make_dirs()

        entries: list[ReviewEntry] = []
        for patch_no, commit in enumerate(commits, start=1):
            entries.extend(self.build_commit(patch_no, len(commits), commit))
        return entries

    def build_commit(
        self, patch_no: int, patch_count: int, commit: CommitReview
    ) -> list[ReviewEntry]:
        entries: list[ReviewEntry] = []
        parent = f"{commit.sha}^"

        for change in commit.changes:
            before = read_blob(self.repo, parent, change.before_path)
            after = read_blob(self.repo, commit.sha, change.after_path)
            if before is None and after is None:
                raise GitRangeError(
                    f"failed to read changed path {change.label_path} in {commit.title}"
                )
            if (before or b"") == (after or b""):
                continue
            entries.append(
                self.entry(patch_no, patch_count, commit, change, before, after)
            )

        return entries

    def entry(
        self,
        patch_no: int,
        patch_count: int,
        commit: CommitReview,
        change: FileChange,
        before: bytes | None,
        after: bytes | None,
    ) -> ReviewEntry:
        name = (
            f"{patch_no:04d} {safe_snapshot_name(commit.title)} "
            f"{safe_snapshot_name(change.label_path)}"
        )
        before_path = self.layout.left / name
        after_path = self.layout.right / name
        self.write_snapshot(before_path, before)
        self.write_snapshot(after_path, after)
        return ReviewEntry(
            patch_no=patch_no,
            patch_count=patch_count,
            patch_name=commit.title,
            rel_path=change.label_path,
            before=before_path,
            after=after_path,
        )

    def write_snapshot(self, path: Path, content: bytes | None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            path.touch()
            return
        path.write_bytes(content)

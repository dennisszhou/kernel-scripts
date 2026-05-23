from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

PATCH_CMD = ["patch", "-f", "-p1"]
VIM_ENTRIES = "__REVIEW_ENTRIES__"
VIM_SCRIPT = """set nosplitbelow
set splitright
set noswapfile
set shadafile=NONE
set diffopt+=linematch:60
let g:review_entries = __REVIEW_ENTRIES__
let g:review_index = 0
let g:review_list_height = min([max([len(g:review_entries), 1]), 10])
function! ReviewBuildQuickfix() abort
  let l:items = []
  for l:idx in range(len(g:review_entries))
    let l:entry = g:review_entries[l:idx]
    call add(l:items, {'text': printf('%4d  %s', l:idx + 1, l:entry.label)})
  endfor
  call setqflist([], 'r', {'title': 'patchreview', 'items': l:items})
endfunction
function! ReviewEnsureQuickfix() abort
  let l:winid = getqflist({'winid': 0}).winid
  if l:winid == 0
    execute 'botright copen ' . g:review_list_height
    let l:winid = getqflist({'winid': 0}).winid
  endif
  if l:winid != 0
    let l:cur_winid = win_getid()
    call win_gotoid(l:winid)
    execute 'resize ' . g:review_list_height
    setlocal winfixheight
    call win_gotoid(l:cur_winid)
  endif
  return l:winid
endfunction
function! ReviewCloseContentWindows() abort
  for l:win in reverse(getwininfo())
    if l:win.tabnr != tabpagenr()
      continue
    endif
    if getbufvar(l:win.bufnr, '&buftype') ==# 'quickfix'
      continue
    endif
    call win_gotoid(l:win.winid)
    close
  endfor
endfunction
function! ReviewSelectQuickfix() abort
  call ReviewOpen(line('.') - 1)
endfunction
function! ReviewSyncQuickfix() abort
  call setqflist([], 'a', {'idx': g:review_index + 1})
endfunction
function! ReviewOpen(idx) abort
  if empty(g:review_entries)
    echo 'No review files were generated'
    return
  endif
  if a:idx < 0 || a:idx >= len(g:review_entries)
    echo 'No more review files'
    return
  endif
  let g:review_index = a:idx
  let l:entry = g:review_entries[a:idx]
  call ReviewEnsureQuickfix()
  call ReviewCloseContentWindows()
  noautocmd aboveleft new
  execute 'edit ' . fnameescape(l:entry.before)
  setlocal readonly nomodifiable
  diffthis
  execute 'rightbelow vert diffsplit ' . fnameescape(l:entry.after)
  setlocal readonly nomodifiable
  diffthis
  wincmd h
  let l:main_winid = win_getid()
  call ReviewEnsureQuickfix()
  call ReviewSyncQuickfix()
  call win_gotoid(l:main_winid)
  echo printf('[%d/%d] patch %d/%d %s', g:review_index + 1, len(g:review_entries), l:entry.patch_index, l:entry.patch_count, l:entry.label)
endfunction
function! ReviewNext() abort
  call ReviewOpen(g:review_index + 1)
endfunction
function! ReviewPrev() abort
  call ReviewOpen(g:review_index - 1)
endfunction
function! ReviewNextPatch() abort
  let l:current_patch = g:review_entries[g:review_index].patch_index
  for l:idx in range(g:review_index + 1, len(g:review_entries) - 1)
    if g:review_entries[l:idx].patch_index != l:current_patch
      call ReviewOpen(l:idx)
      return
    endif
  endfor
  echo 'No more patches'
endfunction
function! ReviewPrevPatch() abort
  let l:current_patch = g:review_entries[g:review_index].patch_index
  for l:idx in reverse(range(0, g:review_index - 1))
    if g:review_entries[l:idx].patch_index != l:current_patch
      call ReviewOpen(l:idx)
      return
    endif
  endfor
  echo 'No earlier patches'
endfunction
command! ReviewNext call ReviewNext()
command! ReviewPrev call ReviewPrev()
command! ReviewNextPatch call ReviewNextPatch()
command! ReviewPrevPatch call ReviewPrevPatch()
command! ReviewList call ReviewEnsureQuickfix()
nnoremap <silent> ]r <Cmd>ReviewNext<CR>
nnoremap <silent> [r <Cmd>ReviewPrev<CR>
nnoremap <silent> ]p <Cmd>ReviewNextPatch<CR>
nnoremap <silent> [p <Cmd>ReviewPrevPatch<CR>
augroup PatchReview
  autocmd!
  autocmd FileType qf if getqflist({'title': 0}).title ==# 'patchreview' | nnoremap <silent><buffer> <CR> <Cmd>call ReviewSelectQuickfix()<CR> | endif
augroup END
call ReviewBuildQuickfix()
call ReviewEnsureQuickfix()
call ReviewOpen(0)
"""


@dataclass(frozen=True)
class ReviewEntry:
    patch_no: int
    patch_count: int
    patch_name: str
    rel_path: str
    before: Path
    after: Path

    @property
    def label(self) -> str:
        return f"{self.patch_no:04d} {self.patch_name} {self.rel_path}"


@dataclass(frozen=True)
class Layout:
    source: Path
    left: Path
    right: Path
    state: Path
    current: Path

    @classmethod
    def create(cls, source: Path, temp_root: Path) -> "Layout":
        state = temp_root / "state"
        return cls(
            source=source,
            left=temp_root / "a",
            right=temp_root / "b",
            state=state,
            current=state / "current",
        )

    def make_dirs(self) -> None:
        self.left.mkdir(parents=True, exist_ok=True)
        self.right.mkdir(parents=True, exist_ok=True)
        self.current.mkdir(parents=True, exist_ok=True)


def read_patch_list(patch_dir: Path, pattern: str) -> list[Path]:
    series_file = patch_dir / "series"
    if series_file.exists():
        patches = []
        for raw_line in series_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            patch_name = line.split()[0]
            patch_path = patch_dir / patch_name
            if not patch_path.is_file():
                raise FileNotFoundError(f"series entry missing on disk: {patch_path}")
            patches.append(patch_path)
        return patches

    return sorted(path for path in patch_dir.glob(pattern) if path.is_file())


def patch_rel_path(raw_path: str) -> str | None:
    path = raw_path.strip()
    if not path or path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def patch_header_path(raw_header: str) -> str:
    header = raw_header.rstrip("\r\n")
    if "\t" in header:
        return header.split("\t", 1)[0].strip()
    header = header.strip()
    parts = shlex.split(header)
    return parts[0] if parts else ""


def diff_header_paths(raw_header: str) -> tuple[str, str] | None:
    parts = shlex.split(raw_header.strip())
    if len(parts) != 4:
        return None
    return parts[2], parts[3]


def touched_files(patch_path: Path) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()

    def add_path(raw_path: str) -> None:
        path = patch_rel_path(raw_path)
        if path is None:
            return
        if path not in seen:
            seen.add(path)
            files.append(path)

    with patch_path.open("r", encoding="utf-8", errors="replace") as patch_file:
        for line in patch_file:
            if line.startswith("diff --git "):
                try:
                    paths = diff_header_paths(line)
                except ValueError as exc:
                    raise ValueError(
                        f"{patch_path}: malformed diff header: {line.rstrip()}"
                    ) from exc
                if paths is not None:
                    for path in paths:
                        add_path(path)
                continue
            if line.startswith("--- ") or line.startswith("+++ "):
                try:
                    header_path = patch_header_path(line[4:])
                except ValueError as exc:
                    raise ValueError(
                        f"{patch_path}: malformed file header: {line.rstrip()}"
                    ) from exc
                add_path(header_path)

    return files


def apply_patch(work_dir: Path, patch_path: Path) -> None:
    with patch_path.open("r", encoding="utf-8") as patch_file:
        subprocess.check_call(PATCH_CMD, stdin=patch_file, cwd=work_dir)


class ReviewBuilder:
    def __init__(
        self, source: Path, patch_paths: list[Path], temp_root: Path
    ) -> None:
        self.layout = Layout.create(source, temp_root)
        self.patch_paths = patch_paths
        self.patch_count = len(patch_paths)

    def build(self) -> list[ReviewEntry]:
        self.layout.make_dirs()
        entries: list[ReviewEntry] = []

        for patch_no, patch_path in enumerate(self.patch_paths, start=1):
            entries.extend(self.build_patch(patch_no, patch_path))

        return entries

    def build_patch(self, patch_no: int, patch_path: Path) -> list[ReviewEntry]:
        files = sorted(set(touched_files(patch_path)))
        work_dir = self.layout.state / f"{patch_no:04d}-work"
        work_dir.mkdir(parents=True, exist_ok=True)

        for rel_path in files:
            self.stage(work_dir, rel_path)

        try:
            apply_patch(work_dir, patch_path)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"failed to apply patch against cumulative tree: {patch_path}"
            ) from exc

        entries: list[ReviewEntry] = []
        for rel_path in files:
            before, after = self.snapshot(work_dir, rel_path)
            if before != after:
                entries.append(self.entry(patch_no, patch_path, work_dir, rel_path))
            self.sync(work_dir, rel_path)

        return entries

    def stage(self, work_dir: Path, rel_path: str) -> None:
        if self.copy(self.layout.current, work_dir, rel_path):
            return
        self.copy(self.layout.source, work_dir, rel_path)

    def snapshot(self, work_dir: Path, rel_path: str) -> tuple[bytes, bytes]:
        before = self.read_bytes(self.layout.current, rel_path)
        if before is None:
            before = self.read_bytes(self.layout.source, rel_path)
        after = self.read_bytes(work_dir, rel_path)
        return before or b"", after or b""

    def entry(
        self, patch_no: int, patch_path: Path, work_dir: Path, rel_path: str
    ) -> ReviewEntry:
        name = f"{patch_no:04d} {patch_path.name} {rel_path.replace('/', ':')}"
        self.write_snapshot(
            (self.layout.current, self.layout.source),
            rel_path,
            self.layout.left,
            name,
        )
        self.write_snapshot((work_dir,), rel_path, self.layout.right, name)
        return ReviewEntry(
            patch_no=patch_no,
            patch_count=self.patch_count,
            patch_name=patch_path.name,
            rel_path=rel_path,
            before=self.layout.left / name,
            after=self.layout.right / name,
        )

    def sync(self, work_dir: Path, rel_path: str) -> None:
        if (work_dir / rel_path).exists():
            self.copy(work_dir, self.layout.current, rel_path)
            return
        (self.layout.current / rel_path).unlink(missing_ok=True)

    def copy(self, src_root: Path, dst_root: Path, rel_path: str) -> bool:
        src_path = src_root / rel_path
        if not src_path.exists():
            return False
        dst_path = dst_root / rel_path
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dst_path)
        return True

    def read_bytes(self, root: Path, rel_path: str) -> bytes | None:
        path = root / rel_path
        if not path.exists():
            return None
        return path.read_bytes()

    def write_snapshot(
        self, roots: tuple[Path, ...], rel_path: str, dst_root: Path, dst_name: str
    ) -> None:
        dst_path = dst_root / dst_name
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        for root in roots:
            src_path = root / rel_path
            if src_path.exists():
                shutil.copyfile(src_path, dst_path)
                return

        dst_path.touch()


def write_review_script(temp_root: Path, review_entries: list[ReviewEntry]) -> Path:
    script_path = temp_root / "review.vim"

    def vim_str(value: str) -> str:
        return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"

    entry_literals = []
    for entry in review_entries:
        entry_literals.append(
            (
                "{'before': %s, 'after': %s, 'label': %s, "
                "'patch_index': %d, 'patch_count': %d}"
            )
            % (
                vim_str(str(entry.before)),
                vim_str(str(entry.after)),
                vim_str(entry.label),
                entry.patch_no,
                entry.patch_count,
            )
        )

    entries = "[%s]" % ", ".join(entry_literals)
    script_path.write_text(
        VIM_SCRIPT.replace(VIM_ENTRIES, entries), encoding="utf-8"
    )
    return script_path

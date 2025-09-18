#!/usr/bin/env python3
"""Utility to locate the least recently used files and applications.

This script scans one or more directories, identifies the files that have not
been accessed for the longest time and optionally removes them with a single
confirmation.  It also inspects directories that typically contain desktop
applications (both binaries on the ``PATH`` and ``.desktop`` launchers) to
highlight the least recently used entries there as well.

The primary signal for "least used" is the access time (``atime``) retrieved
from ``os.stat``.  On most Linux distributions this value is updated lazily
(``relatime``) which is sufficient to distinguish rarely used items.  File
systems mounted with ``noatime`` will not update access times; in such cases
the script still works but the ordering may not reflect real usage.

Example::

    python least_used_cleaner.py --paths ~/Downloads ~/Documents --delete

When ``--delete`` is supplied the tool prints the collected candidates and asks
for a single confirmation before deleting every item in the list.  Use
``--yes`` for non-interactive deletion.  The default directories for the
application scan are derived from the ``PATH`` environment variable combined
with common ``.desktop`` folders.
"""

from __future__ import annotations

import argparse
import heapq
import os
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence


@dataclass(slots=True)
class Candidate:
    """Represents a file or application candidate for deletion."""

    path: Path
    atime: float
    size: int
    kind: str

    @property
    def atime_str(self) -> str:
        """Return a human friendly representation of the access timestamp."""

        try:
            return datetime.fromtimestamp(self.atime).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return "0000-00-00 00:00:00"


def humanize_bytes(value: int) -> str:
    """Convert ``value`` into a friendly size string (e.g. ``12.4 MB``)."""

    suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]
    count = float(value)
    for suffix in suffixes:
        if count < 1024 or suffix == suffixes[-1]:
            return f"{count:.1f} {suffix}"
        count /= 1024
    return f"{value} B"


def _default_file_roots() -> List[Path]:
    """Return sensible default directories to scan for regular files."""

    home = Path.home()
    return [home]


def _default_app_roots() -> List[Path]:
    """Return directories that commonly contain Linux desktop applications."""

    roots: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        try:
            resolved = path.expanduser()
        except RuntimeError:
            resolved = path
        resolved = resolved.resolve() if resolved.exists() else resolved
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(resolved)

    path_env = os.environ.get("PATH", "")
    for part in path_env.split(os.pathsep):
        if not part:
            continue
        candidate = Path(part).expanduser()
        if candidate.exists() and candidate.is_dir():
            _add(candidate)

    for desktop_dir in (
        Path.home() / ".local/share/applications",
        Path("/usr/local/share/applications"),
        Path("/usr/share/applications"),
    ):
        if desktop_dir.exists():
            _add(desktop_dir)

    return roots


def _iter_regular_files(
    roots: Sequence[Path],
    *,
    include_hidden: bool,
    follow_symlinks: bool,
    excludes: Sequence[Path],
) -> Iterator[Path]:
    """Yield regular file paths below ``roots`` honoring various filters."""

    normalized_excludes = []
    for path in excludes:
        expanded = path.expanduser()
        try:
            normalized_excludes.append(expanded.resolve())
        except (OSError, RuntimeError):
            # Ignore paths that cannot be resolved (may not exist or require perms).
            continue

    def _is_excluded(path: Path) -> bool:
        for exc in normalized_excludes:
            try:
                path.resolve().relative_to(exc)
                return True
            except (ValueError, FileNotFoundError, RuntimeError):
                continue
        return False

    stack: list[Path] = []
    for root in roots:
        expanded = root.expanduser()
        if not expanded.exists():
            continue
        stack.append(expanded)

    while stack:
        current = stack.pop()

        if _is_excluded(current):
            continue

        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if not include_hidden and entry.name.startswith('.'):
                        continue

                    try:
                        if entry.is_file(follow_symlinks=follow_symlinks):
                            yield Path(entry.path)
                        elif entry.is_dir(follow_symlinks=follow_symlinks):
                            stack.append(Path(entry.path))
                    except OSError:
                        continue
        except NotADirectoryError:
            # ``current`` can be a file that was queued explicitly.
            try:
                st = current.stat()
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                yield current
        except OSError:
            continue


def _iter_application_files(
    roots: Sequence[Path], *, include_hidden: bool, follow_symlinks: bool
) -> Iterator[Path]:
    """Yield executable files and ``.desktop`` launchers below ``roots``."""

    for root in roots:
        expanded = root.expanduser()
        if not expanded.exists() or not expanded.is_dir():
            continue

        try:
            with os.scandir(expanded) as entries:
                for entry in entries:
                    if not include_hidden and entry.name.startswith('.'):
                        continue

                    try:
                        if entry.is_file(follow_symlinks=follow_symlinks):
                            path = Path(entry.path)
                            if path.suffix == ".desktop" or os.access(path, os.X_OK):
                                yield path
                    except OSError:
                        continue
        except OSError:
            continue


def _collect_least_used(
    paths: Iterable[Path],
    *,
    limit: int,
    kind: str,
    follow_symlinks: bool,
) -> list[Candidate]:
    """Collect the ``limit`` entries with the oldest access time."""

    if limit <= 0:
        return []

    heap: list[tuple[float, str, Candidate]] = []

    for path in paths:
        try:
            st = path.stat(follow_symlinks=follow_symlinks)
        except (FileNotFoundError, PermissionError, OSError):
            continue

        if not stat.S_ISREG(st.st_mode):
            continue

        candidate = Candidate(path=path, atime=st.st_atime, size=st.st_size, kind=kind)

        entry = (-candidate.atime, str(candidate.path), candidate)

        if len(heap) < limit:
            heapq.heappush(heap, entry)
            continue

        newest_atime = -heap[0][0]
        if candidate.atime < newest_atime:
            heapq.heapreplace(heap, entry)

    results = [item[2] for item in heap]
    results.sort(key=lambda c: c.atime)
    return results


def _unique_paths(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Remove duplicate paths while preserving the order of ``candidates``."""

    seen: set[Path] = set()
    unique: list[Candidate] = []
    for candidate in candidates:
        resolved = candidate.path
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def _format_section(title: str, candidates: Sequence[Candidate]) -> str:
    if not candidates:
        return f"{title}\n  (Hiç aday bulunamadı.)"

    lines = [title, "  #  Son erişim           Boyut     Yol"]
    for index, cand in enumerate(candidates, start=1):
        lines.append(
            f"  {index:>2}. {cand.atime_str}  {humanize_bytes(cand.size):>9}  {cand.path}"
        )
    return "\n".join(lines)


def _delete_candidates(candidates: Sequence[Candidate]) -> tuple[int, list[tuple[Path, str]]]:
    """Attempt to delete every candidate and return a summary."""

    errors: list[tuple[Path, str]] = []
    deleted = 0

    for candidate in candidates:
        try:
            candidate.path.unlink()
            deleted += 1
        except FileNotFoundError:
            # Already gone counts as success from the perspective of cleanup.
            deleted += 1
        except OSError as exc:  # pragma: no cover - extremely platform specific.
            errors.append((candidate.path, str(exc)))

    return deleted, errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scan directories for the least recently accessed files and apps."
        )
    )
    parser.add_argument(
        "--paths",
        "-p",
        nargs="*",
        type=Path,
        default=_default_file_roots(),
        help=(
            "Directories to scan for regular files (default: your home directory)."
        ),
    )
    parser.add_argument(
        "--app-paths",
        nargs="*",
        type=Path,
        default=None,
        help="Directories to scan for applications. Defaults to PATH entries and \n"
        "common .desktop folders.",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=50,
        help="Number of items to list for each category (default: 50).",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include dotfiles and entries beginning with '.'",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symbolic links when scanning directories.",
    )
    parser.add_argument(
        "--exclude",
        "-x",
        action="append",
        type=Path,
        default=[],
        help="Exclude the given directories from the file scan.",
    )
    parser.add_argument(
        "--skip-files",
        action="store_true",
        help="Skip the regular file scan.",
    )
    parser.add_argument(
        "--skip-apps",
        action="store_true",
        help="Skip the application scan.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the listed items after a single confirmation step.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Assume yes and delete without prompting.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    file_candidates: list[Candidate] = []
    app_candidates: list[Candidate] = []

    if not args.skip_files:
        file_candidates = _collect_least_used(
            _iter_regular_files(
                args.paths,
                include_hidden=args.include_hidden,
                follow_symlinks=args.follow_symlinks,
                excludes=args.exclude,
            ),
            limit=args.limit,
            kind="file",
            follow_symlinks=args.follow_symlinks,
        )

    if not args.skip_apps:
        app_roots = args.app_paths if args.app_paths is not None else _default_app_roots()
        app_candidates = _collect_least_used(
            _iter_application_files(
                app_roots,
                include_hidden=args.include_hidden,
                follow_symlinks=args.follow_symlinks,
            ),
            limit=args.limit,
            kind="app",
            follow_symlinks=args.follow_symlinks,
        )

    sections: list[str] = []
    if not args.skip_files:
        sections.append(_format_section("En az kullanılan dosyalar", file_candidates))
    if not args.skip_apps:
        sections.append(_format_section("En az kullanılan uygulamalar", app_candidates))

    if sections:
        print("\n\n".join(sections))
    else:
        print("Hiçbir tarama gerçekleştirilmedi. Lütfen seçenekleri kontrol edin.")

    if args.delete:
        targets = _unique_paths(file_candidates + app_candidates)
        if not targets:
            print("\nSilinecek aday bulunamadı.")
            return 0

        if not args.yes:
            print(
                "\nListedeki tüm ögeler silinecek. Onaylamak için 'delete' yazıp "
                "Enter'a basın veya boş bırakın: ",
                end="",
            )
            try:
                confirmation = input().strip().lower()
            except KeyboardInterrupt:
                print("\nİşlem iptal edildi.")
                return 1
            if confirmation != "delete":
                print("İşlem iptal edildi.")
                return 0

        deleted, errors = _delete_candidates(targets)
        print(f"\nSilinen öge sayısı: {deleted}")
        if errors:
            print("Aşağıdaki ögeler silinemedi:")
            for path, message in errors:
                print(f"  {path}: {message}")
            return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    sys.exit(main())

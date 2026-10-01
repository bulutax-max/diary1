#!/usr/bin/env python3
"""Browser-based cleanup utility for finding rarely used files.

This module exposes a small Flask application that scans one or more
directories on the local Linux system, identifies the least recently used
files or executables, and makes them available through a JSON API. The
accompanying front-end (served from ``/``) allows the user to review the
results and delete selected entries with a single action.

Run the application with ``python src/least_used_cleanup_server.py`` and
open ``http://127.0.0.1:5000`` in a browser.
"""

from __future__ import annotations

import argparse
import heapq
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "webapp" / "templates"


def _resolve_path(path: Path) -> Path:
    """Resolve *path* without raising on errors."""

    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def _is_relative_to(path: Path, other: Path) -> bool:
    """Backport of :meth:`Path.is_relative_to` for compatibility."""

    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _format_timestamp(timestamp: float | None) -> str | None:
    """Return an ISO timestamp in the local timezone."""

    if timestamp is None:
        return None
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
    return dt.isoformat(timespec="seconds")


def _humanize_bytes(num: int) -> str:
    """Convert *num* bytes to a human readable string."""

    step = 1024.0
    size = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(size) < step:
            return f"{size:.1f} {unit}"
        size /= step
    return f"{size:.1f} EB"


def _humanize_duration(seconds: float) -> str:
    """Convert *seconds* to a short human friendly duration string."""

    if seconds <= 60:
        return "<1m"
    remaining = int(seconds)
    units = (
        ("y", 365 * 24 * 3600),
        ("d", 24 * 3600),
        ("h", 3600),
        ("m", 60),
    )
    parts: list[str] = []
    for suffix, span in units:
        value, remaining = divmod(remaining, span)
        if value:
            parts.append(f"{value}{suffix}")
        if len(parts) == 2:
            break
    return " ".join(parts) if parts else "<1m"


DEFAULT_EXCLUDE_DIRS = [
    Path("/proc"),
    Path("/sys"),
    Path("/dev"),
    Path("/run"),
    Path("/var/run"),
    Path("/var/lib/docker"),
    Path("/var/lib/containers"),
    Path("/snap"),
    Path("/lost+found"),
]


@dataclass
class FileUsageRecord:
    path: Path
    size: int
    last_access: float | None
    last_modified: float | None
    is_executable: bool
    last_used_ts: float
    unused_seconds: float

    @property
    def category(self) -> str:
        return "application" if self.is_executable else "file"

    def to_payload(self, now: datetime) -> dict:
        return {
            "path": str(self.path),
            "size_bytes": self.size,
            "size_human": _humanize_bytes(self.size),
            "last_access": _format_timestamp(self.last_access),
            "last_modified": _format_timestamp(self.last_modified),
            "last_used": _format_timestamp(self.last_used_ts),
            "unused_for": _humanize_duration(self.unused_seconds),
            "unused_seconds": round(self.unused_seconds, 3),
            "category": self.category,
            "is_executable": self.is_executable,
        }


def _build_record(
    file_path: Path,
    stat_result: os.stat_result,
    now_ts: float,
    include_apps: bool,
    include_regular_files: bool,
    min_size_bytes: int,
    min_unused_seconds: float,
) -> FileUsageRecord | None:
    size = int(stat_result.st_size)
    if size < min_size_bytes:
        return None

    last_access = float(stat_result.st_atime) if stat_result.st_atime else None
    last_modified = float(stat_result.st_mtime) if stat_result.st_mtime else None
    usable_timestamps = [ts for ts in (last_access, last_modified) if ts is not None]
    if not usable_timestamps:
        return None

    last_used_ts = min(usable_timestamps)
    unused_seconds = max(0.0, now_ts - last_used_ts)
    if unused_seconds < min_unused_seconds:
        return None

    mode = stat_result.st_mode
    is_exec = bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    if is_exec and not include_apps:
        return None
    if not is_exec and not include_regular_files:
        return None

    return FileUsageRecord(
        path=file_path,
        size=size,
        last_access=last_access,
        last_modified=last_modified,
        is_executable=is_exec,
        last_used_ts=last_used_ts,
        unused_seconds=unused_seconds,
    )


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    value_lower = value.strip().lower()
    if value_lower in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if value_lower in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _parse_float(value: str | None, default: float, minimum: float | None = None) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    if minimum is not None and parsed < minimum:
        return minimum
    return parsed


def _parse_int(value: str | None, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if minimum is not None and parsed < minimum:
        return minimum
    if maximum is not None and parsed > maximum:
        return maximum
    return parsed


def find_least_used_files(
    directories: Sequence[Path],
    limit: int,
    include_apps: bool,
    include_regular_files: bool,
    follow_symlinks: bool,
    skip_hidden: bool,
    min_size_bytes: int,
    min_unused_seconds: float,
    excluded_dirs: Sequence[Path] = DEFAULT_EXCLUDE_DIRS,
):
    """Scan *directories* and return metadata for the least used entries."""

    now_ts = datetime.now(timezone.utc).timestamp()
    now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc).astimezone()

    heap: list[tuple[float, str, FileUsageRecord]] = []
    visited_files = 0
    considered_files = 0
    missing_dirs: list[str] = []
    errors: list[dict] = []
    skipped_dirs: set[str] = set()
    skipped_hidden: set[str] = set()

    if not include_apps and not include_regular_files:
        return [], {
            "generated_at": now_dt.isoformat(timespec="seconds"),
            "base_directories": [str(p) for p in directories],
            "missing_directories": [],
            "skipped_directories": [],
            "skipped_hidden": [],
            "files_scanned": 0,
            "files_considered": 0,
            "errors": [],
        }

    resolved_bases = [_resolve_path(path) for path in directories]
    base_dir_set = {path for path in resolved_bases if path.exists()}
    resolved_excluded = [_resolve_path(path) for path in excluded_dirs]

    def on_walk_error(exc: OSError):
        errors.append({
            "path": getattr(exc, "filename", None) or str(getattr(exc, "filename2", "")),
            "error": str(exc),
        })

    def should_skip_dir(candidate: Path) -> bool:
        for excluded_resolved in resolved_excluded:
            try:
                if candidate == excluded_resolved or _is_relative_to(candidate, excluded_resolved):
                    return True
            except OSError:
                continue
        return False

    for directory in directories:
        expanded = _resolve_path(directory.expanduser())
        if not expanded.exists():
            missing_dirs.append(str(expanded))
            continue
        if expanded.is_file():
            try:
                stat_result = expanded.stat(follow_symlinks=follow_symlinks)
            except (OSError, PermissionError) as exc:
                errors.append({"path": str(expanded), "error": str(exc)})
                continue
            record = _build_record(
                expanded,
                stat_result,
                now_ts,
                include_apps,
                include_regular_files,
                min_size_bytes,
                min_unused_seconds,
            )
            if record is None:
                continue
            considered_files += 1
            usage_key = record.last_used_ts
            heapq.heappush(heap, (-usage_key, record.path.as_posix(), record))
            if len(heap) > limit:
                heapq.heappop(heap)
            continue

        for root, dirs, files in os.walk(
            expanded,
            topdown=True,
            followlinks=follow_symlinks,
            onerror=on_walk_error,
        ):
            root_path = Path(root)
            # Prune excluded or hidden directories
            kept_dirs: list[str] = []
            for entry in dirs:
                child = root_path / entry
                child_resolved = _resolve_path(child)
                if skip_hidden and entry.startswith(".") and child_resolved not in base_dir_set:
                    skipped_hidden.add(str(child_resolved))
                    continue
                if should_skip_dir(child_resolved):
                    skipped_dirs.add(str(child_resolved))
                    continue
                kept_dirs.append(entry)
            dirs[:] = kept_dirs

            for name in files:
                full_path = root_path / name
                visited_files += 1
                if skip_hidden and name.startswith("."):
                    skipped_hidden.add(str(full_path))
                    continue
                if full_path.is_symlink() and not follow_symlinks:
                    continue
                try:
                    stat_result = full_path.stat(follow_symlinks=follow_symlinks)
                except (OSError, PermissionError) as exc:
                    errors.append({"path": str(full_path), "error": str(exc)})
                    continue

                record = _build_record(
                    full_path,
                    stat_result,
                    now_ts,
                    include_apps,
                    include_regular_files,
                    min_size_bytes,
                    min_unused_seconds,
                )
                if record is None:
                    continue
                considered_files += 1
                usage_key = record.last_used_ts
                heapq.heappush(heap, (-usage_key, record.path.as_posix(), record))
                if len(heap) > limit:
                    heapq.heappop(heap)

    records = [entry[2] for entry in heap]
    records.sort(key=lambda item: item.last_used_ts)

    meta = {
        "generated_at": now_dt.isoformat(timespec="seconds"),
        "base_directories": [str(p) for p in directories],
        "missing_directories": missing_dirs,
        "skipped_directories": sorted(skipped_dirs)[:200],
        "skipped_directories_count": len(skipped_dirs),
        "skipped_hidden": sorted(skipped_hidden)[:200],
        "skipped_hidden_count": len(skipped_hidden),
        "files_scanned": visited_files,
        "files_considered": considered_files,
        "errors": errors[:200],
        "limit": limit,
        "include_apps": include_apps,
        "include_regular_files": include_regular_files,
        "follow_symlinks": follow_symlinks,
        "skip_hidden": skip_hidden,
        "min_size_bytes": min_size_bytes,
        "min_unused_seconds": min_unused_seconds,
    }

    return records, meta


app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
app.config["JSON_SORT_KEYS"] = False
app.url_map.strict_slashes = False


@app.get("/")
def index():
    return render_template("least_used_cleanup.html")


@app.get("/api/least-used")
def api_least_used():
    raw_dirs = request.args.get("dirs")
    if raw_dirs:
        directories = [Path(d.strip()) for d in raw_dirs.split(",") if d.strip()]
    else:
        directories = [Path("~")]

    limit = _parse_int(request.args.get("limit"), 50, minimum=1, maximum=500)
    include_apps = _parse_bool(request.args.get("include_apps"), True)
    include_files = _parse_bool(request.args.get("include_files"), True)
    follow_symlinks = _parse_bool(request.args.get("follow_symlinks"), False)
    skip_hidden = _parse_bool(request.args.get("skip_hidden"), True)
    min_size_mb = _parse_float(request.args.get("min_size_mb"), 0.0, minimum=0.0)
    min_unused_days = _parse_float(request.args.get("min_unused_days"), 0.0, minimum=0.0)

    min_size_bytes = int(min_size_mb * 1024 * 1024)
    min_unused_seconds = min_unused_days * 86400.0

    records, meta = find_least_used_files(
        directories=directories,
        limit=limit,
        include_apps=include_apps,
        include_regular_files=include_files,
        follow_symlinks=follow_symlinks,
        skip_hidden=skip_hidden,
        min_size_bytes=min_size_bytes,
        min_unused_seconds=min_unused_seconds,
    )

    now = datetime.now(timezone.utc).astimezone()
    payload = [record.to_payload(now) for record in records]
    meta["result_count"] = len(payload)

    return jsonify({"meta": meta, "data": payload})


def _validate_deletion_target(path: Path) -> str | None:
    if path == Path("/"):
        return "Refusing to delete the root directory."
    return None


@app.post("/api/delete")
def api_delete():
    payload = request.get_json(silent=True) or {}
    raw_paths = payload.get("paths", [])
    dry_run = bool(payload.get("dry_run", False))

    if not isinstance(raw_paths, list):
        return jsonify({"error": "'paths' must be a list."}), 400

    results: list[dict] = []
    for raw in raw_paths:
        path = Path(str(raw)).expanduser()
        entry = {"path": str(path)}

        if not os.path.lexists(path):
            entry["status"] = "missing"
            results.append(entry)
            continue

        guard_message = _validate_deletion_target(path)
        if guard_message:
            entry["status"] = "skipped"
            entry["error"] = guard_message
            results.append(entry)
            continue

        if path.is_dir() and not path.is_symlink():
            entry["status"] = "skipped"
            entry["error"] = "Refusing to delete directories automatically."
            results.append(entry)
            continue

        if dry_run:
            entry["status"] = "dry-run"
            results.append(entry)
            continue

        try:
            path.unlink()
            entry["status"] = "deleted"
        except (OSError, PermissionError) as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)

        results.append(entry)

    return jsonify({"results": results})


def create_app() -> Flask:
    """Return the configured Flask application (for WSGI servers)."""

    return app


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Least used files cleaner web app")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args(argv)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
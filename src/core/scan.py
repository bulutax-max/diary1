import os, time
from pathlib import Path
from typing import List, Dict, Tuple

SECONDS_PER_DAY = 86400

def human_size(n: int) -> str:
    for unit in ["B","KB","MB","GB","TB","PB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} EB"

def _dir_size(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for f in files:
            try:
                fp = Path(root) / f
                total += fp.stat().st_size
            except Exception:
                pass
    return total

def largest_dirs(root: Path, top_n: int = 10) -> List[Dict]:
    rows = []
    with os.scandir(root) as it:
        for entry in it:
            if entry.is_dir(follow_symlinks=False):
                p = Path(entry.path)
                try:
                    size = _dir_size(p)
                    rows.append({
                        "path": str(p),
                        "size_bytes": size,
                        "size_h": human_size(size),
                        "type": "dir"
                    })
                except Exception:
                    pass
    rows.sort(key=lambda r: r["size_bytes"], reverse=True)
    return rows[:top_n]

def recent_files(root: Path, days: int = 7, limit: int = 200) -> List[Dict]:
    cutoff = time.time() - days * SECONDS_PER_DAY
    rows = []
    for r, dnames, fnames in os.walk(root, followlinks=False):
        for fn in fnames:
            p = Path(r) / fn
            try:
                st = p.stat()
                if st.st_mtime >= cutoff:
                    rows.append({
                        "path": str(p),
                        "mtime": st.st_mtime,
                        "size_bytes": st.st_size,
                        "size_h": human_size(st.st_size),
                        "type": "file"
                    })
            except Exception:
                pass
    rows.sort(key=lambda x: x["mtime"], reverse=True)
    return rows[:limit]

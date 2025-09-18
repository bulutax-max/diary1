#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import subprocess

def list_largest_dirs(base: Path, depth: int = 1, top_n: int = 10):
    """
    base'in altındaki klasörleri boyuta göre sıralar (toplam disk kullanımına göre).
    Linux'ta en hızlı yol çoğu zaman 'du' komutudur; yoksa Python ile de yapılabilir.
    """
    # 'du' hızlı; yoksa Python fallback ekleyebilirsin
    try:
        cmd = ["du", "-b", f"--max-depth={depth}", str(base)]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        rows = []
        for line in out.strip().splitlines():
            # "BYTES\tPATH"
            size_str, path_str = line.split("\t", 1)
            rows.append((int(size_str), path_str))
        rows.sort(reverse=True, key=lambda x: x[0])
        return rows[:top_n]
    except Exception:
        # Basit ve daha yavaş Python fallback
        sizes = []
        for p in base.iterdir():
            try:
                if p.is_dir():
                    total = 0
                    for root, dirs, files in os.walk(p):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                total += os.path.getsize(fp)
                            except OSError:
                                pass
                    sizes.append((total, str(p)))
            except OSError:
                pass
        sizes.sort(reverse=True, key=lambda x: x[0])
        return sizes[:top_n]

def list_recent_files(base: Path, days: int = 7, limit: int = 50):
    """
    base altında son 'days' gün içinde değişen dosyaları mtime’a göre listeler.
    """
    cutoff = time.time() - days * 86400
    hits = []
    for root, dirs, files in os.walk(base):
        for f in files:
            fp = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(fp)
                if mtime >= cutoff:
                    hits.append((mtime, fp))
            except OSError:
                pass
    hits.sort(reverse=True, key=lambda x: x[0])
    return hits[:limit]

def humanize_bytes(n: int) -> str:
    for unit in ["B","KB","MB","GB","TB","PB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} EB"

def write_or_print(lines, output: Path | None):
    if output:
        output.write_text("\n".join(lines), encoding="utf-8")
        print(f"[✓] Çıktı yazıldı → {output}")
    else:
        print("\n".join(lines))

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="disk_avcisi",
        description="Disk Avcısı: En büyük klasörleri ve yakın zamanda değişen dosyaları raporlar.",
        epilog="Örnekler:\n"
               "  disk_avcisi.py --largest 15 --depth 1 --path /home/ubntu --human\n"
               "  disk_avcisi.py --changed 7 --limit 100 --path ~/Downloads --output recent.txt",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--path", "-p", type=str, default=".",
                        help="Taranacak başlangıç yolu (varsayılan: geçerli klasör).")
    parser.add_argument("--largest", "-L", type=int, default=0,
                        help="En büyük N klasörü listele (0 = atla).")
    parser.add_argument("--depth", "-d", type=int, default=1,
                        help="Klasör derinliği (du --max-depth karşılığı). Varsayılan: 1")
    parser.add_argument("--changed", "-c", type=int, default=0,
                        help="Son X gün içinde değişen dosyaları listele (0 = atla).")
    parser.add_argument("--limit", "-n", type=int, default=50,
                        help="Değişen dosyalarda maksimum satır sayısı (varsayılan: 50).")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Çıktıyı yazmak için dosya yolu (örn. largest.txt). Boşsa ekrana yazılır.")
    parser.add_argument("--human", action="store_true",
                        help="Boyutları insan okunur biçimde göster (GB/MB).")
    parser.add_argument("--version", action="version", version="disk_avcisi 0.1.0")
    return parser

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    base = Path(os.path.expanduser(args.path)).resolve()
    if not base.exists():
        print(f"[!] Yol bulunamadı: {base}", file=sys.stderr)
        sys.exit(1)

    lines = []
    # LARGEST
    if args.largest > 0:
        rows = list_largest_dirs(base, depth=args.depth, top_n=args.largest)
        lines.append(f"# En büyük {args.largest} klasör (depth={args.depth}) @ {base}")
        for size, p in rows:
            size_str = humanize_bytes(size) if args.human else str(size)
            lines.append(f"{size_str}\t{p}")
        lines.append("")

    # CHANGED
    if args.changed > 0:
        hits = list_recent_files(base, days=args.changed, limit=args.limit)
        lines.append(f"# Son {args.changed} günde değişen dosyalar (max {args.limit}) @ {base}")
        for mtime, fp in hits:
            ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"{ts}\t{fp}")
        lines.append("")

    if not lines:
        # Kullanıcı hiçbir bayrak vermezse yardım göster:
        parser.print_help()
        return

    out = Path(args.output) if args.output else None
    write_or_print(lines, out)

if __name__ == "__main__":
    main()

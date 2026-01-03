#!/usr/bin/env python3
import os
import re
import csv
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Tuple

VALID_VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".m2ts"}

# ---- ANSI colors ----
C_RESET  = "\033[0m"
C_RED    = "\033[31m"
C_GREEN  = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE   = "\033[34m"

def colorize(s: str, c: str) -> str:
    return f"{c}{s}{C_RESET}"

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

# ---- light parsing from filename (fallback) ----
RES_RE = re.compile(r"\b(2160|1080|720|480|360)p\b", re.IGNORECASE)
CODEC_RE = re.compile(r"\b(x265|h265|hevc)\b", re.IGNORECASE)

@dataclass
class MediaInfo:
    path: Path
    width: Optional[int]
    height: Optional[int]
    bitrate_bps: Optional[int]
    is_hevc: bool
    guessed_res: Optional[int]  # like 1080 from filename

def has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None

SEVERITY = {
    C_RED:  0,  # worst
    C_YELLOW: 1,
    C_GREEN: 2, 
    C_BLUE: 3, #best
    C_RESET: 9
}

LABEL_FOR_COLOR = {
    C_RED: "RED",
    C_YELLOW: "YELLOW",
    C_BLUE: "BLUE",
    C_GREEN: "GREEN",
    C_RESET: "INFO"
}

def ffprobe_info(p: Path) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[str]]:
    """
    Returns (width, height, bitrate_bps, codec_name) using ffprobe.
    bitrate may be None for some containers; we’ll still classify with what we have.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name:format=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(p)
    ]
    # Output order: width, height, codec_name, format_bit_rate (depends a bit; handle defensively)
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip().splitlines()
    except Exception:
        return None, None, None, None

    width = height = bitrate = None
    codec = None

    # Common case: [width, height, codec_name, bit_rate]
    # Sometimes bit_rate missing; sometimes format appears but stream doesn't.
    nums = []
    for line in out:
        if line.isdigit():
            nums.append(int(line))
        elif line:
            codec = line

    if len(nums) >= 2:
        width, height = nums[0], nums[1]
    if len(nums) >= 3:
        # format bit_rate usually last numeric line
        bitrate = nums[-1] if nums[-1] > 10_000 else None

    return width, height, bitrate, codec

def guess_from_name(name: str) -> Tuple[Optional[int], bool]:
    m = RES_RE.search(name)
    guessed_res = int(m.group(1)) if m else None
    is_hevc = bool(CODEC_RE.search(name))
    return guessed_res, is_hevc

def collect_media(root: Path) -> List[Path]:
    return [p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in VALID_VIDEO_EXTENSIONS]

def bps_to_mbps(bps: Optional[int]) -> Optional[float]:
    if not bps:
        return None
    return bps / 1_000_000.0

def quality_tag(info: MediaInfo) -> str:
    if info.height:
        res = f"{info.height}p"
    elif info.guessed_res:
        res = f"{info.guessed_res}p"
    else:
        res = "?p"
    codec = "HEVC" if info.is_hevc else "H264"
    return f"{res:6} {codec}"


def classify(info: MediaInfo) -> Tuple[str, str]:
    res = info.height if info.height else info.guessed_res

    low_res = (res is not None and res < 1080)
    low_codec = (not info.is_hevc)  # your “low bitrate”

    if info.is_hevc and res is not None and res >= 2160:
        return "4K", C_BLUE

    if info.is_hevc and res is not None and res >= 1080:
        return "GOOD", C_GREEN

    if res is None:
        return "UNK", C_YELLOW  # don’t accidentally mark green

    # exactly one low
    if low_res ^ low_codec:
        return "MID", C_YELLOW

    # both low
    if low_res and low_codec:
        return "LOW", C_RED

    return "OK", C_RESET



def cleanup_trash(root: Path) -> int:
    deleted = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name == ".DS_Store" or p.name.startswith("._"):
            try:
                p.unlink()
                deleted += 1
            except Exception:
                pass
    return deleted

def write_quality_csv(rows: List[Dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["path", "size_bytes", "width", "height", "hevc", "label", "tag"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def group_duplicates_by_name_size(files: List[Path]) -> Dict[Tuple[str, int], List[Path]]:
    """
    Fast duplicate grouping: (lower_name, size_bytes).
    This catches obvious dupes like "movie.mkv" and "movie.mkv (1)" that are same size.
    """
    groups: Dict[Tuple[str, int], List[Path]] = {}
    for p in files:
        try:
            size = p.stat().st_size
        except Exception:
            continue
        key = (normalize_dupe_name(p.name), size)
        groups.setdefault(key, []).append(p)
    return {k: v for k, v in groups.items() if len(v) > 1}

def interactive_duplicate_review(dupe_groups: Dict[Tuple[str, int], List[Path]]) -> None:
    """
    One group at a time:
      k = keep all
      d = delete selected
      s = stop
    """
    keys = list(dupe_groups.keys())
    keys.sort(key=lambda k: k[0])

    for key in keys:
        name, size = key
        items = dupe_groups[key]

        clear_screen()
        print(colorize("Duplicate group:", C_YELLOW))
        print(f"Name: {name}")
        print(f"Size: {size} bytes")
        print("\nFiles:")
        for i, p in enumerate(items, start=1):
            print(f"  {i}) {p}")

        print("\nActions:")
        print("  k) keep all (skip)")
        print("  d) delete one or more")
        print("  s) stop")

        choice = input("Select action: ").strip().lower()
        if choice == "s":
            return
        if choice == "k":
            continue
        if choice == "d":
            sel = input("Enter numbers to delete (e.g. 2 3), or b to back: ").strip().lower()
            if sel == "b":
                continue
            nums = []
            for tok in sel.split():
                if tok.isdigit():
                    nums.append(int(tok))
            nums = sorted(set(n for n in nums if 1 <= n <= len(items)), reverse=True)
            if not nums:
                input("No valid selections. (enter)")
                continue

            confirm = input("Type YES to delete selected: ").strip()
            if confirm != "YES":
                input("Cancelled. (enter)")
                continue

            for n in nums:
                target = items[n-1]
                try:
                    target.unlink()
                    print(colorize(f"Deleted: {target}", C_RED))
                except Exception as e:
                    print(colorize(f"Failed to delete {target}: {e}", C_RED))
            input("\nDone. (enter)")
        else:
            input("Invalid choice. (enter)")
COPY_TAIL_RE = re.compile(r"\s*(\(\d+\)|copy|duplicate|dup)\s*$", re.IGNORECASE)

def normalize_dupe_name(name: str) -> str:
    """
    Normalize common duplicate suffix patterns:
      "Movie.mkv (1)" -> "movie.mkv"
      "Movie copy.mkv" -> "movie.mkv"
    Keeps extension intact.
    """
    p = Path(name)
    stem = p.stem
    ext = "".join(p.suffixes)  # handles .eng.srt etc if you ever reuse this
    stem = COPY_TAIL_RE.sub("", stem).strip()
    return (stem + ext).lower()

def print_menu(source: Optional[Path]) -> None:
    print("Phase 0 — Hygiene Menu\n")
    print(f"SOURCE: {source if source else '(not set)'}\n")
    print("1) Set SOURCE (manual path)")
    print("2) Cleanup trash (.DS_Store / ._*)")
    print("3) Generate quality report (color + CSV)")
    print("4) Duplicates report (name+size)")
    print("5) Review duplicates (interactive delete)")
    print("6) Exit")

def main():
    source: Optional[Path] = None
    last_quality_rows: List[Dict[str, str]] = []
    last_dupes: Dict[Tuple[str, int], List[Path]] = {}

    while True:
        clear_screen()
        print_menu(source)
        choice = input("\nEnter number: ").strip()

        if choice == "1":
            raw = input("Enter SOURCE path: ").strip()
            p = Path(raw).expanduser().resolve()
            if p.exists() and p.is_dir():
                source = p
            else:
                input("Invalid directory. (enter)")

        elif choice == "2":
            if not source:
                input("Set SOURCE first. (enter)")
                continue
            deleted = cleanup_trash(source)
            input(f"Deleted {deleted} trash files. (enter)")

        elif choice == "3":
            if not source:
                input("Set SOURCE first. (enter)")
                continue

            use_ff = has_ffprobe()
            files = collect_media(source)

            rows: List[Dict[str, str]] = []
            
            entries = []  # (severity, color, label_short, tag, filename, rowdict)

            counts = {"RED": 0, "YELLOW": 0, "BLUE": 0, "GREEN": 0, "INFO": 0}

            for p in files:
                guessed_res, guessed_hevc = guess_from_name(p.name)

                width = height = bitrate = None
                codec = None
                if use_ff:
                    width, height, bitrate, codec = ffprobe_info(p)

                is_hevc = guessed_hevc or (codec or "").lower() in {"hevc", "h265"}

                info = MediaInfo(
                    path=p,
                    width=width,
                    height=height,
                    bitrate_bps=bitrate,
                    is_hevc=is_hevc,
                    guessed_res=guessed_res
                )

                label_short, col = classify(info)
                tag = quality_tag(info)

                label_text = LABEL_FOR_COLOR.get(col, "INFO")
                counts[label_text] = counts.get(label_text, 0) + 1

                row = {
                        "path": str(p),
                        "size_bytes": str(p.stat().st_size),
                        "width": "" if width is None else str(width),
                        "height": "" if height is None else str(height),
                        "hevc": "yes" if is_hevc else "no",
                        "label": label_text,
                        "tag": tag,
                    }


                entries.append((SEVERITY.get(col, 9), col, label_text, tag, p.name, row))

            # sort worst -> best, then by filename
            entries.sort(key=lambda x: (x[0], x[4].lower()))

            # print
            for _, col, label_text, tag, name, _row in entries:
                print(colorize(f"[{label_text:5}]", col), f"{tag} | {name}")

            # footer
            total = len(entries)
            print("\n" + "-" * 60)
            print(
                f"Total: {total} | "
                f"{colorize('RED ' + str(counts.get('RED',0)), C_RED)} | "
                f"{colorize('YELLOW ' + str(counts.get('YELLO',0)), C_YELLOW)} | "
                f"{colorize('GREEN ' + str(counts.get('GREEN',0)), C_GREEN)} | "
                f"{colorize('BLUE ' + str(counts.get('BLUE',0)), C_BLUE)} | "
            )

            # rows for CSV
            rows = [e[5] for e in entries]
            out_csv = (Path.cwd() / "reports" / "quality_report.csv").resolve()
            write_quality_csv(rows, out_csv)
            last_quality_rows = rows
            input(f"\nQuality report written to: {out_csv}\n(enter)")

        elif choice == "4":
            if not source:
                input("Set SOURCE first. (enter)")
                continue
            files = collect_media(source)
            dupes = group_duplicates_by_name_size(files)
            last_dupes = dupes

            out_csv = (Path.cwd() / "reports" / "duplicates_name_size.csv").resolve()
            out_csv.parent.mkdir(parents=True, exist_ok=True)

            with out_csv.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["name", "size_bytes", "count", "paths"])
                for (name, size), paths in sorted(dupes.items(), key=lambda x: x[0][0]):
                    w.writerow([name, size, len(paths), " | ".join(str(p) for p in paths)])

            input(f"Found {len(dupes)} duplicate groups.\nCSV: {out_csv}\n(enter)")

        elif choice == "5":
            if not last_dupes:
                input("Run duplicates report first (option 4). (enter)")
                continue
            interactive_duplicate_review(last_dupes)

        elif choice == "6":
            return

        else:
            input("Invalid choice. (enter)")

if __name__ == "__main__":
    main()

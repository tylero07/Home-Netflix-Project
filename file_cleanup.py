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
JUNK_TOKENS_RE = re.compile(r"""(?ix)\b(2160p|1080p|720p|480p|360p|x264|h264|avc|x265|h265|hevc|bluray|bdrip|brrip|webrip|web\-dl|hdr|dv|dolby\.?vision
                            |atmos|remux|proper|repack|extended|unrated|director'?s\.?cut)\b""")
SAMPLE_DIR_NAMES = {"sample", "samples"}
SAMPLE_NAME_HINTS = {"sample"}  # you can expand later: {"sample", "rarbg"}
QUARANTINE_DIRNAME = "_SAMPLES"

YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
def is_sample_dir(path: Path) -> bool:
    return path.is_dir() and path.name.lower() in SAMPLE_DIR_NAMES

def looks_like_sample_file(path: Path) -> bool:
    if not path.is_file():
        return False
    low = path.name.lower()
    # common: "sample.mkv", "...sample...", "RARBG sample..."
    if "sample" in low:
        return True
    # also catch tiny “movie” files sometimes used as samples (optional)
    return False

def progress(i: int, total: int, *, every: int = 1, prefix: str = "") -> None:
    if total == 0:
        return
    if i == 1 or i == total or (i % every == 0):
        pct = (i / total) * 100
        print(f"{prefix}{i}/{total} ({pct:5.1f}%)", end="\r", flush=True)
        if i == total:
            print()  # newline at end
            
def quarantine_sample(path: Path, root: Path) -> Optional[Path]:
    """
    Move a sample dir/file into root/_SAMPLES preserving name.
    Returns new path if moved, else None.
    """
    dest_dir = root / QUARANTINE_DIRNAME
    dest_dir.mkdir(exist_ok=True)

    dest = dest_dir / path.name
    dest = resolve_collision(dest)

    try:
        path.rename(dest)
        return dest
    except PermissionError:
        # if uchg locked, you can reuse your unlock prompt flow here if desired
        return None

def variant_key_from_filename(name: str) -> str:
    """
    Build a movie identity key used ONLY for grouping variants.
    Strips: copy/(1), extension, junk tokens (1080p/x265/etc), normalizes separators.
    Keeps: title words + year (if present) so remakes don't collide.
    """
    # strip duplicate markers and extension(s)
    base = normalize_dupe_name(name)
    p = Path(base)
    stem = p.stem  # stem WITHOUT extension(s)

    # normalize separators
    s = re.sub(r"[._\-]+", " ", stem).strip()

    # keep year if present (helps avoid collisions)
    year = YEAR_RE.search(s)
    y = year.group(1) if year else ""

    # remove junk tokens (quality/source/etc)
    s = JUNK_TOKENS_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()

    # build key
    return (s + (" " + y if y else "")).strip().lower()

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

def interactive_variant_review(variant_groups: Dict[str, List[Path]]) -> None:
    keys = sorted(variant_groups.keys())

    for key in keys:
        items = variant_groups[key]

        clear_screen()
        print(colorize("Variant group (same name, different sizes):", C_YELLOW))
        print(f"Key: {key}\n")

        for i, p in enumerate(items, start=1):
            size = p.stat().st_size
            print(f"  {i}) {size} bytes | {p}")

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

            nums = sorted(
                {int(tok) for tok in sel.split() if tok.isdigit() and 1 <= int(tok) <= len(items)},
                reverse=True
            )
            if not nums:
                input("No valid selections. (enter)")
                continue

            confirm = input("Type YES to delete selected variants: ").strip()
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

def group_variants_by_name(files: List[Path]) -> Dict[str, List[Path]]:
    groups: Dict[str, List[Path]] = {}
    for p in files:
        key = variant_key_from_filename(p.name)
        groups.setdefault(key, []).append(p)

    # only groups with 2+ videos
    groups = {k: v for k, v in groups.items() if len(v) > 1}

    # sort each group by size desc (largest first)
    for k, items in groups.items():
        groups[k] = sorted(items, key=lambda x: x.stat().st_size, reverse=True)
    return groups

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

DUPE_SUFFIX_RE = re.compile(
    r"""(?ix)
    ^(?P<base>.+?)               # base name
    (?:\s*(?:\(\d+\)|copy|duplicate|dup))?  # optional dupe marker
    (?P<ext>\.[a-z0-9]+(?:\.[a-z0-9]+)*)$   # extension(s) at end
    """
)

def count_dir_stats(dirpath: Path) -> tuple[int, int]:
    subdirs = 0
    vids = 0
    for p in dirpath.iterdir():
        if p.is_dir():
            subdirs += 1
        elif p.is_file() and p.suffix.lower() in VALID_VIDEO_EXTENSIONS:
            vids += 1
    return subdirs, vids

def write_variants_csv(variants: Dict[str, List[Path]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["normalized_name", "count", "sizes_bytes", "paths"])
        for name, paths in sorted(variants.items(), key=lambda x: x[0]):
            sizes = [p.stat().st_size for p in paths]
            w.writerow([name, len(paths), " | ".join(map(str, sizes)),
                        " | ".join(str(p) for p in paths)])

def browse_for_directory(start: Path) -> Optional[Path]:
    cwd = start.expanduser().resolve()

    while True:
        clear_screen()
        print("Browse for SOURCE directory\n")
        print(f"Current: {cwd}\n")

        dirs = sorted([p for p in cwd.iterdir() if p.is_dir()])

        print("  0) .. (up one level)")
        for i, d in enumerate(dirs, start=1):
            subdir_count, video_count = count_dir_stats(d)
            print(f"  {i}) {d.name}/ [{subdir_count} dirs | {video_count} videos]")

        print("\nOptions:")
        print("  s) select this directory as SOURCE")
        print("  m) enter manual path")
        print("  b) back to main menu")

        sel = input("\nSelect folder #: ").strip().lower()

        if sel == "b":
            return None
        if sel == "s":
            return cwd
        if sel == "m":
            raw = input("Enter path: ").strip()
            p = Path(raw).expanduser().resolve()
            if p.exists() and p.is_dir():
                return p
            input("Invalid directory. (enter)")
            continue
        if sel == "0":
            if cwd.parent != cwd:
                cwd = cwd.parent
            continue
        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(dirs):
                cwd = dirs[idx - 1]
            else:
                input("Invalid selection. (enter)")
            continue

        # allow typing folder name directly
        maybe = (cwd / sel).resolve()
        if maybe.exists() and maybe.is_dir():
            cwd = maybe
        else:
            input("Invalid selection. (enter)")


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
    print("1) Set SOURCE (manual / browse)")
    print("2) Cleanup trash (.DS_Store / ._*)")
    print("3) Generate quality report (color + CSV)")
    print("4) Duplicates report (same name + same size)")
    print("5) Review duplicates (interactive delete)")
    print("6) Variants report (same name, different sizes)")
    print("7) Review variants (interactive delete)")
    print("8) Exit")

def is_sample_path(p: Path) -> bool:
    """
    True if path is a sample file or is contained inside a Sample/Samples directory.
    Works for files returned by collect_media() (which are files).
    """
    try:
        # Any parent folder named "sample" or "samples"
        if any(part.lower() in SAMPLE_DIR_NAMES for part in p.parts):
            return True
    except Exception:
        pass

    # If filename itself hints sample
    return looks_like_sample_file(p)

def main():
    source: Optional[Path] = None
    last_quality_rows: List[Dict[str, str]] = []
    last_dupes: Dict[Tuple[str, int], List[Path]] = {}
    last_variants: Dict[str, List[Path]] = {}

    while True:
        clear_screen()
        print_menu(source)
        choice = input("\nEnter number: ").strip()

        if choice == "1":
            clear_screen()
            print("Set SOURCE\n")
            print("1) Manual path")
            print("2) Browse (seek)")
            sub = input("\nSelect: ").strip()

            if sub == "1":
                raw = input("Enter SOURCE path: ").strip()
                p = Path(raw).expanduser().resolve()
                if p.exists() and p.is_dir():
                    source = p
                else:
                    input("Invalid directory. (enter)")
            elif sub == "2":
                picked = browse_for_directory(Path.cwd())
                if picked:
                    source = picked
            else:
                input("Invalid selection. (enter)")


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
            files_all = collect_media(source)

            # filter out sample content
            files = [p for p in files_all if not is_sample_path(p)]

            skipped = len(files_all) - len(files)
            print(f"Collected: {len(files_all)} media files | Skipping samples: {skipped} | Reporting: {len(files)}")

            entries = []  # (severity, color, label_text, tag, filename, rowdict)
            counts = {"RED": 0, "YELLOW": 0, "BLUE": 0, "GREEN": 0, "INFO": 0}

            total_files = len(files)

            for idx, p in enumerate(files, start=1):
                progress(idx, total_files, every=1, prefix="Analyzing: ")

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

                _label_short, col = classify(info)
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

            # print report
            for _, col, label_text, tag, name, _row in entries:
                print(colorize(f"[{label_text:5}]", col), f"{tag} | {name}")

            # footer
            total = len(entries)
            print("\n" + "-" * 60)
            print(
                f"Total: {total} | "
                f"{colorize('RED ' + str(counts.get('RED',0)), C_RED)} | "
                f"{colorize('YELLOW ' + str(counts.get('YELLOW',0)), C_YELLOW)} | "
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
            if not source:
                input("Set SOURCE first. (enter)")
                continue
            files = collect_media(source)
            variants = group_variants_by_name(files)
            last_variants = variants

            out_csv = (Path.cwd() / "reports" / "variants_by_name.csv").resolve()
            write_variants_csv(variants, out_csv)

            input(f"Found {len(variants)} variant groups.\nCSV: {out_csv}\n(enter)")

        elif choice == "7":
            if not last_variants:
                input("Run variants report first (option 6). (enter)")
                continue
            interactive_variant_review(last_variants)

        elif choice == "8":
            return


        else:
            input("Invalid choice. (enter)")

if __name__ == "__main__":
    main()

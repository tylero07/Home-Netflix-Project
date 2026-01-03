#!/usr/bin/env python3
"""
Rename messy media filenames into a consistent format:
  Title (Year).ext

Also renames matching sidecars (subtitles, .nfo, etc.) using the same base name.
Menu-driven UI for easier navigation.
"""

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import os

VALID_VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".m2ts"}
SIDECAR_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".nfo"}

KNOWN_JUNK_NAMES = {
    "480p","720p","1080p","2160p","4k","uhd",
    "x264","x265","h264","h265","hevc",
    "bluray","bdrip","brrip","remux","web","webrip","webdl","hdrip","dvdrip","hdtv",
    "hdr","hdr10","hdr10+","dv","dolbyvision",
    "aac","ac3","eac3","dd","ddp","dts","dtshd","truehd","atmos",
    "5.1","7.1","2.0",
    "yify","rarbg",
    "unrated","proper","repack",
}

PROPER_YEAR_FORMATS = re.compile(r"^(19\d{2}|20\d{2})$")
PARSE_ON = re.compile(r"[.\-_]+")
CURRENT_YEAR = datetime.now().year


@dataclass
class RenameItem:
    original: Path
    proposed: Path
    action: str   # rename_video / rename_sidecar
    title: str
    year: str


def is_year(tok: str) -> bool:
    if not PROPER_YEAR_FORMATS.match(tok):
        return False
    y = int(tok)
    return 1900 <= y <= CURRENT_YEAR


def smart_title(tokens: List[str]) -> str:
    out = []
    for t in tokens:
        if re.fullmatch(r"[ivxlcdm]+", t.lower()):
            out.append(t.upper())
        else:
            out.append(t[:1].upper() + t[1:].lower() if t else t)
    return " ".join(out).strip()


def parse_base_name(stem: str) -> tuple[str, Optional[str]]:
    raw_tokens = [t for t in PARSE_ON.split(stem) if t]
    title_tokens: List[str] = []
    year: Optional[str] = None

    for tok in raw_tokens:
        low = tok.lower()

        # Skip junk once we've started collecting a title
        if low in KNOWN_JUNK_NAMES and title_tokens:
            continue

        # Treat token as year only if we've already got title tokens
        if is_year(tok) and title_tokens:
            year = tok
            break

        if low not in KNOWN_JUNK_NAMES:
            title_tokens.append(tok)

    title = smart_title(title_tokens) if title_tokens else stem
    return title, year


def create_new_base(file: Path) -> str:
    title, year = parse_base_name(file.stem)
    if year:
        return f"{title} ({year})"
    return title


def iter_video_files(root: Path, recursive: bool) -> List[Path]:
    it = root.rglob("*") if recursive else root.iterdir()
    return [p for p in it if p.is_file() and p.suffix.lower() in VALID_VIDEO_EXTENSIONS]


def resolve_collision(target: Path) -> Path:
    """If target already exists, append ' - dupN' to avoid overwriting."""
    if not target.exists():
        return target
    base = target.with_suffix("")
    ext = target.suffix
    for i in range(1, 1000):
        cand = Path(f"{base} - dup{i}{ext}")
        if not cand.exists():
            return cand
    raise RuntimeError(f"Too many collisions for {target}")


def find_sidecars(video_file: Path) -> List[Path]:
    """
    Sidecars share the same starting stem as the video.
    Examples:
      Movie.Name.2012.mkv
      Movie.Name.2012.srt
      Movie.Name.2012.eng.srt
      Movie.Name.2012.nfo
    """
    parent = video_file.parent
    stem = video_file.stem
    out: List[Path] = []

    for p in parent.iterdir():
        if not p.is_file():
            continue
        if not p.name.startswith(stem):
            continue
        suffixes = [s.lower() for s in p.suffixes]
        if any(s in SIDECAR_EXTENSIONS for s in suffixes):
            out.append(p)

    return out


def build_rename_plan(video_files: List[Path]) -> List[RenameItem]:
    plan: List[RenameItem] = []

    for vid in video_files:
        new_base = create_new_base(vid)

        proposed_vid = vid.with_name(new_base + vid.suffix.lower())
        if proposed_vid.name == vid.name:
            continue

        proposed_vid = resolve_collision(proposed_vid)
        title, year = parse_base_name(vid.stem)

        plan.append(RenameItem(
            original=vid,
            proposed=proposed_vid,
            action="rename_video",
            title=title,
            year=year or ""
        ))

        for sc in find_sidecars(vid):
            tail = sc.name[len(vid.stem):]  # keep ".eng.srt" etc intact
            proposed_sc = sc.with_name(new_base + tail)
            if proposed_sc.name == sc.name:
                continue
            proposed_sc = resolve_collision(proposed_sc)

            plan.append(RenameItem(
                original=sc,
                proposed=proposed_sc,
                action="rename_sidecar",
                title=title,
                year=year or ""
            ))

    return plan


def write_plan_csv(plan: List[RenameItem], csv_path: Path) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["action", "original", "proposed", "title", "year"])
        for item in plan:
            w.writerow([item.action, str(item.original), str(item.proposed), item.title, item.year])


def apply_plan(plan: List[RenameItem]) -> None:
    sidecars = [x for x in plan if x.action == "rename_sidecar"]
    videos = [x for x in plan if x.action == "rename_video"]

    for item in sidecars + videos:
        item.original.rename(item.proposed)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_menu(cwd: Path) -> None:
    print("\nCurrent directory:")
    print(f"  {cwd}\n")
    print("Choose an action:")
    print("  1) List directory")
    print("  2) Change directory")
    print("  3) Scan and Prep")
    print("  4) Show planned renames")
    print("  5) Apply renames")
    print("  6) Exit")


def interactive_menu(start_dir: Path) -> None:
    cwd = start_dir.resolve()
    last_plan: List[RenameItem] = []
    last_report_path = Path("rename_plan.csv").resolve()

    while True:
        print_menu(cwd)
        choice = input("Enter number: ").strip()
        clear_screen()

        if choice == "1":
            for p in sorted(cwd.iterdir()):
                print(p.name + ("/" if p.is_dir() else ""))

        elif choice == "2":
            target = input("Enter directory name or path: ").strip()
            new_dir = (cwd / target).resolve()
            if new_dir.exists() and new_dir.is_dir():
                cwd = new_dir
            else:
                print("Invalid directory.")

        elif choice == "3":
            videos = iter_video_files(cwd, recursive=True)
            videos.sort()
            last_plan = build_rename_plan(videos)
            write_plan_csv(last_plan, last_report_path)
            print(f"Scan complete. Planned renames: {len(last_plan)}")
            print(f"CSV written to: {last_report_path}")

        elif choice == "4":
            if not last_plan:
                print("No scan results yet. Run Scan first.")
            else:
                for item in last_plan[:30]:
                    print(f"{item.original.name} → {item.proposed.name}")
                if len(last_plan) > 30:
                    print(f"... ({len(last_plan) - 30} more)")

        elif choice == "5":
            if not last_plan:
                print("Nothing to apply. Run Scan first.")
                continue
            confirm = input("Type 1 to confirm apply or 2 to cancel: ").strip()
            if confirm == "1":
                apply_plan(last_plan)
                last_plan = []
                print("Renames applied.")
            else:
                print("Cancelled.")

        elif choice == "6":
            print("Exiting.")
            break

        else:
            print("Invalid choice.")


if __name__ == "__main__":
    interactive_menu(Path.cwd())

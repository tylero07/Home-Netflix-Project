#!/usr/bin/env python3
"""
Movie sorter (menu UI)

Sorts movies into:
  DEST/movies/<LETTER>/<Title (Year)>/<Title (Year)>.ext

- Skips anything under BONUS_FEATURES/
- Skips TV episodes (SxxExx)
- If video is inside a "single-movie folder" (video + sidecars + BONUS_FEATURES only),
  moves/renames the whole folder as the movie folder.
- Dry-run by default; writes CSV plan; APPLY only on explicit confirmation.
"""
import pydoc
import csv
import re
from dataclasses import dataclass
from pathlib import Path
import os
from typing import Iterator, Iterable, Set, List, Tuple

def walk_files(root: Path, *, ignore_dir_names: Iterable[str] = ()) -> Iterator[Path]:
    """
    Walk ALL nested dirs under root (top-down) and yield file Paths.
    Only prunes directories whose name matches ignore_dir_names (case-insensitive).
    """
    root = Path(root)
    ignore: Set[str] = {n.lower() for n in ignore_dir_names}

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # prune dirs we want to ignore (but DO NOT prune "looks-good" dirs)
        dirnames[:] = [d for d in dirnames if d.lower() not in ignore]

        for fn in filenames:
            yield Path(dirpath) / fn

IGNORE_DIRS = {"BONUS_FEATURES", ".git", "__pycache__", "reports"}
VALID_VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".m2ts"}
SIDECAR_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".nfo"}

BONUS_DIR_NAME = "bonus_features"  # case-insensitive match
TV_EP_RE = re.compile(r"\bS\d{1,2}E\d{1,2}\b", re.IGNORECASE)


# -------------------- Core planner types --------------------

@dataclass
class MoveItem:
    original: Path
    proposed: Path
    action: str  # mkdir / move_video / move_sidecar / move_folder


# -------------------- Helpers --------------------

def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")

C_RESET  = "\033[0m"
C_GREEN  = "\033[32m"
C_RED    = "\033[31m"
C_YELLOW = "\033[33m"

def colorize(text: str, color: str) -> str:
    return f"{color}{text}{C_RESET}"

def status_line(label: str, path: Path | None, ok: bool, warn: bool = False) -> str:
    if not path:
        return f"{label}: (not set)"
    s = str(path)
    if ok:
        return f"{label}: {colorize(s, C_GREEN)}"
    if warn:
        return f"{label}: {colorize(s, C_YELLOW)}"
    return f"{label}: {colorize(s, C_RED)}"

def is_tv_episode_name(name: str) -> bool:
    return bool(TV_EP_RE.search(name))


def is_in_bonus_features(path: Path) -> bool:
    return any(part.lower() == BONUS_DIR_NAME for part in path.parts)


def bucket_letter(title_base: str) -> str:
    for ch in title_base:
        if ch.isalpha():
            return ch.upper()
        if ch.isdigit():
            return "#"
    return "_"


def resolve_collision_path(target: Path) -> Path:
    """If file target exists, append ' - dupN' before extension."""
    if not target.exists():
        return target
    base = target.with_suffix("")
    ext = target.suffix
    for i in range(1, 1000):
        cand = Path(f"{base} - dup{i}{ext}")
        if not cand.exists():
            return cand
    raise RuntimeError(f"Too many file collisions for {target}")


def resolve_collision_dir(target: Path) -> Path:
    """If folder target exists, append ' - dupN'."""
    if not target.exists():
        return target
    for i in range(1, 1000):
        cand = Path(str(target) + f" - dup{i}")
        if not cand.exists():
            return cand
    raise RuntimeError(f"Too many folder collisions for {target}")


def iter_video_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in walk_files(root, ignore_dir_names=IGNORE_DIRS):
        if p.is_file() and p.suffix.lower() in VALID_VIDEO_EXTENSIONS:
            out.append(p)
    return sorted(out)


def is_single_movie_folder(folder: Path) -> bool:
    if not folder.is_dir():
        return False

    videos = [
        p for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in VALID_VIDEO_EXTENSIONS
        and not is_tv_episode_name(p.name)
    ]
    if len(videos) != 1:
        return False

    for p in folder.iterdir():
        if p == videos[0]:
            continue

        if p.is_dir() and p.name.lower() == BONUS_DIR_NAME:
            continue

        if p.is_file():
            suffixes = {s.lower() for s in p.suffixes}
            if suffixes & SIDECAR_EXTENSIONS:
                continue

        return False

    return True


def find_sidecars(video_file: Path) -> List[Path]:
    parent = video_file.parent
    stem = video_file.stem
    out: List[Path] = []
    for p in parent.iterdir():
        if not p.is_file():
            continue
        if is_in_bonus_features(p):
            continue
        if not p.name.startswith(stem):
            continue
        suffixes = [s.lower() for s in p.suffixes]
        if any(s in SIDECAR_EXTENSIONS for s in suffixes):
            out.append(p)
    return out


# ---- Replace this later by importing your normalizer's create_new_base ----
def create_new_base(file: Path) -> str:
    # Assumes already normalized: "Title (Year).ext"
    return file.stem
# ------------------------------------------------------------------------


def build_sort_plan(source_root: Path, dest_root: Path) -> List[MoveItem]:
    plan: List[MoveItem] = []

    videos = iter_video_files(source_root, recursive=True)
    videos.sort()

    seen_movie_folders = set()

    for vid in videos:
        parent = vid.parent

        # Single-movie folder: move the folder as the movie directory
        if is_single_movie_folder(parent):
            if str(parent) in seen_movie_folders:
                continue
            seen_movie_folders.add(str(parent))

            base = create_new_base(vid)
            letter = bucket_letter(base)

            dest_movie_dir = dest_root / "movies" / letter / base
            dest_movie_dir = resolve_collision_dir(dest_movie_dir)

            plan.append(MoveItem(
                original=parent,
                proposed=dest_movie_dir,
                action="move_folder"
            ))
            continue

        # Loose movie: mkdir + move file + move sidecars
        base = create_new_base(vid)
        letter = bucket_letter(base)

        movie_dir = dest_root / "movies" / letter / base
        plan.append(MoveItem(original=movie_dir, proposed=movie_dir, action="mkdir"))

        proposed_vid = resolve_collision_path(movie_dir / (base + vid.suffix.lower()))
        plan.append(MoveItem(original=vid, proposed=proposed_vid, action="move_video"))

        for sc in find_sidecars(vid):
            tail = sc.name[len(vid.stem):]
            proposed_sc = resolve_collision_path(movie_dir / (base + tail))
            plan.append(MoveItem(original=sc, proposed=proposed_sc, action="move_sidecar"))

    # De-dupe mkdir entries
    seen = set()
    deduped: List[MoveItem] = []
    for item in plan:
        if item.action == "mkdir":
            key = str(item.proposed)
            if key in seen:
                continue
            seen.add(key)
        deduped.append(item)

    return deduped


def write_sort_csv(plan: List[MoveItem], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["action", "original", "proposed"])
        for item in plan:
            w.writerow([item.action, str(item.original), str(item.proposed)])


def apply_sort_plan(plan: List[MoveItem]) -> None:
    # mkdirs first
    for item in plan:
        if item.action == "mkdir":
            Path(item.proposed).mkdir(parents=True, exist_ok=True)

    # folders next
    folders = [x for x in plan if x.action == "move_folder"]
    for item in folders:
        item.proposed.parent.mkdir(parents=True, exist_ok=True)
        item.original.rename(item.proposed)

    # then sidecars + videos
    sidecars = [x for x in plan if x.action == "move_sidecar"]
    videos = [x for x in plan if x.action == "move_video"]
    for item in sidecars + videos:
        item.proposed.parent.mkdir(parents=True, exist_ok=True)
        item.original.rename(item.proposed)


# -------------------- Menu / UI --------------------

def count_dir_stats(dirpath: Path) -> Tuple[int, int]:
    """(subdir_count, video_count) non-recursive for speed."""
    subdirs = 0
    videos = 0
    for p in dirpath.iterdir():
        if p.is_dir():
            subdirs += 1
        elif p.is_file() and p.suffix.lower() in VALID_VIDEO_EXTENSIONS:
            videos += 1
    return subdirs, videos


def list_dirs_numbered(cwd: Path) -> List[Path]:
    dirs = sorted([p for p in cwd.iterdir() if p.is_dir()])
    print("\nFolders:")
    print("  0) .. (up one level)")
    for i, d in enumerate(dirs, start=1):
        subdir_count, video_count = count_dir_stats(d)
        print(f"  {i}) {d.name}/ [{subdir_count} dirs | {video_count} videos]")
    return dirs


def select_directory(start: Path) -> Path:
    cwd = start.resolve()
    while True:
        clear_screen()
        print(f"Current: {cwd}")
        dirs = list_dirs_numbered(cwd)
        print("\nOptions: r=refresh, m=manual path, b=back/confirm")
        sel = input("Select #: ").strip().lower()

        if sel == "b":
            return cwd
        if sel == "r":
            continue
        if sel == "0":
            if cwd.parent != cwd:
                cwd = cwd.parent
            continue
        if sel == "m":
            raw = input("Enter absolute or relative path: ").strip()
            maybe = (cwd / raw).expanduser().resolve() if not Path(raw).is_absolute() else Path(raw).expanduser().resolve()
            if maybe.exists() and maybe.is_dir():
                cwd = maybe
            else:
                input(f"Invalid dir: {maybe} (enter)")
            continue

        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(dirs):
                cwd = dirs[idx - 1]
            else:
                input("Invalid selection. (enter)")
        else:
            input("Invalid input. (enter)")


def validate_paths(source: Path, dest: Path) -> List[str]:
    issues = []
    if not source.exists() or not source.is_dir():
        issues.append("SOURCE does not exist or is not a directory.")
    if not dest.exists() or not dest.is_dir():
        issues.append("DEST does not exist or is not a directory.")
    # prevent dest inside source (or same)
    try:
        src = source.resolve()
        dst = dest.resolve()
        if dst == src:
            issues.append("DEST cannot be the same as SOURCE.")
        if dst.is_relative_to(src):
            issues.append("DEST cannot be inside SOURCE (would re-ingest moved files).")
    except Exception:
        # is_relative_to may fail on older python / weird paths
        pass
    return issues


def pager(text: str) -> None:
    """
    Use system pager (like 'less') when available.
    Controls: q to quit, arrows/pgup/pgdn/space to scroll.
    """
    pydoc.pager(text)



def plan_to_lines(plan: List[MoveItem], changes_only: bool) -> List[str]:
    out = []
    for item in plan:
        if changes_only and item.action == "mkdir":
            continue
        out.append(f"[{item.action}] {item.original} -> {item.proposed}")
    return out


def print_menu(source: Path | None, dest: Path | None) -> None:
    # Validity checks (only if both set)
    src_ok = bool(source and source.exists() and source.is_dir())
    dst_ok = bool(dest and dest.exists() and dest.is_dir())

    pair_ok = False
    pair_warn = False

    if src_ok and dst_ok and source and dest:
        issues = validate_paths(source, dest)
        if not issues:
            pair_ok = True
        else:
            # treat as "warn" if the only problem is something like dest inside source
            pair_warn = True

    print("Movie Sorter Menu\n")

    # if individually ok but pair invalid, show yellow to nudge you
    src_color_ok = src_ok and (pair_ok or not pair_warn)
    dst_color_ok = dst_ok and (pair_ok or not pair_warn)

    print(status_line("SOURCE", source, src_color_ok, warn=(src_ok and pair_warn)))
    print(status_line("DEST  ", dest, dst_color_ok, warn=(dst_ok and pair_warn)))
    print()

    print("1) Set SOURCE (browse)")
    print("2) Set DEST (browse)")
    print("3) Scan (dry-run) + write CSV plan")
    print("4) View plan (changes-only / all) in pager")
    print("5) Apply plan (moves folders/files)")
    print("6) Exit")



def interactive_menu() -> None:
    cwd = Path.cwd()
    source: Path = Path()
    dest: Path = Path()
    last_plan: List[MoveItem] = []
    last_report_path: Path = (cwd / "sort_plan.csv").resolve()

    while True:
        clear_screen()
        print_menu(source if str(source) else None, dest if str(dest) else None)  # type: ignore
        choice = input("\nEnter number: ").strip()

        if choice == "1":
            source = select_directory(cwd)

        elif choice == "2":
            dest = select_directory(cwd)

        elif choice == "3":
            if not str(source) or not str(dest):
                input("Set SOURCE and DEST first. (enter)")
                continue

            issues = validate_paths(source, dest)
            if issues:
                clear_screen()
                print("Path issues:\n")
                for x in issues:
                    print(f"- {x}")
                input("\nFix and try again. (enter)")
                continue

            last_plan = build_sort_plan(source, dest)
            write_sort_csv(last_plan, last_report_path)
            input(f"Scan complete. Items in plan: {len(last_plan)}\nCSV: {last_report_path}\n(enter)")

        elif choice == "4":
            if not last_plan:
                input("No plan yet. Run Scan first. (enter)")
                continue
            clear_screen()
            mode = input("View (1) changes-only or (2) all entries? ").strip()
            changes_only = (mode != "2")
            lines = plan_to_lines(last_plan, changes_only=changes_only)
            pager("\n".join(lines) + "\n")

        elif choice == "5":
            if not last_plan:
                input("Nothing to apply. Run Scan first. (enter)")
                continue

            issues = validate_paths(source, dest)
            if issues:
                clear_screen()
                print("Path issues:\n")
                for x in issues:
                    print(f"- {x}")
                input("\nFix and try again. (enter)")
                continue

            clear_screen()
            print(f"About to APPLY {len(last_plan)} actions.")
            print(f"SOURCE: {source}")
            print(f"DEST:   {dest}")
            confirm = input("\nType YES to confirm: ").strip()
            if confirm == "YES":
                apply_sort_plan(last_plan)
                last_plan = []
                input("Applied. (enter)")
            else:
                input("Cancelled. (enter)")

        elif choice == "6":
            clear_screen()
            print("Exiting.")
            return

        else:
            input("Invalid choice. (enter)")


if __name__ == "__main__":
    interactive_menu()

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
import os
from typing import Iterator, Iterable, Set, List, Optional, Dict, Tuple
import subprocess

def has_uchg(path: Path) -> bool:
    """Detect macOS user immutable flag (uchg) via ls -lO output."""
    try:
        out = subprocess.check_output(
            ["ls", "-lO", str(path)],
            text=True,
            stderr=subprocess.DEVNULL
        )
        return "uchg" in out.split()
    except Exception:
        return False

def sudo_unlock(path: Path) -> bool:
    """
    Attempt to remove uchg/schg flags using sudo chflags.
    Returns True if command ran successfully, False otherwise.
    """
    try:
        # This will prompt for sudo password in the terminal if needed.
        subprocess.check_call(["sudo", "chflags", "nouchg,noschg", str(path)])
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        # chflags not found (non-mac environment)
        return False


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
TRAILING_COPY_RE = re.compile(r"""\s*(?:\(\d+\)|\d+|copy|dup\d*)\s*$""", re.IGNORECASE)
VALID_VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".m2ts"}
SIDECAR_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".nfo"}
MEDIA_EXTS = {e.lower() for e in VALID_VIDEO_EXTENSIONS}
SIDECAR_EXTS = {e.lower() for e in SIDECAR_EXTENSIONS}
BONUS_DIR_NAME = "BONUS_FEATURES" 
KNOWN_JUNK_NAMES = {
    "480p","720p","1080p","2160p","4k","uhd",
    "x264","x265","h264","h265","hevc",
    "bluray","bdrip","brrip","remux","web","webrip","webdl","hdrip","dvdrip","hdtv",
    "hdr","hdr10","hdr10+","dv","dolbyvision",
    "aac","ac3","eac3","dd","ddp","dts","dtshd","truehd","atmos",
    "5.1","7.1","2.0",
    "yify","rarbg",
    "unrated","proper","repack", "dl", "web-dl", "webrip", "hdrip", "brrip", "dvdrip",  
    "copy", "sample",
    "jyk", "rarbg", "ettv", "evo"
}

PROPER_YEAR_FORMATS = re.compile(r"^(19\d{2}|20\d{2})$")
PARSE_ON = re.compile(r"[.\-_\s\[\]\(\)\{\};:,]+")
CURRENT_YEAR = datetime.now().year
YEAR_IN_TOKEN = re.compile(r"(19\d{2}|20\d{2})")


@dataclass
class RenameItem:
    original: Path
    proposed: Path
    action: str   # rename_video / rename_sidecar
    title: str
    year: str

def extract_year(tok: str) -> Optional[str]:
    m = YEAR_IN_TOKEN.search(tok)
    if not m:
        return None
    y = int(m.group(1))
    if 1900 <= y <= CURRENT_YEAR:
        return m.group(1)
    return None

def is_year(tok: str) -> bool:
    if not PROPER_YEAR_FORMATS.match(tok):
        return False
    y = int(tok)
    return 1900 <= y <= CURRENT_YEAR

SPACE_RE = re.compile(r"\s+")

def normalized_name_for_ext(name: str) -> str:
    """
    Normalize filename so extension checks still work on 'file.mkv 2', 'file.mp4 (1)', etc.
    """
    n = name.strip()
    # If it ends with a normal extension already, fine
    lower = n.lower()
    for ext in MEDIA_EXTS | SIDECAR_EXTS:
        if lower.endswith(ext):
            return n
    
    # Otherwise try stripping trailing " 2", "(2)", "copy", "dup1", etc then re-check
    stripped = TRAILING_COPY_RE.sub("", n).strip()
    lower2 = stripped.lower()
    for ext in MEDIA_EXTS | SIDECAR_EXTS:
        if lower2.endswith(ext):
            return stripped

    return n  # fallback (won't match)

def iter_media_files(root: Path) -> List[Path]:
    out: List[Path] = []
    for p in walk_files(root, ignore_dir_names=IGNORE_DIRS):
        if not p.is_file():
            continue

        nn = normalized_name_for_ext(p.name).lower()
        if any(nn.endswith(ext) for ext in (MEDIA_EXTS | SIDECAR_EXTS)):
            out.append(p)

    return sorted(out)

def normalize_spaces(s: str) -> str:
    """Collapse multiple spaces into one and strip ends."""
    return SPACE_RE.sub(" ", s).strip()

def smart_title(tokens: List[str]) -> str:
    out = []
    for t in tokens:
        if re.fullmatch(r"[ivxlcdm]+", t.lower()):
            out.append(t.upper())
        else:
            out.append(t[:1].upper() + t[1:].lower() if t else t)
    # collapse any accidental multi-space
    return re.sub(r"\s+", " ", " ".join(out)).strip()

def is_same_file(a: Path, b: Path) -> bool:
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError:
        # safe fallback (not perfect across mounts)
        return a.resolve() == b.resolve()

def parse_base_name(stem: str) -> tuple[str, Optional[str]]:
    raw_tokens = [t for t in PARSE_ON.split(stem) if t]
    title_tokens: List[str] = []
    year: Optional[str] = None

    for tok in raw_tokens:
        low = tok.lower()

        # skip junk after title has started
        if low in KNOWN_JUNK_NAMES and title_tokens:
            continue

        y = extract_year(tok)
        if y and title_tokens:
            year = y
            break

        if low not in KNOWN_JUNK_NAMES:
            title_tokens.append(tok)

    title = smart_title(title_tokens) if title_tokens else stem
    return title, year


def iter_files_for_rename(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in walk_files(root, ignore_dir_names=IGNORE_DIRS):
        if p.is_file():
            out.append(p)
    return sorted(out)


def is_in_bonus_features(path: Path) -> bool:
    return any(part.lower() == BONUS_DIR_NAME.lower() for part in path.parts)


def key_path(p: Path) -> str:
    # case-insensitive key good for macOS default volumes
    return str(p).casefold()

def resolve_collision(target: Path, reserved: set[str]) -> Path:
    if (not target.exists()) and (key_path(target) not in reserved):
        reserved.add(key_path(target))
        return target

    base = target.with_suffix("")
    ext = target.suffix
    for i in range(1, 1000):
        cand = Path(f"{base} - dup{i}{ext}")
        if (not cand.exists()) and (key_path(cand) not in reserved):
            reserved.add(key_path(cand))
            return cand

    raise RuntimeError(f"Too many collisions for {target}")



def find_sidecars(video_file: Path) -> List[Path]:
    parent = video_file.parent
    stem = Path(normalized_name_for_ext(video_file.name)).stem
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

def iter_video_files(root: Path) -> List[Path]:
    """
    Recursively find video files under root, respecting IGNORE_DIRS.
    """
    out: List[Path] = []
    for p in walk_files(root, ignore_dir_names=IGNORE_DIRS):
        if p.is_file() and p.suffix.lower() in VALID_VIDEO_EXTENSIONS:
            out.append(p)
    return sorted(out)



def build_rename_plan(video_files: List[Path], include_noops: bool = False) -> List[RenameItem]:
    plan: List[RenameItem] = []

    # Reserve targets during planning so two files in the same scan
    # don't both choose the same proposed name.
    reserved: set[str] = set()

    def key_path(p: Path) -> str:
        # macOS default volumes are usually case-insensitive
        return str(p).casefold()

    def resolve_collision_reserved(target: Path) -> Path:
        # If nothing exists on disk AND we haven't already claimed it in this plan, use it.
        if (not target.exists()) and (key_path(target) not in reserved):
            reserved.add(key_path(target))
            return target

        base = target.with_suffix("")
        ext = target.suffix
        for i in range(1, 1000):
            cand = Path(f"{base} - dup{i}{ext}")
            if (not cand.exists()) and (key_path(cand) not in reserved):
                reserved.add(key_path(cand))
                return cand

        raise RuntimeError(f"Too many collisions for {target}")

    for vid in video_files:
        norm_name = normalized_name_for_ext(vid.name)
        norm_path = Path(norm_name)

        # parse based on normalized stem (handles Transformers.Age.of... and mkv 2 cases)
        title, year = parse_base_name(norm_path.stem)
        new_base = f"{title} ({year})" if year else title

        # use normalized suffixes (handles .eng.srt etc)
        effective_suffix = effective_extension_from_name(norm_name)
        proposed_vid = vid.with_name(new_base + effective_suffix)


        # If the proposed path "exists" but it's actually the same file
        # (common on case-insensitive filesystems), treat as NOOP.
        if proposed_vid.exists() and is_same_file(vid, proposed_vid):
            if include_noops:
                plan.append(RenameItem(
                    original=vid,
                    proposed=proposed_vid,
                    action="noop_video",
                    title=title,
                    year=year or ""
                ))
            # still reserve it so nothing else plans to rename into it
            reserved.add(key_path(proposed_vid))
            continue

        # If name is already exactly the same, it's a NOOP.
        if proposed_vid.name == vid.name:
            if include_noops:
                plan.append(RenameItem(
                    original=vid,
                    proposed=proposed_vid,
                    action="noop_video",
                    title=title,
                    year=year or ""
                ))
            reserved.add(key_path(proposed_vid))
            continue

        # If a DIFFERENT file already occupies the desired target, decide what you want to do.
        # Option A (recommended): SKIP and report it, instead of auto-dup'ing silently.
        if proposed_vid.exists() and not is_same_file(vid, proposed_vid):
            if include_noops:
                plan.append(RenameItem(
                    original=vid,
                    proposed=proposed_vid,
                    action="collision_skip",
                    title=title,
                    year=year or ""
                ))
            # reserve anyway so we don't create a pile of dup targets around it
            reserved.add(key_path(proposed_vid))
            continue

        # Otherwise: reserve-aware collision resolution (disk + in-plan)
        proposed_vid = resolve_collision_reserved(proposed_vid)

        plan.append(RenameItem(
            original=vid,
            proposed=proposed_vid,
            action="rename_video",
            title=title,
            year=year or ""
        ))

        # Sidecars: keep pairing and use the SAME reserved collision logic
        for sc in find_sidecars(vid):
            video_stem_norm = Path(normalized_name_for_ext(vid.name)).stem
            tail = sc.name[len(video_stem_norm):]

            proposed_sc = sc.with_name(new_base + tail)

            if proposed_sc.name == sc.name:
                reserved.add(key_path(proposed_sc))
                continue

            if proposed_sc.exists() and is_same_file(sc, proposed_sc):
                reserved.add(key_path(proposed_sc))
                if include_noops:
                    plan.append(RenameItem(
                        original=sc,
                        proposed=proposed_sc,
                        action="noop_sidecar",
                        title=title,
                        year=year or ""
                    ))
                continue

            # If a different file already exists at the target name, skip (don’t dup silently)
            if proposed_sc.exists() and not is_same_file(sc, proposed_sc):
                if include_noops:
                    plan.append(RenameItem(
                        original=sc,
                        proposed=proposed_sc,
                        action="collision_skip_sidecar",
                        title=title,
                        year=year or ""
                    ))
                reserved.add(key_path(proposed_sc))
                continue

            proposed_sc = resolve_collision_reserved(proposed_sc)

            plan.append(RenameItem(
                original=sc,
                proposed=proposed_sc,
                action="rename_sidecar",
                title=title,
                year=year or ""
            ))

    return plan


def effective_extension_from_name(name: str) -> str:
    """
    Return the *real* media/sidecar extension from the end of a filename.
    Works even if the filename contains many dots.
    """
    lower = name.lower().strip()

    # prefer longest matches first (handles .eng.srt, .en.srt, etc)
    candidates = sorted((MEDIA_EXTS | SIDECAR_EXTS), key=len, reverse=True)

    for ext in candidates:
        if lower.endswith(ext):
            return ext
    return Path(name).suffix.lower()  # fallback

def write_plan_csv(plan: List[RenameItem], csv_path: Path) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["action", "original", "proposed", "title", "year"])
        for item in plan:
            w.writerow([item.action, str(item.original), str(item.proposed), item.title, item.year])


def apply_plan(plan: List[RenameItem]) -> None:
    sidecars = [x for x in plan if x.action == "rename_sidecar"]
    videos   = [x for x in plan if x.action == "rename_video"]

    auto_unlock = False  # if True, we will run sudo_unlock automatically on locked files

    for item in sidecars + videos:
        while True:
            try:
                item.original.rename(item.proposed)
                break  # success → next file

            except PermissionError:
                locked = has_uchg(item.original)

                print("\nPermissionError while renaming:")
                print(f"  FROM: {item.original}")
                print(f"  TO:   {item.proposed}")
                print(f"  Immutable (uchg): {locked}")

                # If it's locked and auto-unlock is enabled, try it immediately.
                if locked and auto_unlock:
                    print("\nAuto-unlock enabled → running: sudo chflags nouchg,noschg ...")
                    ok = sudo_unlock(item.original)
                    if ok and not has_uchg(item.original):
                        print("Unlocked. Retrying rename...\n")
                        continue
                    print("Auto-unlock failed (or still locked). Falling back to prompt.\n")

                print("\nOptions:")
                print("  [Enter]  retry rename (after you fix it)")
                print("  s        skip this file")
                print("  q        quit apply")
                if locked:
                    print("  u        run sudo chflags nouchg,noschg on this file, then retry")
                    print("  U        enable auto-unlock for ALL locked files this run")

                choice = input("> ").strip()

                if choice.lower() == "s":
                    print("→ Skipped\n")
                    break

                if choice.lower() == "q":
                    print("Aborting apply.")
                    return

                if locked and choice == "u":
                    print("\nRunning sudo unlock...")
                    ok = sudo_unlock(item.original)
                    if not ok:
                        print("Unlock command failed/cancelled. (maybe wrong password or no sudo rights)")
                        continue
                    if has_uchg(item.original):
                        print("Still appears locked (uchg still set). Fix manually and press Enter to retry.")
                        continue
                    print("Unlocked. Retrying rename...\n")
                    continue

                if locked and choice == "U":
                    auto_unlock = True
                    print("Auto-unlock enabled for this run. Retrying rename...\n")
                    continue

                # Enter (or anything else) → just retry
                print("Retrying...\n")

            except Exception as e:
                print(f"\nUnexpected error on {item.original}: {e}")
                print("Skipping.\n")
                break



def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

import shutil
import subprocess

def build_plan_preview(plan: List[RenameItem]) -> str:
    lines = []
    for i, item in enumerate(plan, start=1):
        lines.append(f"{i:5d}. {item.action:13s}  {item.original.name}  ->  {item.proposed.name}")
    return "\n".join(lines)

def show_in_pager(text: str) -> None:
    """
    Show text in a pager like `less`, similar to `man`.
    Falls back to printing if no pager exists.
    """
    pager = os.environ.get("PAGER")

    if not pager:
        # Prefer less if available, else more, else None
        if shutil.which("less"):
            pager = "less -R"
        elif shutil.which("more"):
            pager = "more"
        else:
            pager = ""

    if not pager:
        print(text)
        input("\n(press Enter to return)")
        return

    # Use shell=True so "less -R" works as a single string command
    proc = subprocess.Popen(pager, shell=True, stdin=subprocess.PIPE, text=True)
    try:
        proc.communicate(text)
    except KeyboardInterrupt:
        pass

def print_menu(cwd: Path) -> None:
    print("\nCurrent directory:")
    print(f"  {cwd}\n")
    print("Choose an action:")
    print("  1) List directory/Easy Folder Change")
    print("  2) Change directory Using Manual Path")
    print("  3) Scan and Prep (Will prep for rename and generate csv plan)")
    print("  4) Show planned renames (uses man pages controls)")
    print("  5) Apply renames")
    print("  6) Exit")

def plan_changes_only(plan: List[RenameItem]) -> List[RenameItem]:
    return [x for x in plan if x.original.name != x.proposed.name]

def build_noop_preview(videos_scanned: List[Path]) -> str:
    # If you don't include no-ops in the plan, this shows a quick count-only fallback
    return f"Note: no-op items aren't currently stored in the plan.\nVideos scanned: {len(videos_scanned)}\n"

def count_dir_stats(dirpath: Path) -> tuple[int, int]:
    """
    Returns (subdir_count, video_file_count)
    Non-recursive on purpose — fast and safe.
    Skips directories we can't read (PermissionError).
    """
    subdirs = 0
    videos = 0

    try:
        it = list(dirpath.iterdir())
    except PermissionError:
        return 0, 0
    except FileNotFoundError:
        return 0, 0

    for p in it:
        try:
            if p.is_dir():
                subdirs += 1
            elif p.is_file() and p.suffix.lower() in VALID_VIDEO_EXTENSIONS:
                videos += 1
        except PermissionError:
            # Some entries inside might also be protected
            continue

    return subdirs, videos




def interactive_menu(start_dir: Path) -> None:
    cwd = start_dir.resolve()
    last_plan: List[RenameItem] = []
    last_report_path = Path("rename_plan.csv").resolve()

    while True:
        clear_screen()
        print_menu(cwd)
        choice = input("Enter number: ").strip()
        clear_screen()

        if choice == "1":
            while True:
                dirs = []
                try:
                    for p in cwd.iterdir():
                        try:
                            if p.is_dir():
                                dirs.append(p)
                        except PermissionError:
                            continue
                except PermissionError:
                    dirs = []


                print("\nFolders:")
                print("  0) .. (Go to parent directory/folder)")

                for i, d in enumerate(dirs, start=1):
                    subdir_count, video_count = count_dir_stats(d)
                    print(
                        f"  {i}) {d.name}/ "
                        f"[{subdir_count} dirs | {video_count} videos]"
                    )

                print("\nOptions:")
                print("  r) refresh")
                print("  b) back to main menu")

                sel = input("Select folder #: ").strip()

                if sel.lower() == "b":
                    break
                if sel == "r":
                    continue
                if sel == "0":
                    parent = cwd.parent
                    if parent != cwd:
                        cwd = parent
                    continue

                # allow manual path entry
                if not sel.isdigit():
                    maybe = (cwd / sel).resolve()
                    if maybe.exists() and maybe.is_dir():
                        cwd = maybe
                    else:
                        print("!!!!!!!!!!!!!!Invalid selection/path!!!!!!!!!!!!!!")
                    continue

                idx = int(sel)
                if 1 <= idx <= len(dirs):
                    cwd = dirs[idx - 1]
                else:
                    print("Invalid folder number.")


        elif choice == "2":
    
            while True:
                dirs = []
                try:
                    for p in cwd.iterdir():
                        try:
                            if p.is_dir():
                                dirs.append(p)
                        except PermissionError:
                            continue
                except PermissionError:
                    dirs = []


                print("\nFolders:")
                for i, d in enumerate(dirs, start=1):
                    subdir_count, video_count = count_dir_stats(d)
                    print(f"  {i}) {d.name}/ [{subdir_count} dirs | {video_count} videos]")

    
                raw = input("Enter directory path (absolute or relative) or b to go back to menu: ").strip()
                if not raw:
                    print("No path entered.")
                    continue
                maybe = (cwd / raw).expanduser().resolve() if not Path(raw).is_absolute() else Path(raw).expanduser().resolve()
                if raw == "b":
                    break
                if maybe.exists() and maybe.is_dir():
                    cwd = maybe
                else:
                    print("Invalid directory:", maybe)
                continue

        elif choice == "3":
            files = iter_media_files(cwd)
            last_plan = build_rename_plan(files)
            write_plan_csv(last_plan, last_report_path)
            write_plan_csv(last_plan, last_report_path)
            print(f"Scan complete. Planned renames: {len(last_plan)}")
            print(f"CSV written to: {last_report_path}")
            input("\n(press Enter to return)")


        elif choice == "4":
            if not last_plan:
                print("No scan results yet. Run Scan first.")
                input("Press Enter to return...")
                continue

            while True:
                clear_screen()
                print("View Options:")
                print("  1) Changes only")
                print("  2) All entries")
                print("  b) Back")
                sel = input("Choose: ").strip().lower()

                if sel == "b":
                    break

                if sel == "1":
                    filtered = plan_changes_only(last_plan)
                    preview = build_plan_preview(filtered)
                    show_in_pager(preview)
                    break

                if sel == "2":
                    preview = build_plan_preview(last_plan)
                    show_in_pager(preview)
                    break

                print("Invalid choice.")
                input("Press Enter...")


                

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

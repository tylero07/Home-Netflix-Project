#!/usr/bin/env python3
from __future__ import annotations
from typing import Optional, List, Tuple
import re, csv
from dataclasses import dataclass
from pathlib import Path
import shutil
import unicodedata


DEBUG_PARSE = True   # set False when done

# --- common release / scene junk tokens ---


# --- token-level junk matcher (single tokens after normalize_for_tokens/tokenize) ---
JUNK_WORDS = {
    # services / sources
    "nf", "netflix", "amzn", "amazon", "prime", "hulu", "dsnp", "disney", "itunes",

    # release types
    "web", "webdl", "webrip", "hdtv", "pdtv", "dvdrip", "bdrip", "brrip", "bluray", "remux",

    # quality / video
    "uhd", "hd", "sd", "4k", "2160p", "1080p", "720p", "480p",

    # codecs
    "x264", "x265", "h264", "h265", "hevc", "av1",

    # audio
    "aac", "ac3", "eac3", "dd", "ddp", "dts", "truehd", "atmos",

    # misc release flags
    "complete", "repack", "proper", "extended", "unrated", "internal", "dubbed", "subbed", "subs",
    "multi", "readnfo", "nfo", "hdr", "sdr",

    # cam / telesync / screener variants
    "cam", "hdcam", "ts", "hdts", "tc", "hdtc", "scr", "screener", "dvdscr", "r5", "line",

    # common trackers/sites (optional; harmless to drop)
    "rarbg", "eztv", "yify", "tgx","H 264", "max", "hbo","hbomax","X264-DIMENSION","DDP5","XviD-DEMAND","WEB-DLRip","x264-BoB"
}

KEEP_SHORT_WORDS = {
    "a","an","and","as","at","by","for","from","in","of","on","or","the","to","with",
    "new","old","bad","big","war","man","mr","ms","dr","vs","pt","part"
}



# Match tokens like "DDP5.1", "AAC2.0", "EAC3", "DDP", "DDP51" after normalization
RE_AUDIO_TOKEN = re.compile(r"(?i)^(?:ddp?|eac3|ac3|aac|dts|truehd)(?:\d(?:\.\d)?)?$")

def suggest_show_name_from_folder(folder: Path) -> str:
    # basic suggestion: folder name with separators normalized
    s = strip_diacritics(folder.name)
    s = re.sub(r"[._\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .-_")
    return s

def ask_path() -> Path:
    p = Path(input("Path to folder: ").strip()).expanduser()
    if not p.exists():
        raise SystemExit("Folder not found.")
    return p

def ask_mode_and_show_name(target: Path) -> tuple[str, Optional[str]]:
    """
    Returns (mode, show_name_override)
    mode:
      - 'parent' = folder contains multiple show folders
      - 'show'   = folder is a single show folder
      - 'season' = folder is a single season folder (optional if you support it)
    """
    print("\nSelect mode:")
    print("  1) Parent folder (contains multiple shows)")
    print("  2) Single show folder")
    print("  3) Single season folder")
    choice = input("Choice [1/2/3]: ").strip()

    if choice == "2":
        print(f"\nTarget folder: {target}")
        show = input("Show name (leave blank to use folder name): ").strip()
        return "show", (show if show else None)

    if choice == "3":
        print(f"\nTarget folder: {target}")
        show = input("Show name (required for season folder): ").strip()
        if not show:
            print("Season mode requires a show name.")
            return ask_mode_and_show_name(target)
        return "season", show

    # default to parent
    return "parent", None

def looks_like_tag(tok: str) -> bool:
    t = tok.strip()
    if not t:
        return False
    # all-caps-ish short tokens are often tags/groups
    if len(t) <= 6 and t.upper() == t and t.lower() != t:
        return t.lower() not in KEEP_SHORT_WORDS
    # tokens with digits are often tags
    if any(c.isdigit() for c in t) and len(t) <= 10:
        return True
    # "no vowels" blobs like "nhtfs"
    low = t.lower()
    if len(low) <= 8 and low.isalnum() and not any(v in low for v in "aeiou"):
        return True
    return False

def print_menu(csv_path: Path, target: Path, mode: str, show_override: Optional[str], planned: int) -> None:
    print("\n" + "="*80)
    print("SHOW RENAMER")
    print("="*80)
    print(f"Target: {target}")
    print(f"Mode:   {mode}" + (f" | Show: {show_override}" if show_override else ""))
    print(f"Planned renames: {planned}")
    print(f"CSV path: {csv_path}")
    print("-"*80)
    print("v  View changes (first N)")
    print("c  Write CSV only")
    print("a  Apply changes (writes CSV first)")
    print("p  Change path / mode / show name (rebuild plan)")
    print("x  Exit")
    print("="*80)

def view_plan(plan: list[Move], n: int = 25) -> None:
    print("\nShowing planned changes:")
    for i, m in enumerate(plan[:n], start=1):
        print(f"{i:3d}. {m.src}  ->  {m.dst}")
    if len(plan) > n:
        print(f"... ({len(plan) - n} more)")

def build_plan(root: Path, *, mode: str, show_name_override: Optional[str]) -> tuple[list[Move], list[tuple[Path, str, int]]]:
    """
    Returns: (plan, summary)
      plan    = list[Move]
      summary = list of (folder_path, show_name, planned_count)
    """

    if mode == "parent":
        # parent library folder: prompt show name per show folder
        return build_plan_parent(root)

    if mode == "show":
        # single show: allow override if provided, else prompt (with suggestion)
        if show_name_override:
            plan = build_plan_for_show_dir(root, show_name_override)
            return plan, [(root, show_name_override, len(plan))]
        return build_plan_single_show(root)

    if mode == "season":
        # season folder: your helper already prompts for show name + season number
        plan, summary = build_plan_season_folder(root)
        return plan, summary

    raise ValueError(f"bad mode: {mode}")

    # inside your loop:
    # show_name = show_name_override if show_name_override else extract_show_name(show_dir)

def build_plan_season_folder(season_dir: Path) -> tuple[list[Move], list[tuple[Path, str, int]]]:
    print("\nSeason folder:")
    print(f"  {season_dir}")
    show_name = input("Show name (required): ").strip()
    if not show_name:
        raise SystemExit("Show name is required for Season folder mode.")

    # try to extract season from folder name, else ask
    m = re.search(r"(?i)(?:season\s*|s)(\d{1,2})", season_dir.name)
    default_season = int(m.group(1)) if m else None
    season_num = prompt_season_number(default_season)

    plan: list[Move] = []
    for src in sorted(season_dir.rglob("*")):
        if not src.is_file() or src.suffix.lower() not in VIDEO_EXTS:
            continue

        parsed = parse_season_episode(src.name)
        if not parsed:
            if DEBUG_PARSE:
                debug_filename_parse(src.name)
            continue

        _s, episode, raw_title = parsed
        # Override season to the user-provided season_num
        s = season_num

        title = clean_title_from_filename(src.name, raw_title)
        title = re.sub(r"\s+", " ", title).strip(" .-_")

        ep_tag = f"S{z2(s)}E{z2(episode)}"
        new_base = f"{show_name} - {ep_tag}" + (f" - {title}" if title else "")

        new_name = ensure_single_extension(new_base, src)
        # rename in-place inside the season folder
        dst = resolve_collision(src.with_name(new_name))

        if src != dst:
            plan.append(Move(src, dst))

    return plan, [(season_dir, f"{show_name} (Season {season_num:02d})", len(plan))]

SEASON_NAME_RE = re.compile(r"(?i)^(?:season\s*\d{1,2}|s\d{1,2})$")

def list_show_dirs_from_parent(parent: Path) -> list[Path]:
    """
    Parent library: immediate children that are folders.
    We *exclude* folders that look like pure season folders.
    """
    dirs = []
    for p in sorted([x for x in parent.iterdir() if x.is_dir()]):
        if SEASON_NAME_RE.match(p.name.strip()):
            continue
        dirs.append(p)
    return dirs

def build_plan_parent(parent: Path) -> tuple[list[Move], list[tuple[Path, str, int]]]:
    all_plan: list[Move] = []
    summary: list[tuple[Path, str, int]] = []

    show_dirs = list_show_dirs_from_parent(parent)
    print(f"\nFound {len(show_dirs)} show folder(s) under:")
    print(f"  {parent}")

    for show_dir in show_dirs:
        show_name = prompt_show_name_for_dir(show_dir)
        plan = build_plan_for_show_dir(show_dir, show_name)
        all_plan.extend(plan)
        summary.append((show_dir, show_name, len(plan)))
        print(f"Planned renames for '{show_name}': {len(plan)}")

    return all_plan, summary

def build_plan_single_show(show_dir: Path) -> tuple[list[Move], list[tuple[Path, str, int]]]:
    show_name = prompt_show_name_for_dir(show_dir)
    plan = build_plan_for_show_dir(show_dir, show_name)
    return plan, [(show_dir, show_name, len(plan))]

def prompt_season_number(default: int | None = None) -> int:
    while True:
        s = input(f"Season number{f' [{default}]' if default else ''}: ").strip()
        if not s and default is not None:
            return default
        if s.isdigit() and 1 <= int(s) <= 99:
            return int(s)
        print("Enter a season number like 1, 2, 3...")

def prompt_root_mode(root: Path) -> str:
    print("\n" + "=" * 80)
    print("You selected:")
    print(f"  {root}")
    print("\nWhat is this path?")
    print("  [P] Parent library folder (contains many shows)")
    print("  [S] Single show folder (one show, maybe many seasons)")
    print("  [E] Season folder (one season of one show)")
    while True:
        choice = input("Choose P / S / E: ").strip().lower()
        if choice in {"p", "s", "e"}:
            return choice
        print("Please type P, S, or E.")

def prompt_show_name_for_dir(show_dir: Path) -> str:
    print("\n" + "-" * 80)
    print("Show folder:")
    print(f"  {show_dir}")

    suggested = suggest_show_name_from_folder(show_dir)

    raw = input(f"Set show name [{suggested}]: ")
    name = re.sub(r"\s+", " ", raw).strip()

    return name if name else suggested

def get_show_dirs(root: Path) -> list[Path]:
    """
    If user points at a single show folder, return [root].
    If user points at a library root, return immediate subfolders as show dirs.
    """
    if looks_like_single_show_dir(root):
        return [root]
    return sorted([p for p in root.iterdir() if p.is_dir()])

# Token is junk if it is in JUNK_WORDS or looks like audio descriptor
def is_junk_token(tok: str) -> bool:
    low = tok.lower()
    if low in JUNK_WORDS:
        return True
    if RE_AUDIO_TOKEN.match(low):
        return True
    # handle "web-dl" that survived as "webdl" / "web dl" etc
    if low.replace("-", "").replace("_", "").replace(".", "") in JUNK_WORDS:
        return True
    return False

RE_BRACKETS = re.compile(r"""
    (\[[^\]]*\]) |      # [stuff]
    (\([^\)]*\)) |      # (stuff)
    (\{[^\}]*\})        # {stuff}
""", re.VERBOSE)

# --- patterns we can normalize ---


VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".m2ts"}

RE_SXXEYY = re.compile(r"(?i)^s(?P<s>\d{1,2})e(?P<e>\d{1,3})$")
RE_XXxYY  = re.compile(r"(?i)^(?P<s>\d{1,2})x(?P<e>\d{1,3})$")

RE_YEAR = re.compile(r"^(19\d{2}|20\d{2})$")

# Keep your JUNK_TOKENS list, but compile token-level junk matcher:


# Audio patterns like DDP5.1, DDP2.0, AAC2.0 etc:


# Group tags often appear as NHFTS, TGx, RARBG etc (heuristic)



def strip_diacritics(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_for_tokens(stem: str) -> str:
    """
    Make separators consistent and normalize common codec splits.
    """
    s = strip_diacritics(stem)

    # normalize common codec split cases like "H.264" / "H 265" -> "H264" / "H265"
    s = re.sub(r"(?i)\bh\s*[.\-_ ]\s*26([45])\b", r"h26\1", s)

    # drop bracket punctuation but keep contents as tokens
    s = re.sub(r"[\[\]\(\)\{\}]", " ", s)

    # turn common separators into spaces
    s = re.sub(r"[._\-/+,]+", " ", s)

    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize(stem: str) -> List[str]:
    norm = normalize_for_tokens(stem)
    return [t for t in norm.split(" ") if t]

# group tags often look like short alnum blobs, mostly uppercase in source, but after normalization we see lowercase
RE_GROUP_TAG = re.compile(r"(?i)^[a-z0-9]{2,12}$")
# very common “word-like but actually junk” tokens we still want gone
EXTRA_JUNK_LITERALS = {
    "nhtfs", "tgx", "tggx", "ntb", "yts", "ettv", "ion10",
    "rarbg", "eztv", "yify",
}


# very common “word-like but actually junk” tokens we still want gone

def classify_tokens(tokens: List[str]) -> Tuple[Optional[int], Optional[int], List[str], List[str]]:
    """
    Returns: season, episode, title_tokens, debug_removed_tokens
    """
    season: Optional[int] = None
    episode: Optional[int] = None
    title: List[str] = []
    removed: List[str] = []

    for tok in tokens:
        low = tok.lower()

        # s01e02 or s1e8
        m = RE_SXXEYY.match(low)
        if m:
            season = int(m.group("s"))
            episode = int(m.group("e"))
            removed.append(tok)
            continue

        # 1x02
        m = RE_XXxYY.match(low)
        
        if looks_like_tag(tok) and tok.lower() not in KEEP_SHORT_WORDS:
            removed.append(tok)
            continue

        if m:
            season = int(m.group("s"))
            episode = int(m.group("e"))
            removed.append(tok)
            continue

        # junk tokens (services / codecs / quality / etc)
        if is_junk_token(tok):
            removed.append(tok)
            continue

        # extra hardcoded group literals (NHTFS, TGx, YTS, etc)
        if low in EXTRA_JUNK_LITERALS:
            removed.append(tok)
            continue

        # years (usually irrelevant for episodes)
        if RE_YEAR.match(tok):
            removed.append(tok)
            continue

        # group-tag heuristic:
        # once we already have S/E, drop short alnum blobs that are unlikely to be title words
        

        # otherwise: part of title
        title.append(tok)

    return season, episode, title, removed




def parse_episode_from_filename(filename: str) -> Optional[Tuple[int, int, str]]:
    """
    Return (season, episode, cleaned_title) or None if no valid tag.
    """
    stem = Path(filename).stem

    # Remove bracketed chunks completely before tokenizing (TGx, group tags, etc.)
    stem = re.sub(r"\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\}", " ", stem)

    tokens = tokenize(stem)
    s, e, title_tokens, _removed = classify_tokens(tokens)

    if s is None or e is None:
        return None

    title = " ".join(title_tokens).strip()
    title = re.sub(r"\s+", " ", title)

    return s, e, title


# e.g. "The Amazing World of Gumball - 105a - The Pressure ..."
RE_DASH_NUM = re.compile(r"(?i)\s-\s(?P<num>\d{3,4})(?P<part>[ab])?\s-\s")
RE_SEASON_DIR = re.compile(r"(?i)\bseason\s*(\d{1,2})\b|^s(\d{1,2})$")

def clean_title_from_filename(filename: str, fallback_title: str) -> str:
    """
    Uses the SAME tokenization + junk filtering rules to clean a title string.
    This avoids needing a separate clean_release_junk() function.
    """
    # Build a fake "stem" so we can reuse tokenize/classify_tokens.
    # Example: fallback_title might contain WEB / 1080p / H264 etc.
    stem = fallback_title

    # remove bracketed junk
    stem = re.sub(r"\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\}", " ", stem)

    toks = tokenize(stem)
    _s, _e, title_tokens, _removed = classify_tokens(toks)

    title = " ".join(title_tokens).strip()
    title = re.sub(r"\s+", " ", title)
    return title.strip(" .-_")

def pre_normalize_for_parsing(s: str) -> str:
    # strip diacritics first so regex sees stable ASCII-ish text
    s = strip_diacritics(s)
    # unify separators so "Shōgun_S01E02_Title" becomes "Shogun S01E02 Title"
    s = re.sub(r"[._]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_punct(s: str) -> str:
    # convert separators to spaces, collapse whitespace
    s = strip_diacritics(s)

    s = re.sub(r"[._]+", " ", s)
    s = re.sub(r"\s*-\s*", " - ", s)
    s = re.sub(r"\s+", " ", s).strip(" -._")
    return s

RE_TAG_SXXEYY = re.compile(r"(?i)S(?P<s>\d{1,2})\s*E(?P<e>\d{1,3})")
RE_TAG_XXxYY  = re.compile(r"(?i)(?P<s>\d{1,2})x(?P<e>\d{1,3})")


def looks_like_single_show_dir(p: Path) -> bool:
    if RE_SEASON_DIR.search(p.name):
        return False
    # If this folder contains season-ish subfolders OR video files anywhere, treat it as a single show
    try:
        for child in p.iterdir():
            if child.is_dir() and RE_SEASON_DIR.search(child.name):
                return True
        # fallback: if there are videos inside, it's probably a show dir
        return any(f.is_file() and f.suffix.lower() in VIDEO_EXTS for f in p.rglob("*"))
    except PermissionError:
        return False

def safe_move(src: Path, dst: Path) -> bool:
    try:
        src.rename(dst)
        return True
    except Exception as e1:
        try:
            shutil.move(str(src), str(dst))
            return True
        except Exception as e2:
            print(f"[FAIL move] {src} -> {dst} (rename: {e1}; shutil: {e2})")
            return False

        
def ensure_single_extension(base_no_ext: str, src: Path) -> str:
    """
    Return 'base + ext' ensuring base does NOT already end with a video ext.
    Fixes cases like 'Rabbit.avi' + '.avi' => 'Rabbit.avi.avi'
    """
    base = base_no_ext.strip()

    # If base accidentally ends with a known extension, strip it
    lower = base.lower()
    for ext in VIDEO_EXTS:
        if lower.endswith(ext):
            base = base[:-len(ext)]
            base = base.rstrip(" .-_")
            break

    return f"{base}{src.suffix.lower()}"
@dataclass
class Move:
    src: Path
    dst: Path

def z2(n: int) -> str:
    return f"{n:02d}"

def resolve_collision(dst: Path) -> Path:
    if not dst.exists():
        return dst
    stem = dst.with_suffix("").name
    ext = dst.suffix
    for i in range(1, 1000):
        cand = dst.with_name(f"{stem} - dup{i}{ext}")
        if not cand.exists():
            return cand
    raise RuntimeError(f"Too many collisions for {dst}")

def season_folder(show_dir: Path, season: int) -> Path:
    return show_dir / f"Season {z2(season)}"



def parse_season_episode(filename: str) -> Optional[Tuple[int, int, str]]:
    """
    Returns (season, episode, raw_title) or None if no valid S/E tag.
    """
    return parse_episode_from_filename(filename)


def debug_filename_parse(filename: str) -> None:
    stem = Path(filename).stem
    stem2 = re.sub(r"\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\}", " ", stem)
    toks = tokenize(stem2)
    s, e, title, removed = classify_tokens(toks)
    print("FILE:", filename)
    print("TOKS:", toks)
    print("SEASON/EP:", s, e)
    print("REMOVED:", removed)
    print("TITLE:", " ".join(title))
    print()

def build_plan_for_show_dir(show_dir: Path, show_name: str) -> list[Move]:
    plan: list[Move] = []
    show_name_clean = re.sub(r"\s+", " ", show_name).strip()

    for src in sorted(show_dir.rglob("*")):
        if not src.is_file() or src.suffix.lower() not in VIDEO_EXTS:
            continue

        parsed = parse_season_episode(src.name)
        if not parsed:
            if DEBUG_PARSE:
                debug_filename_parse(src.name)
            continue

        season, episode, raw_title = parsed

        title = clean_title_from_filename(src.name, raw_title)
        title = re.sub(r"\s+", " ", title).strip(" .-_")

        # If title is just the show name, drop it
        if title.lower() == show_name_clean.lower():
            title = ""

        ep_tag = f"S{z2(season)}E{z2(episode)}"

        # avoid duplication if title begins with show name
        if title.lower().startswith(show_name_clean.lower() + " "):
            title = title[len(show_name_clean):].strip(" -._")

        new_base = f"{show_name_clean} - {ep_tag}" + (f" - {title}" if title else "")

        dst_dir = season_folder(show_dir, season)
        new_name = ensure_single_extension(new_base, src)
        dst = resolve_collision(dst_dir / new_name)

        if src != dst:
            plan.append(Move(src, dst))

    return plan



def write_csv(plan: list[Move], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst"])
        for m in plan:
            w.writerow([str(m.src), str(m.dst)])

def apply(plan: list[Move]) -> None:
    total = len(plan)

    for i, m in enumerate(plan, start=1):
        if i == 1 or i % 100 == 0 or i == total:
            pct = (i / total) * 100 if total else 100.0
            print(f"[{i}/{total}] {pct:6.2f}%")

        m.dst.parent.mkdir(parents=True, exist_ok=True)

        ok = safe_move(m.src, m.dst)
        if not ok:
            print(f"[FAIL move] {m.src} -> {m.dst}")
            continue

if __name__ == "__main__":
    target = ask_path()
    mode, show_override = ask_mode_and_show_name(target)

    report = Path.cwd() / "show_rename_plan.csv"

    plan, summary = build_plan(target, mode=mode, show_name_override=show_override)

    while True:
        print_menu(report, target, mode, show_override, len(plan))
        cmd = input("Command: ").strip().lower()

        if cmd == "v":
            n = input("How many to show [25]: ").strip()
            view_plan(plan, int(n) if n.isdigit() else 25)

        elif cmd == "c":
            write_csv(plan, report)
            print(f"Wrote CSV: {report}")

        elif cmd == "a":
            write_csv(plan, report)
            print(f"CSV written: {report}")
            confirm = input("Type YES to apply: ").strip()
            if confirm == "YES":
                apply(plan)
                print("Done.")
            else:
                print("Cancelled apply.")

        elif cmd == "p":
            target = ask_path()
            mode, show_override = ask_mode_and_show_name(target)
            plan, summary = build_plan(target, mode=mode, show_name_override=show_override)
            print(f"Rebuilt plan: {len(plan)} changes")

        elif cmd == "x":
            print("Exit.")
            break

        else:
            print("Unknown command.")

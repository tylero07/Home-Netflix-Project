#!/usr/bin/env bash
set -euo pipefail

# Usage:
#          *********This utility needs an argument to run*********
#   ./seed_media_test.sh gen
#   ./seed_media_test.sh del
#
# Default BASE_DIR is ./test_media
#
# This generator is intentionally "messy" to stress-test:
#  - Year parsing vs titles that contain years (Blade Runner 2049, 2012, 1917, 300, 127 Hours)
#  - Leading-year titles (2001 A Space Odyssey)
#  - Roman numerals (Rocky II / Rocky III)
#  - Weird separators (. _ -)
#  - Junk tokens (1080p, bluray, x265, etc.)
#  - Duplicate variants / collisions
#  - Sidecars with multi-suffix (.eng.srt, .forced.srt)
#  - BONUS_FEATURES folders that should be ignored by your script

ACTION="${1:-}"
BASE_DIR="${2:-./test_media}"
BASE_SORTED="${3:-./sorted_media}"
BASE_MOVIES="${PWD}/movies"


die() { echo "Error: $*" >&2; exit 1; }

mkdirp() { mkdir -p "$1"; }

touchf() {
  # Create file and ensure parent exists
  local f="$1"
  mkdir -p "$(dirname "$f")"
  : > "$f"
}

gen() {
  echo "Generating test media tree at: $BASE_DIR"
  mkdirp "$BASE_DIR"
    # ---------------- Phase 0 Hygiene test cases ----------------

  # macOS trash files
  touchf "$BASE_DIR/movies/loose_movies/.DS_Store"
  touchf "$BASE_DIR/movies/loose_movies/._The.Matrix.1999.1080p.BluRay.mkv"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/._Dune.2021.2160p.HDR.DV.Atmos.mkv"

  # codec/res quality variety (your rules: low codec = not h265, low res = <1080)
  touchf "$BASE_DIR/movies/loose_movies/Comedy.Classic.1994.480p.x264.mp4"        # RED (both low)
  touchf "$BASE_DIR/movies/loose_movies/Old.Action.1987.720p.x265.mkv"            # YELLO (low res only, but HEVC)
  touchf "$BASE_DIR/movies/loose_movies/Modern.Movie.2019.1080p.x264.mkv"         # YELLO (codec low only)
  touchf "$BASE_DIR/movies/loose_movies/Good.Movie.2020.1080p.x265.mkv"           # GREEN
  touchf "$BASE_DIR/movies/loose_movies/Spectacle.2021.2160p.x265.mkv"            # BLUE

  # duplicates by name+size (exact)
  # NOTE: touch creates 0-byte files, so same name/size duplicates will group.
  touchf "$BASE_DIR/movies/loose_movies/Dupe.Test.2010.1080p.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/Dupe.Test.2010.1080p.x265.mkv (1)"

  # duplicates with same name but different size (simulate by writing bytes)
  mkdirp "$BASE_DIR/movies/loose_movies/dupe_sizes"
  printf 'AAAA' > "$BASE_DIR/movies/loose_movies/dupe_sizes/Size.Dupe.2005.1080p.x264.mkv"
  printf 'BBBBBBBB' > "$BASE_DIR/movies/loose_movies/dupe_sizes/Size.Dupe.2005.1080p.x264.mkv (1)"
  printf 'CCCCCCCCCCCC' > "$BASE_DIR/movies/loose_movies/dupe_sizes/Size.Dupe.2005.1080p.x264.mkv (2)"

    # ---------------- Phase 1 Standard test cases ----------------
  # Top-level buckets
  mkdirp "$BASE_DIR/movies/loose_movies"
  mkdirp "$BASE_DIR/movies/directories"
  mkdirp "$BASE_DIR/tv_shows"
  mkdirp "$BASE_DIR/kung_fu"
  mkdirp "$BASE_DIR/horror"
  mkdirp "$BASE_DIR/comedies"

  # --- Movies: loose files (messy names) ---
  touchf "$BASE_DIR/movies/loose_movies/Blade.Runner.2049.1080p.BluRay.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/Blade.Runner.2049.1080p.BluRay.x265.eng.srt"
  touchf "$BASE_DIR/movies/loose_movies/Blade.Runner.2049.1080p.BluRay.x265.nfo"

  touchf "$BASE_DIR/movies/loose_movies/1917.1080p.BluRay.mkv"
  touchf "$BASE_DIR/movies/loose_movies/1917.1080p.BluRay.srt"

  touchf "$BASE_DIR/movies/loose_movies/2001.A.Space.Odyssey.1968.1080p.mkv"
  touchf "$BASE_DIR/movies/loose_movies/2001.A.Space.Odyssey.1968.1080p.forced.srt"

  touchf "$BASE_DIR/movies/loose_movies/The.Matrix.1999.1080p.BluRay.mkv"
  touchf "$BASE_DIR/movies/loose_movies/The.Matrix.1999.1080p.BluRay.eng.srt"
  touchf "$BASE_DIR/movies/loose_movies/The.Matrix.1999.1080p.BluRay.idx"
  touchf "$BASE_DIR/movies/loose_movies/The.Matrix.1999.1080p.BluRay.sub"

  touchf "$BASE_DIR/movies/loose_movies/Movie.Title.EXTENDED.2012.720p.mkv"
  touchf "$BASE_DIR/movies/loose_movies/Movie.Title.EXTENDED.2012.720p.srt"

  # Duplicates / variants
  touchf "$BASE_DIR/movies/loose_movies/thematrix_lostmovies.net.mvi"
  touchf "$BASE_DIR/movies/loose_movies/thematrix_lostmovies.net.mvi (1)"
  touchf "$BASE_DIR/movies/loose_movies/matrix1080(2002).mp4"
  touchf "$BASE_DIR/movies/loose_movies/the.matrix.1999.720p.mkv"
  touchf "$BASE_DIR/movies/loose_movies/The.Matrix.1999.2160p.REMUX.H265.mkv"

  # Weird separators
  touchf "$BASE_DIR/movies/loose_movies/Good_Bad_Ugly-1966-480p-lizbothnetmovies.mkv"
  touchf "$BASE_DIR/movies/loose_movies/Good-Bad-Ugly_1966_1080p_BluRay_x265.mkv"

  # ---------------- Edge cases to add ----------------

  # 1) Titles that contain a "year-like" number but it's NOT the release year
  #    (should NOT become "(2049)" etc. because 2049 is outside CURRENT_YEAR)
  touchf "$BASE_DIR/movies/loose_movies/Blade.Runner.2049.1080p.WEBRip.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/Blade.Runner.2049.1080p.WEBRip.x265.eng.srt"

  # 2) Movies whose titles are 4-digit numbers (your year parser should only treat as year AFTER title exists)
  touchf "$BASE_DIR/movies/loose_movies/2012.2009.1080p.BluRay.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/2012.2009.1080p.BluRay.x265.srt"

  touchf "$BASE_DIR/movies/loose_movies/300.2006.1080p.BluRay.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/127.Hours.2010.1080p.BluRay.x265.mkv"

  # 3) Leading year in the title (should keep first token as title, then use later year as release year)
  touchf "$BASE_DIR/movies/loose_movies/2001.A.Space.Odyssey.1968.REMUX.2160p.mkv"

  # 4) Roman numerals (II / III / IV)
  touchf "$BASE_DIR/movies/loose_movies/Rocky.II.1979.1080p.BluRay.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/Rocky.III.1982.1080p.BluRay.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/Star.Wars.Episode.IV.1977.1080p.BluRay.x265.mkv"

  # 5) Multi-suffix sidecars (.eng.forced.srt)
  touchf "$BASE_DIR/movies/loose_movies/The.Matrix.1999.1080p.BluRay.eng.forced.srt"

  # 6) Collision test: two different originals normalize to the same target name
  #    (your resolve_collision() should generate " - dup1")
  touchf "$BASE_DIR/movies/loose_movies/The.Matrix.1999.1080p.WEBRip.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/The.Matrix.1999.1080p.WEBRip.x265.srt"

  # 7) Case weirdness + junk tokens
  touchf "$BASE_DIR/movies/loose_movies/the.LOrd.of.the.RINGS.the.RETURN.of.the.KING.2003.1080p.BluRay.x265.mkv"
  touchf "$BASE_DIR/movies/loose_movies/the.LOrd.of.the.RINGS.the.RETURN.of.the.KING.2003.1080p.BluRay.x265.eng.srt"

  # 8) BONUS_FEATURES folder should be ignored by the rename/sort tools
  mkdirp "$BASE_DIR/movies/loose_movies/BONUS_FEATURES"
  touchf "$BASE_DIR/movies/loose_movies/BONUS_FEATURES/Random.Featurette.2020.1080p.mkv"
  touchf "$BASE_DIR/movies/loose_movies/BONUS_FEATURES/Random.Featurette.2020.1080p.srt"

  # --- Movies: each in its own directory ---
  mkdirp "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/Dune.2021.2160p.HDR.DV.Atmos.mkv"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/Dune.2021.2160p.HDR.DV.Atmos.eng.srt"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/Dune.2021.2160p.HDR.DV.Atmos.nfo"

  # BONUS_FEATURES inside a movie folder (common real-world layout)
  mkdirp "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/BONUS_FEATURES"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/BONUS_FEATURES/Behind.The.Scenes.mkv"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/BONUS_FEATURES/Deleted.Scenes.mkv"

  mkdirp "$BASE_DIR/movies/directories/Interstellar.2014.1080p.BluRay.x264"
  touchf "$BASE_DIR/movies/directories/Interstellar.2014.1080p.BluRay.x264/Interstellar.2014.1080p.BluRay.x264.mkv"
  touchf "$BASE_DIR/movies/directories/Interstellar.2014.1080p.BluRay.x264/Interstellar.2014.1080p.BluRay.x264.srt"

  mkdirp "$BASE_DIR/movies/directories/Rocky.II.1979.1080p"
  touchf "$BASE_DIR/movies/directories/Rocky.II.1979.1080p/Rocky.II.1979.1080p.mkv"

  # --- TV shows (nested seasons) ---
  mkdirp "$BASE_DIR/tv_shows/Breaking.Bad/Season.01"
  touchf "$BASE_DIR/tv_shows/Breaking.Bad/Season.01/Breaking.Bad.S01E01.720p.WEB-DL.x265.mkv"
  touchf "$BASE_DIR/tv_shows/Breaking.Bad/Season.01/Breaking.Bad.S01E01.720p.WEB-DL.x265.eng.srt"
  touchf "$BASE_DIR/tv_shows/Breaking.Bad/Season.01/Breaking.Bad.S01E02.720p.WEB-DL.x265.mkv"

  mkdirp "$BASE_DIR/tv_shows/The.Office/Season_02"
  touchf "$BASE_DIR/tv_shows/The.Office/Season_02/The.Office.S02E01.1080p.WEBRip.h265.mkv"
  touchf "$BASE_DIR/tv_shows/The.Office/Season_02/The.Office.S02E01.1080p.WEBRip.h265.srt"

  # A TV show named "Extras" (to prove BONUS_FEATURES doesn't collide)
  mkdirp "$BASE_DIR/tv_shows/Extras/Season.01"
  touchf "$BASE_DIR/tv_shows/Extras/Season.01/Extras.S01E01.576p.DVDRip.x264.mkv"

  # --- Kung fu (genre folder + deeper nesting) ---
  mkdirp "$BASE_DIR/kung_fu/Jackie_Chan/Classic"
  touchf "$BASE_DIR/kung_fu/Jackie_Chan/Classic/Police.Story.1985.1080p.BluRay.x265.mkv"
  touchf "$BASE_DIR/kung_fu/Jackie_Chan/Classic/Drunken.Master.1978.720p.BRRip.x264.mkv"
  touchf "$BASE_DIR/kung_fu/Jackie_Chan/Classic/Drunken.Master.1978.720p.BRRip.x264.srt"

  # --- Extra buckets with nested items ---
  mkdirp "$BASE_DIR/horror/80s"
  touchf "$BASE_DIR/horror/80s/The.Thing.1982.1080p.BluRay.x265.mkv"

  mkdirp "$BASE_DIR/comedies/adam_sandler"
  touchf "$BASE_DIR/comedies/adam_sandler/Happy.Gilmore.1996.1080p.BluRay.x265.mkv"

  echo "Done."
  echo "Tip: run your python tool against: $BASE_DIR"
}

del() {
  if [[ -d "$BASE_DIR" ]]; then
    echo "Deleting test media tree: $BASE_DIR"
    rm -rf "$BASE_DIR"
    echo "Deleted."
  else
    echo "Nothing to delete at: $BASE_DIR"
  fi

  if [[ -d "$BASE_SORTED" ]]; then
    echo "Deleting test media tree: $BASE_SORTED"
    rm -rf "$BASE_SORTED"
    echo "Deleted."
  else
    echo "Nothing to delete at: $BASE_SORTED"
  fi

  if [[ -d "$BASE_MOVIES" ]]; then
    echo "Deleting test media tree: $BASE_MOVIES"
    rm -rf "$BASE_MOVIES"
    echo "Deleted."
  else
    echo "Nothing to delete at: $BASE_MOVIES"
  fi
}

case "$ACTION" in
  gen) gen ;;
  del) del ;;
  *) die "Usage: $0 {gen|del} [BASE_DIR]" ;;
esac

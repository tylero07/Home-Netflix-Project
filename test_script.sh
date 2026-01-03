#!/usr/bin/env bash
set -euo pipefail

# Usage:
#          *********This utility needs an argument to run*********
#   ./seed_media_test.sh gen 
#   ./seed_media_test.sh del 
#
# Default BASE_DIR is ./test_media

ACTION="${1:-}"
BASE_DIR="${2:-./test_media}"

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

  # --- Movies: each in its own directory ---
  mkdirp "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/Dune.2021.2160p.HDR.DV.Atmos.mkv"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/Dune.2021.2160p.HDR.DV.Atmos.eng.srt"
  touchf "$BASE_DIR/movies/directories/Dune.2021.2160p.HDR.DV.Atmos/Dune.2021.2160p.HDR.DV.Atmos.nfo"

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
}

case "$ACTION" in
  gen) gen ;;
  del) del ;;
  *) die "Usage: $0 {gen|del} [BASE_DIR]" ;;
esac

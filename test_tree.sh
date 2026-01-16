#!/usr/bin/env bash
set -e

ROOT="./movie_sort_test"

echo "==> Creating test tree at: $ROOT"
rm -rf "$ROOT"
mkdir -p "$ROOT"

########################################
# Case 1: Single-movie folder + BONUS_FEATURES
########################################
mkdir -p "$ROOT/A/Alpha Movie (2001)/BONUS_FEATURES"

touch "$ROOT/A/Alpha Movie (2001)/Alpha Movie (2001).mkv"
touch "$ROOT/A/Alpha Movie (2001)/Alpha Movie (2001).srt"
touch "$ROOT/A/Alpha Movie (2001)/BONUS_FEATURES/behind_the_scenes.mkv"
touch "$ROOT/A/Alpha Movie (2001)/BONUS_FEATURES/deleted_scenes.mp4"

########################################
# Case 2: Loose movie (no folder)
########################################
mkdir -p "$ROOT/B"

touch "$ROOT/B/Bravo Film (1999).mp4"
touch "$ROOT/B/Bravo Film (1999).eng.srt"

########################################
# Case 3: Folder with multiple movies (NOT single-movie)
########################################
mkdir -p "$ROOT/C/Charlie Bundle"

touch "$ROOT/C/Charlie Bundle/Charlie One (2010).mkv"
touch "$ROOT/C/Charlie Bundle/Charlie Two (2012).mkv"

########################################
# Case 4: Folder with video + junk (should NOT qualify)
########################################
mkdir -p "$ROOT/D/Dirty Folder"

touch "$ROOT/D/Dirty Folder/Dirty Movie (2005).avi"
touch "$ROOT/D/Dirty Folder/random.txt"

########################################
# Case 5: Orphaned sidecar
########################################
mkdir -p "$ROOT/E"

touch "$ROOT/E/Orphan.srt"

########################################
# Case 6: Weird / legacy / unknown extensions
########################################
mkdir -p "$ROOT/F"

touch "$ROOT/F/OldMovie.mvi"
touch "$ROOT/F/OldMovie.dat"
touch "$ROOT/F/junk.something.mkv123"

########################################
# Case 7: BONUS_FEATURES alone (edge case)
########################################
mkdir -p "$ROOT/G/BONUS_FEATURES"
touch "$ROOT/G/BONUS_FEATURES/bonus_only.mkv"

########################################
# Case 8: Trash files
########################################
mkdir -p "$ROOT/H"
touch "$ROOT/H/.DS_Store"
touch "$ROOT/H/._AppleDouble"

########################################
# Done
########################################
echo
echo "==> Test structure created."
echo
echo "Inspect with:"
echo "  tree $ROOT"
echo
q
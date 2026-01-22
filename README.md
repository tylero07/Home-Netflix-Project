# Home Netflix Project
This project is about building a long-term home media setup using a mix of hardware and simple Python automation. The main goal is to keep a large personal movie and TV library organized, usable, and easy to maintain as it grows.

Instead of relying on streaming platforms that rotate or remove content, this system is built around owning the media, storing it locally, and playing it back at good quality (1080p+ using H.265). The code in this repo focuses on handling the boring but necessary parts: naming, sorting, metadata, and cleanup.

This repo documents both what I’m building and how I’m thinking about it as the project evolves.

# Updates/Revisions
* Version 1.0.1
    Will add Interface to navigate directories, generate list of recommended updates, and reconcile duplicate files
    

Project Goals
* Normalize inconsistent movie filenames into a consistent format
* Automatically pull basic metadata (title, year, posters, cast, etc.)
* Generate List of Poor Quality Videos
* Reconcile Duplicate Files
* Easier UI to Ease Use
* Keep metadata compatible with playback devices like the Zidoo Z9X Pro
* Sort media by quality level
* 4K vs 1080p
* High vs low bitrate
* Codec-based differences (ie dolby vision and 3D iso's)
* Detect duplicate versions and allow choosing between them
* Blu-ray vs WEB
* Extended or director’s cuts (See LOTR and Star Wars editions)
* Attach subtitles automatically when available
* Leave room for smarter movie searching or recommendations later
* Keep everything modular and easy to change as hardware and movie types (eventual 8k) or needs evolve

Why This Project Exists

I have a large media library (5800+ videos), problems have started stacking up:
* Filenames from different sources don’t match
* Scrapers break or pull the wrong movie
* Duplicate versions pile up quietly
* Storage fills faster than expected (files range from ~2 GB to 100+ GB)
* Manually fixing everything doesn’t scale and inefficient
* Playback is wildly incosistent from player to player and device to device causing weird artifacts and poor playback with fancier encoding types
* Overall preservation mindset with old games, and media types

My current setup slows down as more media is added. This project is meant to fix that and provide a local media preservation project start for eventually sharing content with friends or family.

# READ BEFORE RUNNING
* Movies and tv shows MUST be in seperate directories
* Movie extras MUST manually be named to EXACTLY the following 'BONUS_FEATURES'
* Sidecar/subtitle files will be ignored if there is no movie to match on the current normalizor run
* handles .mvi files and junk and will be ignored and sorted if chosen
* tv shows will use the parent dir to determine show name ie shows-> Name of show (dir) -> season__ -> episode where name of show should be manually fixed
* recursion is used to search to depth so if something is a mess in a sub directory the sorting will also be a mess
* USE CSV PLANS AND READ CAREFULLY PRIOR TO APPLYING CHANGES

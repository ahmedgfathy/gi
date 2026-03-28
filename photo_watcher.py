#!/usr/bin/env python3
"""
photo_watcher.py
Watches /mnt/c/photo and auto-moves any new file into:
  /mnt/c/photo/Images/   <-- for image files
  /mnt/c/photo/Videos/   <-- for video files
Files that are not media are left untouched.

Uses POLLING (not inotify) so it works on Windows drives via /mnt/c/.
Poll interval: 3 seconds.

Usage:
  python photo_watcher.py           # run in foreground (Ctrl+C to stop)
  bash watch_photos.sh start        # run in background
"""

import sys
import time
import shutil
import logging
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
WATCH_DIR  = Path("/mnt/c/photo")
IMAGES_DIR = WATCH_DIR / "Images"
VIDEOS_DIR = WATCH_DIR / "Videos"
LOG_FILE   = WATCH_DIR / "watcher.log"
POLL_SECS  = 3          # how often to scan the watch directory

IMAGE_EXTS = {".jpg",".jpeg",".png",".gif",".bmp",".tiff",".tif",
              ".webp",".heic",".heif",".avif",".svg",".ico",
              ".cr2",".nef",".arw",".dng",".raw"}
VIDEO_EXTS = {".mp4",".mov",".avi",".mkv",".wmv",".flv",".webm",
              ".m4v",".3gp",".3g2",".mts",".m2ts",".ts",".vob",
              ".ogv",".f4v",".rm",".rmvb"}

# ── Logging ───────────────────────────────────────────────────────────────────
IMAGES_DIR.mkdir(exist_ok=True)
VIDEOS_DIR.mkdir(exist_ok=True)

fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(
    level=logging.INFO,
    format=fmt,
    datefmt=datefmt,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("watcher")

# ── Helpers ───────────────────────────────────────────────────────────────────
def unique_dest(dest: Path) -> Path:
    """If dest exists, append _dup1, _dup2 … until unique."""
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while True:
        candidate = dest.parent / f"{stem}_dup{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1

def classify_and_move(src: Path) -> None:
    """Move src to the correct subfolder."""
    ext = src.suffix.lower()
    if ext in IMAGE_EXTS:
        target_dir = IMAGES_DIR
        category = "Images"
    elif ext in VIDEO_EXTS:
        target_dir = VIDEOS_DIR
        category = "Videos"
    else:
        return  # not a media file, skip

    dest = unique_dest(target_dir / src.name)
    try:
        shutil.move(str(src), dest)
        log.info("Moved [%s]  %s  ->  %s", category, src.name, dest)
    except Exception as exc:
        log.error("Failed to move %s: %s", src.name, exc)

# ── Polling loop ──────────────────────────────────────────────────────────────
def get_files_in_root(directory: Path) -> set:
    """Return set of file paths directly inside directory (not subdirs)."""
    try:
        return {p for p in directory.iterdir() if p.is_file()}
    except Exception:
        return set()

def main():
    log.info("=" * 60)
    log.info("Photo Watcher started (polling every %ds)", POLL_SECS)
    log.info("  Watching : %s", WATCH_DIR)
    log.info("  Images   -> %s", IMAGES_DIR)
    log.info("  Videos   -> %s", VIDEOS_DIR)
    log.info("  Log file : %s", LOG_FILE)
    log.info("  Press Ctrl+C to stop")
    log.info("=" * 60)

    known_files = get_files_in_root(WATCH_DIR)

    try:
        while True:
            time.sleep(POLL_SECS)
            current_files = get_files_in_root(WATCH_DIR)
            new_files = current_files - known_files

            for f in new_files:
                # Skip log file and hidden/system files
                if f.name.startswith(".") or f == LOG_FILE:
                    known_files.add(f)
                    continue
                # Give Windows time to finish writing the file
                time.sleep(0.5)
                if f.exists():
                    classify_and_move(f)
                    # remove from known (it was moved), do not add
                else:
                    known_files.add(f)

            # Refresh known set (only files still present in root)
            known_files = get_files_in_root(WATCH_DIR)

    except KeyboardInterrupt:
        log.info("Watcher stopped by user.")

if __name__ == "__main__":
    main()

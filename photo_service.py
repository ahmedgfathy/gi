#!/usr/bin/env python3
"""
photo_service.py  —  Unified Photo Service v3
==============================================
Pipeline for every image/video in C:\photo\ (root OR any subfolder):
  1. DEDUP     — SHA256: delete exact byte-for-byte copies
  2. MOVE      — Images/ or Videos/
  3. CLASSIFY  — CLIP AI → People / Animals / Nature / Food /
                            Vehicles / Architecture / Documents / Other

On startup:
  - Deduplicates the ENTIRE tree
  - Processes ALL files already in root / input subfolders
  - Classifies images already staged in Images/ root

Then polls every POLL_SECS for new arrivals — forever.
"""

import os, sys, re, time, shutil, hashlib, logging, warnings
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["MPLBACKEND"] = "Agg"

# ── Config ────────────────────────────────────────────────────────────────────
WATCH_DIR  = Path("/mnt/c/photo")
IMAGES_DIR = WATCH_DIR / "Images"
VIDEOS_DIR = WATCH_DIR / "Videos"
LOG_FILE   = WATCH_DIR / "photo_service.log"
POLL_SECS  = 4
BATCH_SIZE = 32   # images per CLIP batch

IMAGE_EXTS = {".jpg",".jpeg",".png",".gif",".bmp",".tiff",".tif",
              ".webp",".heic",".heif",".avif",".cr2",".nef",
              ".arw",".dng",".raw",".svg",".ico"}
VIDEO_EXTS = {".mp4",".mov",".avi",".mkv",".wmv",".flv",".webm",
              ".m4v",".3gp",".3g2",".mts",".m2ts",".ts",".vob",
              ".ogv",".f4v",".rm",".rmvb"}
SKIP_EXT   = {".log",".txt",".md",".csv",".json",".py",".sh",".pid",".db"}
SKIP_PFX   = ("dedup_report","photo_service","watcher","classification",
              "content_watcher")

# Output dirs — never pick up files from inside these as "new input"
OUTPUT_DIRS = {"Images", "Videos"}

CATEGORIES = {
    "People":       ["a photo of a person", "a portrait of a human face",
                     "a selfie photo", "people together in a photo"],
    "Animals":      ["a photo of an animal", "a dog or cat pet",
                     "wildlife nature animals", "birds or fish in a photo"],
    "Documents":    ["a document or written paper", "text printed on paper",
                     "a screenshot of an app", "an ID card or certificate"],
    "Nature":       ["a scenic landscape photo", "trees plants or flowers",
                     "mountains sky or ocean", "outdoor nature photography"],
    "Food":         ["food on a plate or bowl", "a cooked meal or dish",
                     "beverage or drink", "cooking food ingredients"],
    "Vehicles":     ["a car or automobile", "motorcycle or bicycle",
                     "truck bus or van", "airplane ship or boat"],
    "Architecture": ["a building or house exterior", "indoor room interior design",
                     "architectural photo of structures", "city street or bridge"],
    "Other":        ["an abstract or artistic photo", "a product on white background",
                     "technology device or gadget", "random miscellaneous photo"],
}

# ── Setup ─────────────────────────────────────────────────────────────────────
def setup():
    for d in [IMAGES_DIR, VIDEOS_DIR]:
        d.mkdir(exist_ok=True)
    for cat in CATEGORIES:
        (IMAGES_DIR / cat).mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("photo_service")

def skippable(entry) -> bool:
    name = entry.name if hasattr(entry, 'name') else Path(entry).name
    return (
        name.startswith(".")
        or any(name.startswith(p) for p in SKIP_PFX)
        or Path(name).suffix.lower() in SKIP_EXT
    )

# ── File helpers ──────────────────────────────────────────────────────────────
def sha256(path: Path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

def copy_score(path: Path) -> int:
    """Lower score = more likely the original."""
    n = path.stem
    # Count total copy-suffix markers like (1)(2), (3), etc.
    markers = re.findall(r'\((\d+)\)', n)
    if not markers:
        return len(n)               # no copy suffix = original
    max_num = max(int(m) for m in markers)
    if max_num >= 2:
        return len(n) + 10000       # (2), (3), (4) etc = definitely a copy
    return len(n) + 500             # (1) = likely a copy, but might be original

def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 1
    while True:
        c = dest.parent / f"{dest.stem}_new{i}{dest.suffix}"
        if not c.exists():
            return c
        i += 1

def all_files_recursive(root: Path) -> list:
    """All non-skipped files in entire tree."""
    result = []
    try:
        for e in os.scandir(root):
            if e.is_dir(follow_symlinks=False):
                result.extend(all_files_recursive(Path(e.path)))
            elif e.is_file() and not skippable(e):
                result.append(Path(e.path))
    except Exception:
        pass
    return result

def scan_input_files(watch_dir: Path) -> list:
    """
    Files that need processing (not already in output destinations):
    - Files directly in watch_dir root
    - Files in any subfolder that is NOT Images/ or Videos/ or their children
    """
    result = []
    try:
        for e in os.scandir(watch_dir):
            if e.is_file() and not skippable(e):
                ext = Path(e.name).suffix.lower()
                if ext in (IMAGE_EXTS | VIDEO_EXTS):
                    result.append(Path(e.path))
            elif e.is_dir() and e.name not in OUTPUT_DIRS and not e.name.startswith("."):
                try:
                    for sub in os.scandir(e.path):
                        if sub.is_file() and not skippable(sub):
                            ext = Path(sub.name).suffix.lower()
                            if ext in (IMAGE_EXTS | VIDEO_EXTS):
                                result.append(Path(sub.path))
                except Exception:
                    pass
    except Exception:
        pass
    return result

def scan_images_root() -> list:
    """Images sitting in Images/ root — staged but not classified yet."""
    try:
        return [
            Path(e.path) for e in os.scandir(IMAGES_DIR)
            if e.is_file() and not skippable(e)
            and Path(e.name).suffix.lower() in IMAGE_EXTS
        ]
    except Exception:
        return []

def try_remove_empty(folder: Path):
    if folder not in (WATCH_DIR, IMAGES_DIR, VIDEOS_DIR):
        try:
            if not any(True for _ in os.scandir(folder)):
                folder.rmdir()
        except Exception:
            pass

# ── Hash Store ────────────────────────────────────────────────────────────────
class HashStore:
    def __init__(self, log):
        self._db: dict = {}
        self.log = log

    def build(self, root: Path) -> int:
        files = all_files_recursive(root)
        self.log.info("Dedup scan: hashing %d existing files...", len(files))
        groups: dict = defaultdict(list)
        for i, p in enumerate(files, 1):
            h = sha256(p)
            if h:
                groups[h].append(p)
            if i % 1000 == 0:
                self.log.info("  Hashed %d / %d...", i, len(files))
        deleted = 0
        for h, paths in groups.items():
            best = min(paths, key=lambda p: (copy_score(p), str(p)))
            self._db[h] = best
            for p in paths:
                if p != best and p.exists():
                    try:
                        p.unlink()
                        self.log.info("DEDUP-INIT  kept: %-40s  deleted: %s",
                                      best.name, p.name)
                        deleted += 1
                    except Exception as exc:
                        self.log.error("DEDUP-INIT  fail %s: %s", p, exc)
        self.log.info("Dedup done — %d duplicates removed, %d unique files",
                      deleted, len(self._db))
        return deleted

    def check(self, path: Path):
        h = sha256(path)
        if h is None:
            return "no-hash"
        if h in self._db:
            existing = self._db[h]
            if existing == path:
                return h   # same file, already registered
            if existing.exists():
                keep_existing = copy_score(existing) <= copy_score(path)
                if keep_existing:
                    try:
                        path.unlink()
                        self.log.info("DEDUP  del copy: %-40s  kept: %s",
                                      path.name, existing.name)
                    except Exception as exc:
                        self.log.error("DEDUP  fail %s: %s", path.name, exc)
                    return None
                else:
                    try:
                        existing.unlink()
                        self.log.info("DEDUP  del old:  %-40s  kept: %s",
                                      existing.name, path.name)
                    except Exception as exc:
                        self.log.error("DEDUP  fail %s: %s", existing.name, exc)
                    self._db[h] = path
                    return h
            else:
                self._db[h] = path
                return h
        self._db[h] = path
        return h

    def update(self, h, new_path: Path):
        if h and h != "no-hash" and h in self._db:
            self._db[h] = new_path

# ── CLIP Classifier ───────────────────────────────────────────────────────────
class Classifier:
    def __init__(self, log):
        self.log = log
        self._ok = False

    def load(self):
        import torch
        from transformers import CLIPProcessor, CLIPModel
        self.log.info("Loading CLIP model...")
        self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.proc  = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        self.model.eval()
        self.torch = torch
        vecs = {}
        with torch.no_grad():
            for cat, prompts in CATEGORIES.items():
                enc = self.proc(text=prompts, return_tensors="pt",
                                padding=True, truncation=True)
                out = self.model.text_model(
                    input_ids=enc["input_ids"],
                    attention_mask=enc.get("attention_mask"),
                )
                f = self.model.text_projection(out.pooler_output)
                f = f / f.norm(dim=-1, keepdim=True)
                avg = f.mean(dim=0)
                vecs[cat] = avg / avg.norm()
        self.cats    = list(vecs.keys())
        self.cat_mat = torch.stack([vecs[c] for c in self.cats])
        self._ok = True
        self.log.info("CLIP ready — categories: %s", ", ".join(self.cats))

    def predict_batch(self, paths: list) -> list:
        """Classify a batch of paths at once. Returns list of category strings."""
        from PIL import Image
        images, valid_idx = [], []
        results = ["Other"] * len(paths)
        for i, p in enumerate(paths):
            try:
                images.append(Image.open(p).convert("RGB"))
                valid_idx.append(i)
            except Exception:
                pass
        if not images:
            return results
        with self.torch.no_grad():
            enc  = self.proc(images=images, return_tensors="pt", padding=True)
            vis  = self.model.vision_model(pixel_values=enc["pixel_values"])
            feat = self.model.visual_projection(vis.pooler_output)
            feat = feat / feat.norm(dim=-1, keepdim=True)
        sims = feat @ self.cat_mat.T
        best = sims.argmax(dim=-1).tolist()
        if isinstance(best, int):
            best = [best]
        for li, oi in enumerate(valid_idx):
            results[oi] = self.cats[best[li]]
        return results

# ── Core pipeline ─────────────────────────────────────────────────────────────
def process_batch(paths: list, clf: Classifier, hs: HashStore, log,
                  already_in_images=False):
    """
    Dedup + classify a batch of files.
    already_in_images=True means files are already inside IMAGES_DIR root.
    """
    # Stage all files into IMAGES_DIR root first (skip if already there)
    staged = []
    origins = {}   # staged path -> original path (for cleanup)
    for src in paths:
        if not src.exists():
            continue
        ext = src.suffix.lower()
        if ext in VIDEO_EXTS:
            # Videos: just dedup + move to Videos/
            h = hs.check(src)
            if h is not None:
                dest = unique_dest(VIDEOS_DIR / src.name)
                try:
                    shutil.move(str(src), dest)
                    hs.update(h, dest)
                    log.info("VIDEO     %s", src.name)
                    try_remove_empty(src.parent)
                except Exception as exc:
                    log.error("Video-move fail %s: %s", src.name, exc)
            continue
        if ext not in IMAGE_EXTS:
            continue
        if already_in_images:
            staged.append(src)
        else:
            dst = unique_dest(IMAGES_DIR / src.name)
            try:
                shutil.move(str(src), dst)
                try_remove_empty(src.parent)
                staged.append(dst)
                origins[dst] = src
            except Exception as exc:
                log.error("Stage fail %s: %s", src.name, exc)

    if not staged:
        return

    # Dedup
    to_classify = []
    hashes = {}
    for p in staged:
        h = hs.check(p)
        if h is not None:
            to_classify.append(p)
            hashes[p] = h
        # if None, file was a duplicate and was deleted

    if not to_classify:
        return

    # Batch CLIP classify
    categories = clf.predict_batch(to_classify)
    for p, cat in zip(to_classify, categories):
        dest = unique_dest(IMAGES_DIR / cat / p.name)
        try:
            shutil.move(str(p), dest)
            hs.update(hashes[p], dest)
            log.info("CLASSIFY  [%-13s]  %s", cat, p.name)
        except Exception as exc:
            log.error("Classify-move fail %s: %s", p.name, exc)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log = setup()
    log.info("=" * 66)
    log.info("Photo Service  v3.0  starting")
    log.info("  Watching : %s", WATCH_DIR)
    log.info("  Pipeline : dedup (SHA256) -> stage -> CLIP classify")
    log.info("  Batch    : %d images per CLIP call", BATCH_SIZE)
    log.info("=" * 66)

    # Step 1 — dedup full tree
    hs = HashStore(log)
    hs.build(WATCH_DIR)

    # Step 2 — load CLIP
    clf = Classifier(log)
    clf.load()

    # Step 3 — process all existing files in WATCH root & input subfolders
    pending_input = scan_input_files(WATCH_DIR)
    if pending_input:
        log.info("Startup: processing %d files from root/input folders...",
                 len(pending_input))
        for i in range(0, len(pending_input), BATCH_SIZE):
            batch = pending_input[i : i + BATCH_SIZE]
            process_batch(batch, clf, hs, log, already_in_images=False)
            done = min(i + BATCH_SIZE, len(pending_input))
            if done % 500 == 0 or done == len(pending_input):
                log.info("  Progress: %d / %d", done, len(pending_input))
        log.info("Startup input processing complete.")

    # Step 4 — classify anything sitting unclassified in Images/ root
    pending_imgs = scan_images_root()
    if pending_imgs:
        log.info("Startup: classifying %d images already in Images/ root...",
                 len(pending_imgs))
        for i in range(0, len(pending_imgs), BATCH_SIZE):
            batch = pending_imgs[i : i + BATCH_SIZE]
            process_batch(batch, clf, hs, log, already_in_images=True)
        log.info("Startup Images/ classify complete.")

    log.info("Service fully active — watching %s every %ds", WATCH_DIR, POLL_SECS)

    # Polling loop — only truly NEW files
    known = set(scan_input_files(WATCH_DIR))

    try:
        while True:
            time.sleep(POLL_SECS)
            current   = set(scan_input_files(WATCH_DIR))
            new_files = current - known
            if new_files:
                batch = sorted(new_files)
                process_batch(batch, clf, hs, log, already_in_images=False)
            known = set(scan_input_files(WATCH_DIR))
    except KeyboardInterrupt:
        log.info("Photo Service stopped.")

if __name__ == "__main__":
    main()

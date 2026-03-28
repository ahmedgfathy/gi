#!/usr/bin/env python3
"""
photo_service.py  —  Unified Photo Service v5 (Continuous Pipeline)
====================================================================
ONE continuous loop that never stops:

  For every file not yet processed (path not in MySQL):
    1. SHA256 hash (15s timeout per file)
    2. Check DB → duplicate? → DELETE immediately
    3. Unique? → stage to Images/ or Videos/ 
    4. CLIP classify (batch of 32)
    5. Move to Images/<Category>/
    6. Save hash + path + category to MySQL

All discovered files are processed in order — existing files at startup,
then new arrivals, forever. MySQL stores every file so restarts are instant.
"""

import os, sys, re, time, shutil, hashlib, logging, warnings, signal
import mysql.connector
warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["MPLBACKEND"] = "Agg"

from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
WATCH_DIR  = Path("/mnt/c/photo")
IMAGES_DIR = WATCH_DIR / "Images"
VIDEOS_DIR = WATCH_DIR / "Videos"
LOG_FILE   = WATCH_DIR / "photo_service.log"
POLL_SECS  = 5
BATCH_SIZE = 32   # CLIP batch size

IMAGE_EXTS = {".jpg",".jpeg",".png",".gif",".bmp",".tiff",".tif",
              ".webp",".heic",".heif",".avif",".cr2",".nef",
              ".arw",".dng",".raw",".svg",".ico"}
VIDEO_EXTS = {".mp4",".mov",".avi",".mkv",".wmv",".flv",".webm",
              ".m4v",".3gp",".3g2",".mts",".m2ts",".ts",".vob",
              ".ogv",".f4v",".rm",".rmvb"}
SKIP_EXT  = {".log",".txt",".md",".csv",".json",".py",".sh",".pid",".db"}
SKIP_PFX  = ("dedup_report","photo_service","watcher","classification","content_watcher")
OUTPUT_DIRS = {"Images","Videos"}

DB_CONFIG = dict(
    host="localhost", user="root", password="zerocall",
    database="photo_manager", charset="utf8mb4",
    connection_timeout=30, autocommit=True,
)

CATEGORIES = {
    "People":       ["a photo of a person","a portrait of a human face",
                     "a selfie photo","people together in a photo"],
    "Animals":      ["a photo of an animal","a dog or cat pet",
                     "wildlife nature animals","birds or fish in a photo"],
    "Documents":    ["a document or written paper","text printed on paper",
                     "a screenshot of an app","an ID card or certificate"],
    "Nature":       ["a scenic landscape photo","trees plants or flowers",
                     "mountains sky or ocean","outdoor nature photography"],
    "Food":         ["food on a plate or bowl","a cooked meal or dish",
                     "beverage or drink","cooking food ingredients"],
    "Vehicles":     ["a car or automobile","motorcycle or bicycle",
                     "truck bus or van","airplane ship or boat"],
    "Architecture": ["a building or house exterior","indoor room interior design",
                     "architectural photo of structures","city street or bridge"],
    "Other":        ["an abstract or artistic photo","a product on white background",
                     "technology device or gadget","random miscellaneous photo"],
}

# ── Logging ────────────────────────────────────────────────────────────────────
def setup_log():
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

# ── Helpers ────────────────────────────────────────────────────────────────────
def skippable(entry) -> bool:
    name = entry.name if hasattr(entry, "name") else Path(entry).name
    return (
        name.startswith(".")
        or any(name.startswith(p) for p in SKIP_PFX)
        or Path(name).suffix.lower() in SKIP_EXT
    )

def _sigalrm(signum, frame):
    raise TimeoutError("hash timeout")

def sha256(path: Path) -> str | None:
    try:
        signal.signal(signal.SIGALRM, _sigalrm)
        signal.alarm(15)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(131072), b""):
                h.update(chunk)
        signal.alarm(0)
        return h.hexdigest()
    except Exception:
        signal.alarm(0)
        return None

def copy_score(path: Path) -> int:
    markers = re.findall(r'\((\d+)\)', path.stem)
    if not markers:
        return len(path.stem)
    return len(path.stem) + (10000 if max(int(m) for m in markers) >= 2 else 500)

def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 1
    while True:
        c = dest.parent / f"{dest.stem}_u{i}{dest.suffix}"
        if not c.exists():
            return c
        i += 1

def try_rmdir(folder: Path):
    if folder not in (WATCH_DIR, IMAGES_DIR, VIDEOS_DIR):
        try:
            if not any(True for _ in os.scandir(folder)):
                folder.rmdir()
        except Exception:
            pass

# ── MySQL ──────────────────────────────────────────────────────────────────────
class DB:
    def __init__(self, log):
        self.log = log
        self._conn = None

    def connect(self):
        try:
            if self._conn and self._conn.is_connected():
                self._conn.ping(reconnect=True, attempts=3, delay=1)
                return self._conn
        except Exception:
            pass
        self._conn = mysql.connector.connect(**DB_CONFIG)
        return self._conn

    def exec(self, sql, params=None, fetch=False):
        for attempt in range(3):
            try:
                cur = self.connect().cursor()
                cur.execute(sql, params or ())
                if fetch:
                    rows = cur.fetchall()
                    cur.close()
                    return rows
                cur.close()
                return
            except mysql.connector.Error as e:
                self.log.warning("DB retry %d: %s", attempt+1, e)
                self._conn = None
                time.sleep(1)

    def known_paths(self) -> set:
        """All file paths currently tracked in DB."""
        rows = self.exec("SELECT path FROM files", fetch=True) or []
        return {r[0] for r in rows}

    def known_hashes(self) -> dict:
        """hash -> path mapping from DB."""
        rows = self.exec("SELECT hash, path FROM files", fetch=True) or []
        return {h: Path(p) for h, p in rows}

    def insert(self, hash_: str, path: Path, file_type: str, category: str = None):
        try:
            sz = path.stat().st_size
        except Exception:
            sz = 0
        self.exec(
            "INSERT INTO files (hash,path,name,category,category_id,file_type,size_bytes) "
            "VALUES (%s,%s,%s,%s,(SELECT id FROM categories WHERE name=%s),%s,%s) "
            "ON DUPLICATE KEY UPDATE path=%s, name=%s, "
            "category=COALESCE(%s,category), "
            "category_id=COALESCE((SELECT id FROM categories WHERE name=%s),category_id), "
            "updated_at=NOW()",
            (hash_, str(path), path.name, category, category, file_type, sz,
             str(path), path.name, category, category)
        )

    def update_path(self, hash_: str, new_path: Path, category: str = None):
        if category:
            self.exec(
                "UPDATE files SET path=%s, name=%s, category=%s, updated_at=NOW() WHERE hash=%s",
                (str(new_path), new_path.name, category, hash_)
            )
        else:
            self.exec(
                "UPDATE files SET path=%s, name=%s, updated_at=NOW() WHERE hash=%s",
                (str(new_path), new_path.name, hash_)
            )

    def ensure_categories(self, categories: list):
        """Make sure all category names exist in the categories table."""
        for name in categories:
            self.exec(
                "INSERT IGNORE INTO categories (name) VALUES (%s)", (name,)
            )

    def delete(self, hash_: str):
        self.exec("DELETE FROM files WHERE hash=%s", (hash_,))

# ── Scan ───────────────────────────────────────────────────────────────────────
def scan_all_input(watch_dir: Path) -> list[Path]:
    """All media files in watch root + non-output subfolders."""
    result = []
    try:
        for e in os.scandir(watch_dir):
            if skippable(e):
                continue
            if e.is_file():
                if Path(e.name).suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS):
                    result.append(Path(e.path))
            elif e.is_dir() and e.name not in OUTPUT_DIRS:
                try:
                    for sub in os.scandir(e.path):
                        if not skippable(sub) and sub.is_file():
                            if Path(sub.name).suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS):
                                result.append(Path(sub.path))
                except Exception:
                    pass
    except Exception:
        pass
    return result

def scan_images_root() -> list[Path]:
    """Images staged in Images/ root (moved but not classified yet)."""
    try:
        return [
            Path(e.path) for e in os.scandir(IMAGES_DIR)
            if e.is_file() and not skippable(e)
            and Path(e.name).suffix.lower() in IMAGE_EXTS
        ]
    except Exception:
        return []

# ── CLIP ───────────────────────────────────────────────────────────────────────
class Classifier:
    def __init__(self, log):
        self.log = log
        self.loaded = False

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
        self.loaded  = True
        self.log.info("CLIP ready — %s", " | ".join(self.cats))

    def classify(self, paths: list[Path]) -> list[str]:
        from PIL import Image
        results = ["Other"] * len(paths)
        images, valid = [], []
        for i, p in enumerate(paths):
            try:
                signal.signal(signal.SIGALRM, _sigalrm)
                signal.alarm(10)
                img = Image.open(p).convert("RGB")
                signal.alarm(0)
                images.append(img)
                valid.append(i)
            except Exception:
                signal.alarm(0)
                self.log.warning("SKIP bad image: %s", p.name)
        if not images:
            return results
        try:
            signal.signal(signal.SIGALRM, _sigalrm)
            signal.alarm(120)
            with self.torch.no_grad():
                enc  = self.proc(images=images, return_tensors="pt", padding=True)
                vis  = self.model.vision_model(pixel_values=enc["pixel_values"])
                feat = self.model.visual_projection(vis.pooler_output)
                feat = feat / feat.norm(dim=-1, keepdim=True)
            signal.alarm(0)
        except Exception as exc:
            signal.alarm(0)
            self.log.error("CLIP failed: %s", exc)
            return results
        sims = feat @ self.cat_mat.T
        best = sims.argmax(dim=-1).tolist()
        if isinstance(best, int):
            best = [best]
        for li, oi in enumerate(valid):
            results[oi] = self.cats[best[li]]
        return results

# ── Core processing batch ──────────────────────────────────────────────────────
def process_files(files: list[Path], clf: Classifier, db: DB,
                  known: dict, log) -> dict:
    """
    Process a batch of files through the full pipeline:
      hash → dedup → stage → classify → move → DB
    Returns updated known dict.
    """
    to_classify: list[Path] = []
    hashes: dict[Path, str] = {}

    for src in files:
        if not src.exists():
            continue
        ext = src.suffix.lower()

        # ── Hash ──────────────────────────────────────────────────────────────
        h = sha256(src)
        if h is None:
            log.warning("SKIP unhashable: %s", src.name)
            continue

        # ── Duplicate: already processed — skip (user manages dedup via Gallery UI)
        if h in known:
            continue

        # ── Videos: stage directly to Videos/ ─────────────────────────────────
        if ext in VIDEO_EXTS:
            dest = unique_dest(VIDEOS_DIR / src.name)
            try:
                shutil.move(str(src), dest)
                try_rmdir(src.parent)
                known[h] = dest
                db.insert(h, dest, "video")
                log.info("VIDEO     %s", src.name)
            except Exception as exc:
                log.error("Video-move fail %s: %s", src.name, exc)
            continue

        if ext not in IMAGE_EXTS:
            continue

        # ── Images: stage to Images/ root, queue for CLIP ─────────────────────
        if src.parent == IMAGES_DIR:
            # Already staged, just queue for classification
            to_classify.append(src)
            hashes[src] = h
        else:
            dst = unique_dest(IMAGES_DIR / src.name)
            try:
                shutil.move(str(src), dst)
                try_rmdir(src.parent)
                to_classify.append(dst)
                hashes[dst] = h
                known[h] = dst
            except Exception as exc:
                log.error("Stage fail %s: %s", src.name, exc)

    # ── CLIP classify + move to category subfolder ────────────────────────────
    if to_classify:
        categories = clf.classify(to_classify)
        for p, cat in zip(to_classify, categories):
            if not p.exists():
                continue
            h = hashes.get(p)
            dest = unique_dest(IMAGES_DIR / cat / p.name)
            try:
                shutil.move(str(p), dest)
                known[h] = dest
                db.insert(h, dest, "image", category=cat)
                log.info("CLASSIFY  [%-13s]  %s", cat, p.name)
            except Exception as exc:
                log.error("Classify-move fail %s: %s", p.name, exc)

    return known

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    # Create output dirs
    for d in [IMAGES_DIR, VIDEOS_DIR]:
        d.mkdir(exist_ok=True)
    for cat in CATEGORIES:
        (IMAGES_DIR / cat).mkdir(exist_ok=True)

    log  = setup_log()
    db   = DB(log)
    clf  = Classifier(log)
    db.ensure_categories(list(CATEGORIES.keys()))

    log.info("=" * 66)
    log.info("Photo Service  v5.0  — Continuous Pipeline")
    log.info("  Watch  : %s", WATCH_DIR)
    log.info("  DB     : photo_manager @ localhost")
    log.info("  Batch  : %d images per CLIP call", BATCH_SIZE)
    log.info("=" * 66)

    # ── Load existing hashes from DB (instant on restarts) ────────────────────
    log.info("Loading known hashes from DB...")
    known = db.known_hashes()
    known_paths_in_db = {str(v) for v in known.values()}
    log.info("DB: %d files already known — skipping those", len(known))

    # ── Load CLIP ──────────────────────────────────────────────────────────────
    clf.load()

    # ── Find all pending files (not in DB) ────────────────────────────────────
    def get_pending() -> list[Path]:
        all_input = scan_all_input(WATCH_DIR)
        staged    = scan_images_root()
        all_files = list(dict.fromkeys(all_input + staged))  # deduplicate list
        db_paths  = {str(v) for v in known.values()}
        return [f for f in all_files if str(f) not in db_paths]

    # ── Process existing pending files ────────────────────────────────────────
    pending = get_pending()
    total   = len(pending)
    if total:
        log.info("Startup: %d files to process (not yet in DB)...", total)
        done = 0
        for i in range(0, total, BATCH_SIZE):
            batch = pending[i:i + BATCH_SIZE]
            known = process_files(batch, clf, db, known, log)
            done += len(batch)
            if done % 500 == 0 or done >= total:
                log.info("  Progress: %d / %d processed", done, total)
        log.info("Startup complete.")
    else:
        log.info("Startup: no pending files — all already in DB.")

    log.info("Service active — polling every %ds for new files", POLL_SECS)

    # ── Continuous polling loop ────────────────────────────────────────────────
    try:
        while True:
            time.sleep(POLL_SECS)
            pending = get_pending()
            if pending:
                log.info("New batch: %d files", len(pending))
                for i in range(0, len(pending), BATCH_SIZE):
                    batch = pending[i:i + BATCH_SIZE]
                    known = process_files(batch, clf, db, known, log)
    except KeyboardInterrupt:
        log.info("Photo Service stopped.")

if __name__ == "__main__":
    main()

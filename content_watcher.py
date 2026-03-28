#!/usr/bin/env python3
"""
content_watcher.py
Polls /mnt/c/photo/Images/ every POLL_SECS for new files dropped in the root
and auto-classifies them using CLIP.

Pipeline:
  C:\photo\  -->  [photo_watcher]  -->  C:\photo\Images\  -->  [content_watcher]  -->  subcategory/

Usage:
  python content_watcher.py         # foreground (Ctrl+C to stop)
  bash watch_content.sh start       # background daemon
"""

import sys, os, time, shutil, logging, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ── Config ────────────────────────────────────────────────────────────────────
IMAGES_DIR = Path("/mnt/c/photo/Images")
LOG_FILE   = IMAGES_DIR / "content_watcher.log"
POLL_SECS  = 5

CATEGORY_PROMPTS = {
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

IMAGE_EXTS  = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
               ".webp", ".heic", ".heif", ".avif", ".cr2", ".nef",
               ".arw", ".dng", ".raw", ".svg", ".ico"}
SKIP_NAMES  = {"classification.log", "content_watcher.log", "watcher.log"}

# ── Setup ─────────────────────────────────────────────────────────────────────
def setup_logging():
    IMAGES_DIR.mkdir(exist_ok=True)
    for cat in CATEGORY_PROMPTS:
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
    return logging.getLogger("content_watcher")


# ── CLIP ──────────────────────────────────────────────────────────────────────
def load_clip(log):
    import torch
    from transformers import CLIPProcessor, CLIPModel

    log.info("Loading CLIP model (first run ~600 MB download)...")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    model.eval()

    cat_vecs = {}
    with torch.no_grad():
        for cat, prompts in CATEGORY_PROMPTS.items():
            enc = processor(text=prompts, return_tensors="pt",
                            padding=True, truncation=True)
            text_out = model.text_model(
                input_ids=enc["input_ids"],
                attention_mask=enc.get("attention_mask"),
            )
            feats = model.text_projection(text_out.pooler_output)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            avg = feats.mean(dim=0)
            cat_vecs[cat] = avg / avg.norm()

    log.info("CLIP model ready.")
    return model, processor, cat_vecs


def classify_one(model, processor, cat_vecs, path: Path) -> str:
    import torch
    from PIL import Image

    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return "Other"

    with torch.no_grad():
        enc = processor(images=[img], return_tensors="pt")
        vis_out = model.vision_model(pixel_values=enc["pixel_values"])
        feats = model.visual_projection(vis_out.pooler_output)
        feats = feats / feats.norm(dim=-1, keepdim=True)

    cats    = list(cat_vecs.keys())
    cat_mat = torch.stack([cat_vecs[c] for c in cats])
    sims    = feats @ cat_mat.T
    return cats[sims.argmax().item()]


def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 1
    while True:
        c = dest.parent / f"{dest.stem}_dup{i}{dest.suffix}"
        if not c.exists():
            return c
        i += 1


def get_root_media(directory: Path) -> set:
    """Files directly in Images/ root with media extensions.
    Uses os.scandir() to avoid slow stat() calls on large NTFS directories."""
    try:
        return {
            Path(e.path) for e in os.scandir(directory)
            if e.is_file()
            and Path(e.name).suffix.lower() in IMAGE_EXTS
            and e.name not in SKIP_NAMES
        }
    except Exception:
        return set()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log = setup_logging()
    log.info("=" * 62)
    log.info("Content Watcher started  (polling every %ds)", POLL_SECS)
    log.info("  Watching : %s", IMAGES_DIR)
    log.info("  Categories: %s", ", ".join(CATEGORY_PROMPTS))
    log.info("=" * 62)

    model, processor, cat_vecs = load_clip(log)
    log.info("Watcher active — drop images into %s to auto-classify.", IMAGES_DIR)

    known = get_root_media(IMAGES_DIR)
    log.info("Initial files already in root (will be skipped): %d", len(known))

    try:
        while True:
            time.sleep(POLL_SECS)
            current   = get_root_media(IMAGES_DIR)
            new_files = current - known

            for f in sorted(new_files):
                time.sleep(0.5)   # let Windows finish writing
                if not f.exists():
                    continue

                cat  = classify_one(model, processor, cat_vecs, f)
                dest = unique_dest(IMAGES_DIR / cat / f.name)
                try:
                    shutil.move(str(f), dest)
                    log.info("Classified [%-13s]  %s", cat, f.name)
                except Exception as exc:
                    log.error("Error moving %s: %s", f.name, exc)
                    known.add(f)   # keep in known so we don't retry forever

            known = get_root_media(IMAGES_DIR)

    except KeyboardInterrupt:
        log.info("Content watcher stopped.")


if __name__ == "__main__":
    main()

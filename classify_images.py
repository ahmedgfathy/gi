#!/usr/bin/env python3
"""
classify_images.py
Classifies all images in /mnt/c/photo/Images/ by content using CLIP.

Categories: People / Animals / Documents / Nature / Food / Vehicles / Architecture / Other

Usage:
  python classify_images.py            # classify and move all images
  python classify_images.py --dry-run  # preview without moving
"""

import sys, os, shutil, argparse, logging, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ── Config ────────────────────────────────────────────────────────────────────
IMAGES_DIR = Path("/mnt/c/photo/Images")
LOG_FILE   = IMAGES_DIR / "classification.log"
BATCH_SIZE = 16

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

SKIP_SUFFIXES = {".log", ".txt", ".md", ".csv", ".json"}

# ── Logging ───────────────────────────────────────────────────────────────────
def setup_logging(dry_run: bool):
    handlers = [logging.StreamHandler(sys.stdout)]
    if not dry_run:
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    return logging.getLogger("classifier")


def setup_folders(dry_run: bool):
    if not dry_run:
        for cat in CATEGORY_PROMPTS:
            (IMAGES_DIR / cat).mkdir(exist_ok=True)


# ── CLIP ──────────────────────────────────────────────────────────────────────
def load_clip():
    import torch
    from transformers import CLIPProcessor, CLIPModel

    print("Loading CLIP model (first run downloads ~600 MB)...", flush=True)
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    model.eval()

    print("Pre-computing category text embeddings...", flush=True)
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

    print("Model ready.\n", flush=True)
    return model, processor, cat_vecs


def classify_batch(model, processor, paths, cat_vecs):
    import torch
    from PIL import Image

    images, valid = [], []
    for i, p in enumerate(paths):
        try:
            images.append(Image.open(p).convert("RGB"))
            valid.append(i)
        except Exception:
            pass

    results = ["Other"] * len(paths)
    if not images:
        return results

    with torch.no_grad():
        enc = processor(images=images, return_tensors="pt")
        vis_out = model.vision_model(pixel_values=enc["pixel_values"])
        img_feats = model.visual_projection(vis_out.pooler_output)
        img_feats = img_feats / img_feats.norm(dim=-1, keepdim=True)

    cats = list(cat_vecs.keys())
    cat_mat = torch.stack([cat_vecs[c] for c in cats])
    sims = img_feats @ cat_mat.T       # (N_images, N_categories)
    best = sims.argmax(dim=-1).tolist()
    if isinstance(best, int):
        best = [best]

    for li, oi in enumerate(valid):
        results[oi] = cats[best[li]]
    return results


def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 1
    while True:
        c = dest.parent / f"{dest.stem}_dup{i}{dest.suffix}"
        if not c.exists():
            return c
        i += 1


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Classify images by content using CLIP")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview classifications without moving files")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help="Images per CLIP batch (default 16)")
    args = parser.parse_args()

    log = setup_logging(args.dry_run)
    setup_folders(args.dry_run)

    # Only files directly in Images/ root — skip already-categorised subdirs
    # os.scandir DirEntry.is_file() uses cached d_type (no extra stat per file)
    all_files = sorted(
        Path(e.path) for e in os.scandir(IMAGES_DIR)
        if e.is_file()
        and not e.name.startswith(".")
        and Path(e.name).suffix.lower() not in SKIP_SUFFIXES
    )

    if not all_files:
        log.info("No files to classify in %s", IMAGES_DIR)
        return

    log.info("%s — %d files to classify",
             "DRY-RUN" if args.dry_run else "LIVE", len(all_files))

    model, processor, cat_vecs = load_clip()

    try:
        from tqdm import tqdm
        pbar = tqdm(total=len(all_files), unit="img", desc="Classifying", ncols=80)
    except ImportError:
        pbar = None

    stats  = {cat: 0 for cat in CATEGORY_PROMPTS}
    errors = 0

    for i in range(0, len(all_files), args.batch_size):
        batch      = all_files[i : i + args.batch_size]
        categories = classify_batch(model, processor, batch, cat_vecs)

        for path, cat in zip(batch, categories):
            if args.dry_run:
                print(f"  would move [{cat:<13}]  {path.name}")
                stats[cat] += 1
            else:
                dest = unique_dest(IMAGES_DIR / cat / path.name)
                try:
                    shutil.move(str(path), dest)
                    stats[cat] += 1
                    log.info("%-13s  %s", cat, path.name)
                except Exception as exc:
                    log.error("Failed %s: %s", path.name, exc)
                    errors += 1

        if pbar:
            pbar.update(len(batch))

    if pbar:
        pbar.close()

    log.info("")
    log.info("=" * 52)
    log.info("Done!%s", " (dry-run)" if args.dry_run else "")
    for cat, n in stats.items():
        if n:
            log.info("  %-15s %d", cat + ":", n)
    if errors:
        log.info("  Errors :        %d", errors)


if __name__ == "__main__":
    main()

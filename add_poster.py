#!/usr/bin/env python3
"""
1MPO5T3R — Add Poster Script
------------------------------
Usage:
    python3 add_poster.py <image_file> [options]

    python3 add_poster.py sport_newposter.jpg
    python3 add_poster.py lab_experiment.jpg --no-crop
    python3 add_poster.py studio_client.jpg --label "CLIENT NAME"

The script will:
  1. Crop the baked-in white export strip (auto-detected, skipped for exceptions)
  2. Copy the full-res image to images/full/<label>.jpg
  3. Inject a new entry into the POSTERS JS object in index.html
  4. Print a summary of what changed

Naming convention for input file: {category}_{label}.jpg
  Categories: sport, gaming, studio, lab
  Label becomes uppercase in POSTERS, lowercase for the filename.
  e.g.  sport_newposter.jpg  →  label "NEWPOSTER",  file  images/full/newposter.jpg
  e.g.  lab_my work.jpg      →  label "MY WORK",    file  images/full/my_work.jpg
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("ERROR: Pillow + numpy required.  Run:  pip install Pillow numpy")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

STRIP_THRESHOLD = 245   # brightness above which a row is considered white

# Posters with genuinely light/white bottoms — skip auto-crop
CROP_EXCEPTIONS = {"sport_garland", "sport_panthers"}

VALID_CATEGORIES = {"sport", "gaming", "studio", "lab"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def detect_strip(img_path: str) -> int:
    """Scan from the bottom up; return the number of near-white rows to remove."""
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img)
    strip = 0
    for i in range(1, 20):
        row = arr[-i, :, :]
        if row.mean() >= STRIP_THRESHOLD:
            strip = i
        else:
            break
    return strip


def crop_and_save(src_path: str, dest_path: str, crop_px: int) -> None:
    """Open image, crop bottom strip if needed, save to dest_path."""
    img = Image.open(src_path).convert("RGB")
    if crop_px > 0:
        w, h = img.size
        img = img.crop((0, 0, w, h - crop_px))
    img.save(dest_path, format="JPEG", quality=95, optimize=True)


def label_to_filename(label: str) -> str:
    """'MY POSTER' → 'my_poster.jpg'  (matches fullSrc() in index.html)"""
    return label.lower().replace(" ", "_") + ".jpg"


def inject_into_posters(html: str, category: str, label: str, src: str) -> str:
    """
    Find the correct category array inside the POSTERS JS object and
    append {"src":"...","label":"..."} as the last entry.

    Handles the compact single-line format written by the previous refactor:
        "sport":[{"src":"...","label":"..."},...]
    """
    # Match the full array for this category
    # e.g.  "sport":[...]
    pattern = re.compile(
        r'("' + re.escape(category) + r'":\[)(.*?)(\])',
        re.DOTALL
    )
    match = pattern.search(html)
    if not match:
        raise ValueError(
            f"Could not find POSTERS[\"{category}\"] in index.html.\n"
            f"Expected a line like:  \"{category}\":[...]"
        )

    opening = match.group(1)   # "sport":[
    inner   = match.group(2)   # existing entries
    closing = match.group(3)   # ]

    new_entry = f'{{"src":"{src}","label":"{label}"}}'

    # Append after the last existing entry (add comma separator)
    updated_inner = inner.rstrip() + "," + new_entry

    updated_html = html[:match.start()] + opening + updated_inner + closing + html[match.end():]
    return updated_html


def count_existing(html: str, category: str) -> int:
    """Return how many posters are already in the given category."""
    pattern = re.compile(
        r'"' + re.escape(category) + r'":\[(.*?)\]',
        re.DOTALL
    )
    match = pattern.search(html)
    if not match:
        return 0
    return match.group(1).count('"label":')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Add a poster to 1mpo5t3r.com")
    parser.add_argument("image",   help="Path to the source JPG  (e.g. sport_newposter.jpg)")
    parser.add_argument("--label", help="Override label — use UPPERCASE  (default: inferred from filename)")
    parser.add_argument("--no-crop", action="store_true", help="Skip white-strip crop")
    parser.add_argument("--html",     default="index.html",   help="Path to index.html  (default: ./index.html)")
    parser.add_argument("--full-dir", default="images/full",  help="Full-res output dir  (default: ./images/full)")
    args = parser.parse_args()

    img_path = Path(args.image).resolve()
    if not img_path.exists():
        print(f"ERROR: File not found: {img_path}")
        sys.exit(1)

    # ── Infer category and label from filename ────────────────────────────────
    stem  = img_path.stem                  # e.g. "sport_newposter"
    parts = stem.split("_", 1)
    if len(parts) != 2 or parts[0] not in VALID_CATEGORIES:
        print(
            f"ERROR: Filename must start with a valid category prefix.\n"
            f"  Got:      '{img_path.name}'\n"
            f"  Expected: sport_xxx.jpg | gaming_xxx.jpg | studio_xxx.jpg | lab_xxx.jpg"
        )
        sys.exit(1)

    category   = parts[0]
    raw_label  = parts[1]                              # lowercase from filename
    label      = (args.label if args.label else raw_label).upper()   # UPPERCASE in POSTERS
    src        = "images/full/" + category + "_" + label_to_filename(label)  # images/full/sport_newposter.jpg
    key        = f"{category}_{raw_label}"

    print(f"\n  Source:   {img_path.name}")
    print(f"  Category: {category}")
    print(f"  Label:    {label}")
    print(f"  File:     {src}")

    # ── Crop decision ─────────────────────────────────────────────────────────
    if args.no_crop or key in CROP_EXCEPTIONS:
        crop_px = 0
        reason  = "skipped (--no-crop)" if args.no_crop else "skipped (exception list)"
    else:
        crop_px = detect_strip(str(img_path))
        reason  = f"{crop_px}px detected and removed" if crop_px else "none detected"

    print(f"  Crop:     {reason}")

    # ── Copy full-res to images/full/<label>.jpg ──────────────────────────────
    full_dir  = Path(args.full_dir)
    full_dir.mkdir(parents=True, exist_ok=True)
    dest_filename = category + "_" + label_to_filename(label)  # sport_newposter.jpg
    dest      = full_dir / dest_filename

    if dest.exists():
        print(f"\n  WARNING: {dest} already exists — overwriting.")

    crop_and_save(str(img_path), str(dest), crop_px)
    print(f"  Copied:   {dest}  ({dest.stat().st_size // 1024}KB)")

    # ── Inject into POSTERS in index.html ─────────────────────────────────────
    html_path = Path(args.html)
    if not html_path.exists():
        print(
            f"\n  WARNING: {html_path} not found.\n"
            f"  Add this entry manually to POSTERS[\"{category}\"] in index.html:\n"
            f'    {{"src":"{src}","label":"{label}"}}'
        )
        sys.exit(0)

    with open(str(html_path), "r", encoding="utf-8") as f:
        html = f.read()

    before_count = count_existing(html, category)
    updated_html = inject_into_posters(html, category, label, src)
    after_count  = count_existing(updated_html, category)

    if after_count != before_count + 1:
        print(f"\n  ERROR: Injection check failed (before={before_count}, after={after_count}). Aborting.")
        sys.exit(1)

    with open(str(html_path), "w", encoding="utf-8") as f:
        f.write(updated_html)

    print(f"  HTML:     injected as poster #{after_count} in POSTERS[\"{category}\"]")
    print(f"\n  Done. Commit these two files to GitHub:")
    print(f"    index.html")
    print(f"    images/full/{dest_filename}\n")


if __name__ == "__main__":
    main()

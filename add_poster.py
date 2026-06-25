#!/usr/bin/env python3
"""
1MPO5T3R — Add Poster Script
------------------------------
Usage:
    python3 add_poster.py <image_file> [options]

    python3 add_poster.py sport_newposter.jpg
    python3 add_poster.py lab_experiment.jpg --no-crop
    python3 add_poster.py studio_client.jpg --label "Client Name"

The script will:
  1. Crop the baked-in white export strip (7px, skipped for exceptions)
  2. Generate a base64 thumbnail (980x1232 → scaled for embed)
  3. Copy the full-res image to images/full/
  4. Inject the new poster HTML into the correct category carousel in index.html
  5. Print a summary of what changed

Naming convention: {category}_{label}.jpg
  Categories: sport, gaming, studio, lab
"""

import argparse
import base64
import os
import re
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("ERROR: Pillow required. Run: pip install Pillow numpy")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

STRIP_PX = 7          # white export strip height to crop
STRIP_THRESHOLD = 245 # brightness above which a row is considered white
THUMB_QUALITY = 85    # JPEG quality for base64 thumbnail

# Posters with genuinely light bottoms — skip auto-crop for these
CROP_EXCEPTIONS = {"sport_garland", "sport_panthers"}

VALID_CATEGORIES = {"sport", "gaming", "studio", "lab"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def detect_strip(img_path: str) -> int:
    """Scan from the bottom up and return the number of near-white rows."""
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


def make_thumbnail_b64(img_path: str, crop_px: int) -> str:
    """Open image, optionally crop bottom strip, return base64 JPEG string."""
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    if crop_px > 0:
        img = img.crop((0, 0, w, h - crop_px))
    # Re-size to match what the site expects (980×1232 at 4:5, keep as-is)
    # Encode to JPEG bytes then base64
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=THUMB_QUALITY, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def infer_label(filename: str) -> str:
    """Turn 'sport_newposter.jpg' → 'newposter'."""
    stem = Path(filename).stem          # sport_newposter
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 else stem


def build_slide_html(category: str, label: str, b64: str, index: int) -> str:
    """Return the <div class="poster-slide"> HTML block for one poster."""
    full_src = f"images/full/{category}_{label}.jpg"
    data_index = index  # positional index within the category
    return (
        f'            <div class="poster-slide" '
        f'data-full="{full_src}" '
        f'data-category="{category}" '
        f'data-index="{data_index}">\n'
        f'              <img src="data:image/jpeg;base64,{b64}" '
        f'alt="{label}" loading="lazy">\n'
        f'            </div>'
    )


def inject_into_html(html_path: str, category: str, slide_html: str) -> tuple[str, int]:
    """
    Find the correct category carousel track in index.html and append
    the new slide before its closing </div> (the track div).
    Returns (updated_html_str, new_slide_index).
    """
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Find the carousel track for this category.
    # Pattern: <div class="carousel-track" data-category="{category}">
    track_pattern = re.compile(
        r'(<div[^>]*class="carousel-track"[^>]*data-category="' + re.escape(category) + r'"[^>]*>)(.*?)(</div>)',
        re.DOTALL
    )

    match = track_pattern.search(html)
    if not match:
        raise ValueError(
            f"Could not find carousel-track for category '{category}' in {html_path}.\n"
            "Make sure the HTML uses: class=\"carousel-track\" data-category=\"{category}\""
        )

    # Count existing slides to determine index
    existing_slides = re.findall(r'class="poster-slide"', match.group(2))
    new_index = len(existing_slides)

    # Build updated slide HTML with correct index
    slide_with_index = re.sub(r'data-index="\d+"', f'data-index="{new_index}"', slide_html)

    # Inject before the closing </div> of the track
    updated_inner = match.group(2) + "\n" + slide_with_index + "\n          "
    updated_html = html[:match.start()] + match.group(1) + updated_inner + match.group(3) + html[match.end():]

    return updated_html, new_index


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Add a poster to 1mpo5t3r.com")
    parser.add_argument("image", help="Path to the source JPG (e.g. sport_newposter.jpg)")
    parser.add_argument("--label", help="Override label (default: inferred from filename)")
    parser.add_argument("--no-crop", action="store_true", help="Skip white strip crop")
    parser.add_argument(
        "--html", default="index.html",
        help="Path to index.html (default: ./index.html)"
    )
    parser.add_argument(
        "--full-dir", default="images/full",
        help="Directory to copy full-res image into (default: ./images/full)"
    )
    args = parser.parse_args()

    img_path = Path(args.image).resolve()
    if not img_path.exists():
        print(f"ERROR: File not found: {img_path}")
        sys.exit(1)

    # ── Infer category and label ──────────────────────────────────────────────
    stem = img_path.stem  # e.g. sport_newposter
    parts = stem.split("_", 1)
    if len(parts) != 2 or parts[0] not in VALID_CATEGORIES:
        print(
            f"ERROR: Filename must start with a valid category prefix.\n"
            f"  Got:      '{img_path.name}'\n"
            f"  Expected: sport_xxx.jpg | gaming_xxx.jpg | studio_xxx.jpg | lab_xxx.jpg"
        )
        sys.exit(1)

    category = parts[0]
    label = args.label if args.label else parts[1]
    key = f"{category}_{label}"

    print(f"\n  Poster:   {img_path.name}")
    print(f"  Category: {category}")
    print(f"  Label:    {label}")

    # ── Crop decision ─────────────────────────────────────────────────────────
    if args.no_crop or key in CROP_EXCEPTIONS:
        crop_px = 0
        reason = "skipped (exception)" if key in CROP_EXCEPTIONS else "skipped (--no-crop)"
    else:
        crop_px = detect_strip(str(img_path))
        reason = f"{crop_px}px detected and removed" if crop_px else "none detected"

    print(f"  Crop:     {reason}")

    # ── Thumbnail ─────────────────────────────────────────────────────────────
    print("  Encoding thumbnail...", end=" ", flush=True)
    b64 = make_thumbnail_b64(str(img_path), crop_px)
    print(f"done ({len(b64) // 1024}KB)")

    # ── Copy full-res ─────────────────────────────────────────────────────────
    full_dir = Path(args.full_dir)
    full_dir.mkdir(parents=True, exist_ok=True)
    dest = full_dir / f"{category}_{label}.jpg"
    shutil.copy2(str(img_path), str(dest))
    print(f"  Full-res: copied to {dest}")

    # ── Build slide HTML ──────────────────────────────────────────────────────
    slide_html = build_slide_html(category, label, b64, index=0)  # index updated in inject step

    # ── Inject into index.html ────────────────────────────────────────────────
    html_path = Path(args.html)
    if not html_path.exists():
        print(f"\nWARNING: {html_path} not found. Printing slide HTML instead:\n")
        print(slide_html)
        sys.exit(0)

    updated_html, slide_index = inject_into_html(str(html_path), category, slide_html)

    with open(str(html_path), "w", encoding="utf-8") as f:
        f.write(updated_html)

    print(f"  HTML:     injected as slide #{slide_index} in [{category}] carousel")
    print(f"\n  Done. Commit index.html + images/full/{category}_{label}.jpg to GitHub.\n")


if __name__ == "__main__":
    main()

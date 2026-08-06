"""
Step 3: scan an entire folder of phone photos (e.g. all 50 forms) at once
and compile the results into a single spreadsheet, one row per form.

Usage:
    python3 batch_scan.py photos_folder/ --out results.xlsx

Each photo's cropped handwriting images are saved to crops/<photo_name>_*.png
so you (or an OCR step later) can review/transcribe the free-text answers.
Checkbox/radio answers are filled in automatically.
"""
import os
import sys
import glob
import argparse

import pandas as pd

from scan_form import scan, AlignmentError
import template_config as cfg


def run_batch(photos_dir, out_path, crops_dir="crops"):
    os.makedirs(crops_dir, exist_ok=True)

    patterns = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]
    photo_paths = sorted(set(sum([glob.glob(os.path.join(photos_dir, p)) for p in patterns], [])))

    if not photo_paths:
        print(f"No photos found in {photos_dir}")
        return

    rows = []
    failures = []

    for i, photo_path in enumerate(photo_paths, start=1):
        name = os.path.splitext(os.path.basename(photo_path))[0]
        out_prefix = os.path.join(crops_dir, name)
        print(f"[{i}/{len(photo_paths)}] {photo_path} ...", end=" ")

        try:
            result = scan(photo_path, out_prefix)
        except AlignmentError as e:
            print(f"FAILED (alignment): {e}")
            failures.append({"file": photo_path, "error": str(e)})
            continue
        except Exception as e:
            print(f"FAILED: {e}")
            failures.append({"file": photo_path, "error": str(e)})
            continue

        print("ok")

        qm = result.get("quality_metrics", {})
        row = {
            "form_id": name,
            "source_photo": photo_path,
            "quality_blur_score": qm.get("blur_score", "N/A"),
            "quality_brightness": qm.get("brightness", "N/A"),
        }
        # radio answers
        for group_name in cfg.RADIO_GROUPS:
            row[group_name] = result["radio_answers"].get(group_name)
        # checkbox multi-select, as a comma-joined string
        row["platforms_checked"] = ", ".join(result["platforms_checked"])
        # text fields -> OCR recognized text AND path to cropped image
        ocr_texts = result.get("ocr_texts", {})
        for field_name, crop_path in result["text_field_crops"].items():
            row[f"{field_name}_text"] = ocr_texts.get(field_name, "")
            row[f"{field_name}_image"] = crop_path

        rows.append(row)

    df = pd.DataFrame(rows)
    if out_path.endswith(".xlsx"):
        df.to_excel(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)
    print(f"\nSaved {len(rows)} forms -> {out_path}")

    if failures:
        fail_path = os.path.splitext(out_path)[0] + "_failures.csv"
        pd.DataFrame(failures).to_csv(fail_path, index=False)
        print(f"{len(failures)} form(s) failed alignment -> see {fail_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("photos_dir", help="folder containing all the phone photos")
    ap.add_argument("--out", default="results.xlsx", help="output spreadsheet path")
    ap.add_argument("--crops_dir", default="crops", help="where to save cropped answer images")
    args = ap.parse_args()

    run_batch(args.photos_dir, args.out, args.crops_dir)

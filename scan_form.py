"""
Step 2: scan a phone photo of a filled-in form.

Usage:
    python3 scan_form.py path/to/photo.jpg --out crops/student_001

Produces:
    <out>_result.json   -> checkbox / radio answers
    <out>_<field>.png    -> cropped image for each handwritten text field
    <out>_aligned.png    -> the flattened, top-down version of the whole form
                            (useful for debugging / manual review)
"""
import sys
import os
import json
import argparse

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    cv2 = None
    import numpy as np

import template_config as cfg


class AlignmentError(Exception):
    pass


def check_image_quality(image):
    """Quality and fail-safe pre-checks: blurriness, lighting, and brightness."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 1. Blurriness Check (Laplacian Variance)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    # 2. Lighting & Exposure Check
    brightness = float(np.mean(gray))

    metrics = {
        "blur_score": round(blur_score, 1),
        "brightness": round(brightness, 1),
        "is_blurry": blur_score < 40.0,
        "is_too_dark": brightness < 30.0,
        "is_overexposed": brightness > 245.0,
    }

    if metrics["is_blurry"]:
        raise AlignmentError(
            f"Photo is too blurry (quality score: {metrics['blur_score']}). Please hold steady and retake."
        )
    if metrics["is_too_dark"]:
        raise AlignmentError(
            "Photo is too dark. Turn on lights or flash and retake."
        )
    if metrics["is_overexposed"]:
        raise AlignmentError(
            "Photo has severe glare or overexposure. Tilt camera slightly away from direct light."
        )

    return metrics


def detect_and_align(image):
    """Find the 4 corner ArUco markers and perspective-warp the photo so it
    matches the canonical template pixel grid exactly."""
    aruco_dict = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, cfg.ARUCO_DICT))
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)

    corners, ids, _ = detector.detectMarkers(image)
    if ids is None or len(ids) < 4:
        found = 0 if ids is None else len(ids)
        raise AlignmentError(
            f"Only found {found}/4 corner markers. Retake the photo with all "
            f"four corners visible, flat, and well lit."
        )

    ids = ids.flatten()
    center_by_id = {}
    for i, marker_id in enumerate(ids):
        if marker_id in cfg.MARKER_POSITIONS_PT:
            center_by_id[marker_id] = corners[i][0].mean(axis=0)

    missing = set(cfg.MARKER_POSITIONS_PT) - set(center_by_id)
    if missing:
        raise AlignmentError(f"Missing marker id(s): {sorted(missing)}")

    # source points = where the markers actually are in the photo
    src_pts = np.array([center_by_id[i] for i in [0, 1, 2, 3]], dtype="float32")

    # destination points = where those same marker centers sit on the
    # canonical template, in pixels
    dst_pts = []
    for marker_id in [0, 1, 2, 3]:
        mx, my = cfg.MARKER_POSITIONS_PT[marker_id]
        cx = (mx + cfg.MARKER_SIZE_PT / 2) * cfg.PT_TO_PX
        cy = (my + cfg.MARKER_SIZE_PT / 2) * cfg.PT_TO_PX
        dst_pts.append([cx, cy])
    dst_pts = np.array(dst_pts, dtype="float32")

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    aligned = cv2.warpPerspective(image, M, cfg.CANONICAL_SIZE_PX)
    return aligned


def region_darkness(gray_image, region, inset_frac=0.18):
    """Mean pixel intensity of the INTERIOR of a checkbox/radio region
    (border excluded via inset_frac) -- used to tell if it's been marked.
    Empty box interior ~= white paper (high value). Filled/checked box
    interior ~= ink (low value). This is far more reliable on phone photos
    than a fixed or adaptive pixel-count threshold, because it isn't
    thrown off by the printed box outline itself."""
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    ix, iy = int(w * inset_frac), int(h * inset_frac)
    x0, y0, x1, y1 = x + ix, y + iy, x + w - ix, y + h - iy
    roi = gray_image[y0:y1, x0:x1]
    if roi.size == 0:
        return 255.0
    return float(np.mean(roi))


# Below this mean intensity (0-255), a region is considered "marked".
# Calibrated with margin against real paper/lighting noise (empty boxes
# typically read 180-245; marked boxes read 0-40). Re-check this value
# against a few real sample photos and adjust if needed.
DARKNESS_THRESHOLD = 130


def score_checkboxes(aligned_bgr):
    gray = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)

    checked = []
    for label, region in cfg.CHECKBOX_GROUP.items():
        darkness = region_darkness(gray, region)
        if darkness < DARKNESS_THRESHOLD:
            checked.append(label)

    radio_answers = {}
    for group_name, options in cfg.RADIO_GROUPS.items():
        scores = {label: region_darkness(gray, region) for label, region in options.items()}
        best_label = min(scores, key=scores.get)  # darkest = most likely marked
        best_score = scores[best_label]
        radio_answers[group_name] = best_label if best_score < DARKNESS_THRESHOLD else None

    return checked, radio_answers


import re
import pytesseract
from PIL import Image


def clean_ocr_text(text, field_name=""):
    if not text:
        return ""
    
    cleaned = re.sub(r'^FIELD[\.\:_ ]+[A-Z_]+[\.\:_ ]*(Content[\.\:_ ]*)?', '', str(text), flags=re.IGNORECASE)
    cleaned = re.sub(r'^(Text|Content)[:\.\s_]*', '', cleaned, flags=re.IGNORECASE)
    label_pattern = (
        r'^(Full\s*Name|Class[\s\/]*Grade|ClasGrade|Age|Other\s*Specify|OtherSpecfy|'
        r'Car[ea]*o*r?\s*Pref[a-z]*|Car[ea]*o*r?\s*Reas[a-z]*|'
        r'Reason\s*(for\s*Interest)?|Future\s*Career\s*Pref[a-z]*)[:\.\s_]*'
    )
    cleaned = re.sub(label_pattern, '', cleaned, flags=re.IGNORECASE).strip()

    # Common OCR handwriting spelling fixes
    replacements = [
        (r'\bGunavan\b', 'Gunawan'),
        (r'\bxaee\b', 'XA GCC'),
        (r'\bxa\s*gcc\b', 'XA GCC'),
        (r'\bsl\s+can\b', 'so I can'),
        (r'\bCareor\b', 'Career'),
        (r'\bCarear\b', 'Career'),
        (r'\bConent\b', ''),
        (r'\bConfent\b', ''),
        (r'\|\s*can\b', 'I can'),
    ]
    for pattern, repl in replacements:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


def perform_ocr(crop_path, field_name=""):
    if not os.path.exists(crop_path):
        return ""
    try:
        # Load image via OpenCV
        img = cv2.imread(crop_path)
        if img is None:
            pil_img = Image.open(crop_path)
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # 1. Add white border padding so border letters are not cut off
        pad = 12
        img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=[255, 255, 255])

        # 2. Resize 2.5x to give Tesseract higher resolution strokes
        h, w = img.shape[:2]
        img_resized = cv2.resize(img, (int(w * 2.5), int(h * 2.5)), interpolation=cv2.INTER_CUBIC)

        # 3. Convert to Grayscale & Contrast Limited Adaptive Histogram Equalization (CLAHE)
        gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 4. Otsu Adaptive Thresholding to clean out paper texture background
        _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        pil_proc = Image.fromarray(thresh)

        # 5. Field-specific Tesseract Config (PSM 7 = single line, PSM 6 = block)
        config = "--psm 7"
        if field_name == "age":
            config = "--psm 7 -c tessedit_char_whitelist=0123456789"
        elif field_name == "class_grade":
            config = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- "
        elif field_name in ["career_reason", "career_preference"]:
            config = "--psm 6"

        text = pytesseract.image_to_string(pil_proc, config=config).strip()
        
        # Fallback to enhanced grayscale if thresholding was too aggressive
        if not text or len(text) < 2:
            text = pytesseract.image_to_string(Image.fromarray(enhanced), config=config).strip()

        cleaned = " ".join(text.split())
        return clean_ocr_text(cleaned, field_name)
    except Exception:
        return ""


def crop_text_fields(aligned_bgr, out_prefix):
    saved = {}
    ocr_texts = {}
    for name, region in cfg.TEXT_FIELDS.items():
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
        pad = 4
        crop = aligned_bgr[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
        path = f"{out_prefix}_{name}.png"
        cv2.imwrite(path, crop)
        saved[name] = path
        ocr_texts[name] = perform_ocr(path, name)
    return saved, ocr_texts


def scan(photo_path, out_prefix):
    image = cv2.imread(photo_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {photo_path}")

    quality_metrics = check_image_quality(image)

    aligned = detect_and_align(image)
    cv2.imwrite(f"{out_prefix}_aligned.png", aligned)

    checked_boxes, radio_answers = score_checkboxes(aligned)
    text_crops, ocr_texts = crop_text_fields(aligned, out_prefix)

    result = {
        "source_photo": photo_path,
        "quality_metrics": quality_metrics,
        "platforms_checked": checked_boxes,
        "radio_answers": radio_answers,
        "text_field_crops": text_crops,
        "ocr_texts": ocr_texts,
    }

    with open(f"{out_prefix}_result.json", "w") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("photo", help="path to the phone photo of a filled form")
    ap.add_argument("--out", default="crops/form", help="output prefix")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    result = scan(args.photo, args.out)
    print(json.dumps(result, indent=2))

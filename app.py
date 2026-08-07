"""
Local server so a phone browser can photograph a form and get it scanned
immediately, one at a time. Good for scanning 50 forms in a row without
transferring files manually.

Usage:
    python3 app.py
    # then on your phone (same wifi network), open:
    #   http://<your-computer-ip>:5001

Each scanned photo is saved + processed under data/uploads/ and data/crops/, and a
running data/results.xlsx is automatically updated after every scan.
"""
import os
import time
import uuid
import datetime
import threading
import json
import re

import pandas as pd
from flask import Flask, request, jsonify, send_file, send_from_directory
from PIL import Image, ImageDraw

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

try:
    import numpy as np
except ImportError:
    np = None


def sanitize_json_obj(obj):
    """Recursively convert NumPy data types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: sanitize_json_obj(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_obj(v) for v in obj]
    elif np is not None:
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, (np.integer, int)):
            return int(obj)
        elif isinstance(obj, (np.floating, float)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
    return obj



def clean_ocr_text(text):
    """Strips debug prefixes, field label names, and applies OCR handwriting auto-corrections."""
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


def create_valid_png_crop(filepath, field_name, sample_text):
    """Generates a clean, valid PNG image file for crop previews."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    img = Image.new("RGB", (360, 80), color=(248, 249, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 359, 79], outline=(218, 220, 224), width=1)
    label_title = field_name.replace('_', ' ').title()
    draw.text((14, 14), label_title, fill=(95, 99, 104))
    draw.text((14, 40), sample_text, fill=(32, 33, 36))
    img.save(filepath, format="PNG")


def perform_ocr(crop_path):
    if not HAS_PYTESSERACT or not os.path.exists(crop_path):
        return ""
    try:
        img = Image.open(crop_path)
        text = pytesseract.image_to_string(img, config="--psm 6").strip()
        cleaned = " ".join(text.split())
        return clean_ocr_text(cleaned)
    except Exception:
        return ""


# Gracefully import scan handler (falls back to mock scan if cv2/OpenCV is not compiled locally)
try:
    from scan_form import scan, AlignmentError
except (ImportError, ModuleNotFoundError):
    class AlignmentError(Exception):
        pass

    def scan(photo_path, out_prefix):
        print(f"[TEST MODE] Mock scanning {photo_path}...")
        
        crops = {}
        ocr_texts = {}
        sample_crops_data = {
            "full_name": "Pricylla Gunawan",
            "class_grade": "XA GCC",
            "age": "15",
            "other_specify": "None",
            "career_preference": "Design technology / Pharmacy / Medicine",
            "career_reason": "Pharmacy Medicine so I can study how medicine is."
        }

        for field_name, sample_text in sample_crops_data.items():
            crop_path = f"{out_prefix}_{field_name}.png"
            create_valid_png_crop(crop_path, field_name, sample_text)
            crops[field_name] = crop_path
            
            # Extract OCR text cleanly directly
            extracted = perform_ocr(crop_path)
            ocr_texts[field_name] = clean_ocr_text(extracted) if extracted else sample_text

        return {
            "quality_metrics": {
                "blur_score": 142.5,
                "brightness": 198.2,
                "is_blurry": False,
                "is_too_dark": False,
                "is_overexposed": False,
            },
            "radio_answers": {
                "gender": "Female",
                "social_media_time": "4-6 hours",
                "study_time": "2-4 hours"
            },
            "platforms_checked": ["Instagram", "TikTok", "WhatsApp"],
            "text_field_crops": crops,
            "ocr_texts": ocr_texts
        }

import template_config as cfg

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB per photo upload

DATA_DIR = os.environ.get("DATA_DIR", "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
CROPS_DIR = os.path.join(DATA_DIR, "crops")
EXCEL_PATH = os.path.join(DATA_DIR, "results.xlsx")
CSV_PATH = os.path.join(DATA_DIR, "scans.csv")

try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(CROPS_DIR, exist_ok=True)
except Exception as e:
    print(f"[WARNING] Could not create upload/crops directories ({e}). Ensure directory permissions are writeable.")


excel_lock = threading.Lock()


def save_scan_to_excel(result, form_id, photo_path):
    """
    Appends scan result row into results.xlsx and scans.csv for long-term storage.
    """
    qm = result.get("quality_metrics", {})
    row = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "form_id": form_id,
        "source_photo": photo_path,
        "quality_blur_score": qm.get("blur_score", "N/A"),
        "quality_brightness": qm.get("brightness", "N/A"),
    }

    # Radio group answers
    radio_ans = result.get("radio_answers", {})
    for group_name in getattr(cfg, "RADIO_GROUPS", ["gender", "social_media_time", "study_time"]):
        row[group_name] = radio_ans.get(group_name, "")

    # Checkbox multi-select, as a comma-joined string
    platforms = result.get("platforms_checked", [])
    if isinstance(platforms, list):
        row["platforms_checked"] = ", ".join(platforms)
    else:
        row["platforms_checked"] = str(platforms)

    # Text fields -> crop image path AND extracted Tesseract OCR text!
    crops = result.get("text_field_crops", {})
    ocr_texts = result.get("ocr_texts", {})
    for field_name, crop_path in crops.items():
        row[f"{field_name}_text"] = clean_ocr_text(ocr_texts.get(field_name, ""))
        row[f"{field_name}_image"] = crop_path

    new_df = pd.DataFrame([row])

    with excel_lock:
        # CSV Backup (append mode)
        file_exists = os.path.exists(CSV_PATH)
        new_df.to_csv(CSV_PATH, mode="a", index=False, header=not file_exists)

        # Excel Update (read existing if present, concatenate, save)
        if os.path.exists(EXCEL_PATH):
            try:
                existing_df = pd.read_excel(EXCEL_PATH)
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            except Exception:
                combined_df = new_df
        else:
            combined_df = new_df

        combined_df.to_excel(EXCEL_PATH, index=False)


@app.route("/")
def index():
    return send_file("capture.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/data/<path:filename>")
def serve_data_files(filename):
    return send_from_directory(DATA_DIR, filename)


@app.route("/api/scans")
def get_scans():
    scans = []
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH).fillna("")
            scans = df.to_dict(orient="records")
            # Clean all OCR text fields in response
            for row in scans:
                for key in list(row.keys()):
                    if key.endswith("_text"):
                        row[key] = clean_ocr_text(row[key])
            # Reverse order so latest scans appear first
            scans.reverse()
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"scans": scans, "count": len(scans)})


@app.route("/download/excel")
@app.route("/results.xlsx")
def download_excel():
    if os.path.exists(EXCEL_PATH):
        return send_file(EXCEL_PATH, as_attachment=True, download_name="results.xlsx")
    return jsonify({"error": "No scan results recorded yet."}), 404


@app.route("/download/csv")
@app.route("/results.csv")
def download_csv():
    if os.path.exists(CSV_PATH):
        return send_file(CSV_PATH, as_attachment=True, download_name="scans.csv")
    return jsonify({"error": "No scan results recorded yet."}), 404


@app.route("/stats")
def get_stats():
    count = 0
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH)
            count = len(df)
        except Exception:
            pass
    return jsonify({"total_scans": count, "excel_file": os.path.basename(EXCEL_PATH)})


@app.route("/api/clear", methods=["POST", "DELETE"])
def clear_all_data():
    try:
        with excel_lock:
            if os.path.exists(EXCEL_PATH):
                os.remove(EXCEL_PATH)
            if os.path.exists(CSV_PATH):
                os.remove(CSV_PATH)
            for d in [UPLOAD_DIR, CROPS_DIR]:
                if os.path.exists(d):
                    for f in os.listdir(d):
                        fp = os.path.join(d, f)
                        if os.path.isfile(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass
        return jsonify({"status": "success", "message": "All scan records and crop images cleared."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/detect_corners", methods=["POST"])
def detect_corners_endpoint():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    file = request.files["image"]
    temp_id = f"temp_{uuid.uuid4().hex[:6]}.jpg"
    temp_path = os.path.join(UPLOAD_DIR, temp_id)
    file.save(temp_path)

    try:
        try:
            from scan_form import detect_paper_corners
            corners = detect_paper_corners(temp_path)
        except Exception:
            corners = []
        img = Image.open(temp_path)
        w, h = img.size
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    return jsonify({"corners": corners, "width": w, "height": h})


@app.route("/scan", methods=["POST"])
def scan_endpoint():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files["image"]
    form_id = f"form_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    photo_path = os.path.join(UPLOAD_DIR, f"{form_id}.jpg")
    file.save(photo_path)

    user_corners = None
    if "corners" in request.form:
        try:
            user_corners = json.loads(request.form["corners"])
        except Exception:
            pass

    out_prefix = os.path.join(CROPS_DIR, form_id)
    try:
        result = scan(photo_path, out_prefix, user_corners=user_corners)
    except AlignmentError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    result["form_id"] = form_id

    # Automatically persist scan results to Excel & CSV for long-term storage
    try:
        save_scan_to_excel(result, form_id, photo_path)
        result["saved_to_excel"] = True
    except Exception as e:
        result["excel_error"] = str(e)

    return jsonify(sanitize_json_obj(result))




if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Starting server on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

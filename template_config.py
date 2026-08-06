"""
Template configuration for: student_survey_form.pdf

All coordinates below were extracted directly from the PDF's vector drawing
commands (fitz page.get_drawings()) — they are the REAL box/circle/line
positions from your form, in PDF points (1 pt = 1/72 inch), NOT guesses.

Origin (0,0) is the TOP-LEFT of the original page.
Original page size: 595.28 x 841.89 pt (A4).

We print a version of the form with a white margin added around it and a
small ArUco marker in each corner of that margin. That lets a phone photo
of the (possibly tilted / skewed) paper be automatically flattened back to
these exact coordinates, the same way exam-scanning machines use corner
timing marks.
"""

# ---- Page / printing geometry -------------------------------------------
ORIG_PAGE_W_PT = 595.2755737304688
ORIG_PAGE_H_PT = 841.8897705078125

MARGIN_PT = 50          # white border added around the original content
MARKER_SIZE_PT = 28     # size of each ArUco marker square
MARKER_INSET_PT = 10    # gap from the new page edge to the marker

NEW_PAGE_W_PT = ORIG_PAGE_W_PT + 2 * MARGIN_PT
NEW_PAGE_H_PT = ORIG_PAGE_H_PT + 2 * MARGIN_PT

# Marker IDs and their (x, y) top-left position on the NEW page, in points.
# IDs double as a sanity check: if scan detects wrong IDs in wrong corners,
# something is misprinted / photographed upside down.
MARKER_POSITIONS_PT = {
    0: (MARKER_INSET_PT, MARKER_INSET_PT),                                            # top-left
    1: (NEW_PAGE_W_PT - MARKER_INSET_PT - MARKER_SIZE_PT, MARKER_INSET_PT),            # top-right
    2: (NEW_PAGE_W_PT - MARKER_INSET_PT - MARKER_SIZE_PT,
        NEW_PAGE_H_PT - MARKER_INSET_PT - MARKER_SIZE_PT),                             # bottom-right
    3: (MARKER_INSET_PT, NEW_PAGE_H_PT - MARKER_INSET_PT - MARKER_SIZE_PT),            # bottom-left
}
ARUCO_DICT = "DICT_4X4_50"

# Rendering resolution used everywhere downstream (both when building the
# canonical template image and when warping a phone photo onto it).
DPI = 200
PT_TO_PX = DPI / 72.0


def offset(x0, y0, x1, y1):
    """Shift a region from ORIGINAL page coordinates to NEW (margin-added)
    page coordinates, then convert points -> pixels at DPI."""
    return {
        "x": round((x0 + MARGIN_PT) * PT_TO_PX),
        "y": round((y0 + MARGIN_PT) * PT_TO_PX),
        "w": round((x1 - x0) * PT_TO_PX),
        "h": round((y1 - y0) * PT_TO_PX),
    }


# ---- Fields: single-line text answers (crop out as an image) ------------
TEXT_FIELDS = {
    "full_name":         offset(130.5, 118.5, 359.5, 133.5),
    "class_grade":       offset(470.5, 118.5, 559.5, 133.5),
    "age":               offset(80.5, 148.5, 129.5, 163.5),
    "other_specify":     offset(190.5, 361.5, 529.5, 376.5),
    "career_preference": offset(320.5, 509.5, 559.5, 524.5),
    "career_reason":     offset(40.5, 560.5, 559.5, 609.5),   # bigger paragraph box
}

# ---- Fields: single-select "radio" circles (pick highest-fill one) ------
# Each group: name -> {option_label: region}
RADIO_GROUPS = {
    "gender": {
        "Male":   offset(205.5, 151.5, 215.5, 161.5),
        "Female": offset(275.5, 151.5, 285.5, 161.5),
    },
    "social_media_time": {
        "Less than 1 hour": offset(45.5, 246.5, 55.5, 256.5),
        "1-2 hours":        offset(152.5, 246.5, 162.5, 256.5),
        "2-4 hours":        offset(242.5, 246.5, 252.5, 256.5),
        "4-6 hours":        offset(332.5, 246.5, 342.5, 256.5),
        "More than 6 hours": offset(422.5, 246.5, 432.5, 256.5),
    },
    "study_time": {
        "Less than 1 hour": offset(45.5, 444.5, 55.5, 454.5),
        "1-2 hours":        offset(152.5, 444.5, 162.5, 454.5),
        "2-4 hours":        offset(242.5, 444.5, 252.5, 454.5),
        "4-6 hours":        offset(332.5, 444.5, 342.5, 454.5),
        "More than 6 hours": offset(422.5, 444.5, 432.5, 454.5),
    },
}

# ---- Fields: multi-select checkboxes (any number can be checked) --------
CHECKBOX_GROUP = {
    "Instagram": offset(45.5, 298.5, 55.5, 308.5),
    "TikTok":    offset(213.9, 298.5, 223.9, 308.5),
    "Facebook":  offset(382.4, 298.5, 392.4, 308.5),
    "WhatsApp":  offset(45.5, 322.5, 55.5, 332.5),
    "YouTube":   offset(213.9, 322.5, 223.9, 332.5),
    "Twitter/X": offset(382.4, 322.5, 392.4, 332.5),
    "Snapchat":  offset(45.5, 346.5, 55.5, 356.5),
    "Telegram":  offset(213.9, 346.5, 223.9, 356.5),
    "Other":     offset(382.4, 346.5, 392.4, 356.5),
}

CANONICAL_SIZE_PX = (round(NEW_PAGE_W_PT * PT_TO_PX), round(NEW_PAGE_H_PT * PT_TO_PX))

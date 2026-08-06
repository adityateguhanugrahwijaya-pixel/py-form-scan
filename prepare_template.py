"""
Step 0 (run once per form design).

Takes the original form PDF and produces a PRINTABLE version with a white
margin and 4 ArUco corner markers added. Print/photocopy THIS version for
your 50 students — the markers are what let a phone photo be auto-aligned
later, the same way exam scanners use corner timing marks.

Usage:
    python3 prepare_template.py input_form.pdf output_printable.pdf
"""
import sys
import os
import cv2
import numpy as np
import fitz  # PyMuPDF

import template_config as cfg


def generate_marker_pngs(out_dir):
    aruco_dict = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, cfg.ARUCO_DICT))
    paths = {}
    for marker_id in cfg.MARKER_POSITIONS_PT:
        img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, 400)
        # add a thin white quiet-zone border so the marker reads reliably
        img = cv2.copyMakeBorder(img, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
        path = os.path.join(out_dir, f"marker_{marker_id}.png")
        cv2.imwrite(path, img)
        paths[marker_id] = path
    return paths


def build_printable_pdf(input_pdf, output_pdf, marker_dir):
    marker_paths = generate_marker_pngs(marker_dir)

    src = fitz.open(input_pdf)
    src_page = src[0]

    out = fitz.open()
    new_page = out.new_page(width=cfg.NEW_PAGE_W_PT, height=cfg.NEW_PAGE_H_PT)

    # place the original form content, shifted by MARGIN_PT
    content_rect = fitz.Rect(
        cfg.MARGIN_PT, cfg.MARGIN_PT,
        cfg.MARGIN_PT + cfg.ORIG_PAGE_W_PT, cfg.MARGIN_PT + cfg.ORIG_PAGE_H_PT,
    )
    new_page.show_pdf_page(content_rect, src, 0)

    # stamp the 4 corner markers
    for marker_id, (mx, my) in cfg.MARKER_POSITIONS_PT.items():
        rect = fitz.Rect(mx, my, mx + cfg.MARKER_SIZE_PT, my + cfg.MARKER_SIZE_PT)
        new_page.insert_image(rect, filename=marker_paths[marker_id])

    out.save(output_pdf)
    out.close()
    src.close()
    print(f"Saved printable form -> {output_pdf}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 prepare_template.py input.pdf output_printable.pdf")
        sys.exit(1)
    build_printable_pdf(sys.argv[1], sys.argv[2], marker_dir="markers")

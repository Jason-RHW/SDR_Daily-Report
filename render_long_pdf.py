"""
Renders the report HTML as a single continuous PDF page (no letter/A4
pagination breaks). Works by rendering onto an oversized page, then
rasterizing to find the actual bottom of the content and cropping the
page down to that height.
"""
import numpy as np
import fitz  # PyMuPDF
from weasyprint import HTML, CSS
import os

# Background color used by the email templates (#EEF0F4)
BG_COLOR = np.array([238, 240, 244])
BG_DIFF_THRESHOLD = 12


def render_long_pdf(html_string, out_path, page_width_px, oversized_height_px=9000, oversized_width_px=1600, dpi=150):
    """Renders html_string to a single-page PDF cropped to its actual
    content bounding box (no pagination, no clipped columns). Renders
    onto a page wider AND taller than any expected content, then crops
    to whatever was actually drawn."""
    tmp_path = out_path + ".tmp.pdf"

    render_width = max(page_width_px, oversized_width_px)
    page_css = CSS(string=f"@page {{ size: {render_width}px {oversized_height_px}px; margin: 0; }}")
    HTML(string=html_string).write_pdf(tmp_path, stylesheets=[page_css])

    doc = fitz.open(tmp_path)
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    rgb = img[:, :, :3].astype(int)

    # A pixel counts as "background" if it matches the page's gray
    # background OR is near-white (the card interior, and - importantly -
    # the blank canvas beyond the real content, which renders as plain
    # white rather than inheriting the page's gray background).
    diff_gray = np.abs(rgb - BG_COLOR).sum(axis=2)
    is_gray_bg = diff_gray <= 20
    is_near_white = rgb.min(axis=2) >= 244
    is_bg_pixel = is_gray_bg | is_near_white
    is_content = ~is_bg_pixel

    rows_with_content = np.where(is_content.any(axis=1))[0]
    cols_with_content = np.where(is_content.any(axis=0))[0]

    last_row_px = int(rows_with_content.max()) if len(rows_with_content) else pix.height - 1
    first_col_px = int(cols_with_content.min()) if len(cols_with_content) else 0
    last_col_px = int(cols_with_content.max()) if len(cols_with_content) else pix.width - 1

    padding_px = 40
    content_height_pt = (last_row_px + padding_px) / dpi * 72
    left_pt = max(0, first_col_px - padding_px) / dpi * 72
    right_pt = min(pix.width - 1, last_col_px + padding_px) / dpi * 72

    rect = page.rect
    # PDF coordinates originate at the bottom-left, but the rendered
    # content sits at the TOP of this oversized page - so we keep the
    # top slice (near rect.y1), not the bottom (near rect.y0).
    new_rect = fitz.Rect(
        rect.x0 + left_pt,
        max(rect.y0, rect.y1 - content_height_pt),
        rect.x0 + right_pt,
        rect.y1,
    )
    page.set_cropbox(new_rect)
    page.set_mediabox(new_rect)

    doc.save(out_path)
    doc.close()
    os.remove(tmp_path)

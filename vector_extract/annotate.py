"""Render a page with the extraction drawn on top, for visual QA."""

from __future__ import annotations

from pathlib import Path as FsPath

import pymupdf

from .models import Sheet

COLORS = {"outlet": (0.85, 0.1, 0.1), "light": (0.95, 0.6, 0.0),
          "diffuser": (0.1, 0.35, 0.9), "duct": (0.0, 0.6, 0.6)}
ROOM_COLOR = (0.1, 0.6, 0.2)


def annotate(pdf_path: str | FsPath, sheet: Sheet, room_shapes, out_png: str | FsPath, dpi: int = 110):
    doc = pymupdf.open(pdf_path)
    page = doc[sheet.page - 1]

    for shape in room_shapes:
        ring = [pymupdf.Point(x, y) for x, y in shape.polygon.exterior.coords]
        page.draw_polyline(ring, color=ROOM_COLOR, width=2.5, stroke_opacity=0.35)

    for s in sheet.symbols:
        c = COLORS.get(s.type, (0.5, 0, 0.5))
        r = pymupdf.Rect(s.bbox.x0 - 2, s.bbox.y0 - 2, s.bbox.x1 + 2, s.bbox.y1 + 2)
        page.draw_rect(r, color=c, width=1.2)
        if s.length_m is None:
            page.insert_text((r.x1 + 1, r.y0 + 5), s.id.split("-")[-1], fontsize=5, color=c)
        else:
            page.insert_text((r.x0, r.y0 - 3), f"{s.id}: {s.length_m:g} m", fontsize=7, color=c)

    # room tags last, so they stay readable on top of symbols
    for shape in room_shapes:
        room = next(r for r in sheet.rooms if r.name == shape.name)
        x0, y0 = shape.polygon.bounds[:2]
        parts = [f"{v} {k}" for k, v in sorted(room.counts.items())]
        if room.duct_length_m:
            parts.append(f"{room.duct_length_m:g} m duct")
        tag = f"{room.name}  {room.area_m2:g} m2 [{room.area_check}]"
        detail = ", ".join(parts) or "-"
        width = max(pymupdf.get_text_length(tag, fontsize=8), pymupdf.get_text_length(detail, fontsize=7))
        page.draw_rect(pymupdf.Rect(x0 + 4, y0 + 5, x0 + 10 + width, y0 + 28),
                       color=None, fill=(1, 1, 1), fill_opacity=0.9)
        page.insert_text((x0 + 6, y0 + 14), tag, fontsize=8, color=ROOM_COLOR)
        page.insert_text((x0 + 6, y0 + 25), detail, fontsize=7, color=ROOM_COLOR)

    page.get_pixmap(dpi=dpi).save(str(out_png))

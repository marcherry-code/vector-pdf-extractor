"""Generate a synthetic CAD-style floor plan as a vector PDF with real layers.

The drawing mimics a typical CAD export: single-line walls, electrical and HVAC
symbols built from primitive lines/curves (no "symbol" objects survive the
export), room labels as positioned text, and everything sorted into optional
content groups (PDF layers) named like AIA CAD layers.

It also writes ``floorplan.truth.json`` with the exact symbol counts per room,
which the test suite uses as acceptance criteria.

Usage:
    python samples/make_sample.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
PT_PER_M = 40.0                      # drawing scale: 40 pt = 1 m (A3, 1:~70)
ORIGIN = (110.0, 130.0)              # top-left corner of the building on the sheet

# Rooms in metres: name, x0, y0, x1, y1
ROOMS = [
    ("LIVING ROOM", 0, 0, 12, 8),
    ("KITCHEN", 12, 0, 24, 8),
    ("BEDROOM", 0, 8, 10, 14),
    ("BATHROOM", 10, 8, 16, 14),
    ("OFFICE", 16, 8, 24, 14),
]

# Symbol placements in metres (x, y)
OUTLETS = {
    "LIVING ROOM": [(0.4, 2), (0.4, 6), (6, 0.4), (11.6, 4)],
    "KITCHEN": [(13, 0.4), (15, 0.4), (17, 0.4), (19, 0.4), (23.6, 4), (21, 7.6)],
    "BEDROOM": [(0.4, 10), (5, 13.6), (9.6, 11)],
    "BATHROOM": [(15.6, 9)],
    "OFFICE": [(16.4, 10), (16.4, 12), (20, 13.6), (23.6, 11), (23.6, 13)],
}
LIGHTS = {
    "LIVING ROOM": [(3, 4), (9, 4)],
    "KITCHEN": [(16, 4), (20, 4)],
    "BEDROOM": [(5, 12.4)],
    "BATHROOM": [(13, 12.4)],
    "OFFICE": [(18, 11), (22, 11)],
}
DIFFUSERS = {
    "LIVING ROOM": [(6, 6.5)],
    "KITCHEN": [(18, 6.5)],
    "BEDROOM": [(5, 9.2)],
    "BATHROOM": [],
    "OFFICE": [(20, 9.2)],
}
# Duct runs (centre lines, metres): horizontal trunk + two drops
DUCTS = [((1, 7.2), (23, 7.2)), ((5, 7.2), (5, 9.2)), ((20, 7.2), (20, 9.2))]
DUCT_WIDTH_M = 0.3


def m(x: float, y: float) -> pymupdf.Point:
    """Metres -> sheet points."""
    return pymupdf.Point(ORIGIN[0] + x * PT_PER_M, ORIGIN[1] + y * PT_PER_M)


def draw_outlet(page, c, oc):
    # duplex receptacle: circle + two short parallel lines
    page.draw_circle(c, 5, color=(0, 0, 0), width=0.6, oc=oc)
    page.draw_line(c + (-2, -3), c + (-2, 3), color=(0, 0, 0), width=0.6, oc=oc)
    page.draw_line(c + (2, -3), c + (2, 3), color=(0, 0, 0), width=0.6, oc=oc)


def draw_light(page, c, oc):
    # ceiling light: circle with an X
    page.draw_circle(c, 8, color=(0, 0, 0), width=0.6, oc=oc)
    page.draw_line(c + (-5.6, -5.6), c + (5.6, 5.6), color=(0, 0, 0), width=0.6, oc=oc)
    page.draw_line(c + (-5.6, 5.6), c + (5.6, -5.6), color=(0, 0, 0), width=0.6, oc=oc)


def draw_diffuser(page, c, oc):
    # supply air diffuser: square with diagonals
    r = pymupdf.Rect(c.x - 9, c.y - 9, c.x + 9, c.y + 9)
    page.draw_rect(r, color=(0, 0, 0.6), width=0.6, oc=oc)
    page.draw_line(r.tl, r.br, color=(0, 0, 0.6), width=0.4, oc=oc)
    page.draw_line(r.bl, r.tr, color=(0, 0, 0.6), width=0.4, oc=oc)


def draw_duct(page, a, b, oc):
    pa, pb = m(*a), m(*b)
    half = DUCT_WIDTH_M * PT_PER_M / 2
    if pa.y == pb.y:   # horizontal
        r = pymupdf.Rect(min(pa.x, pb.x), pa.y - half, max(pa.x, pb.x), pa.y + half)
    else:              # vertical
        r = pymupdf.Rect(pa.x - half, min(pa.y, pb.y), pa.x + half, max(pa.y, pb.y))
    page.draw_rect(r, color=(0, 0, 0.6), width=0.5, dashes="[4 2] 0", oc=oc)


def build(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=1191, height=842)   # A3 landscape
    L = {name: doc.add_ocg(name, on=True) for name in
         ["A-WALL", "A-DOOR", "A-ANNO", "A-TTLB", "E-POWER", "E-LITE", "M-HVAC"]}

    # walls: outer box + interior partitions, drawn as single lines like a CAD export
    walls = [((0, 0), (24, 0)), ((24, 0), (24, 14)), ((24, 14), (0, 14)), ((0, 14), (0, 0)),
             ((12, 0), (12, 8)), ((0, 8), (24, 8)), ((10, 8), (10, 14)), ((16, 8), (16, 14))]
    for a, b in walls:
        page.draw_line(m(*a), m(*b), color=(0, 0, 0), width=2.0, oc=L["A-WALL"])

    # door swings (noise the extractor must ignore for counting)
    for hinge in [(12, 3), (2, 8), (13, 8), (22, 8)]:
        h = m(*hinge)
        page.draw_line(h, h + (0, 32), color=(0.4, 0.4, 0.4), width=0.4, oc=L["A-DOOR"])
        page.draw_curve(h + (0, 32), h + (26, 26), h + (32, 0), color=(0.4, 0.4, 0.4),
                        width=0.4, oc=L["A-DOOR"])

    truth: dict = {"pt_per_m": PT_PER_M, "rooms": {}}
    for name, x0, y0, x1, y1 in ROOMS:
        area = (x1 - x0) * (y1 - y0)
        c = m((x0 + x1) / 2, (y0 + y1) / 2)
        page.insert_text(c + (-30, -4), name, fontsize=9, oc=L["A-ANNO"])
        page.insert_text(c + (-30, 8), f"{area:.1f} m2", fontsize=7, oc=L["A-ANNO"])
        for p in OUTLETS[name]:
            draw_outlet(page, m(*p), L["E-POWER"])
        for p in LIGHTS[name]:
            draw_light(page, m(*p), L["E-LITE"])
        for p in DIFFUSERS[name]:
            draw_diffuser(page, m(*p), L["M-HVAC"])
        truth["rooms"][name] = {
            "area_m2": area,
            "outlet": len(OUTLETS[name]),
            "light": len(LIGHTS[name]),
            "diffuser": len(DIFFUSERS[name]),
        }

    for a, b in DUCTS:
        draw_duct(page, a, b, L["M-HVAC"])
    # overlapping duct rectangles merge into one network; its length is the union of runs
    truth["duct_length_m"] = 22.0 + 2.0 + 2.0

    # title block
    tb = pymupdf.Rect(800, 735, 1160, 815)
    page.draw_rect(tb, color=(0, 0, 0), width=1, oc=L["A-TTLB"])
    page.insert_text(tb.tl + (8, 18), "DEMO RESIDENCE - GROUND FLOOR", fontsize=10, oc=L["A-TTLB"])
    page.insert_text(tb.tl + (8, 36), "SHEET E-101   ELECTRICAL + HVAC LAYOUT", fontsize=8, oc=L["A-TTLB"])
    page.insert_text(tb.tl + (8, 52), f"SCALE: {PT_PER_M:g} PT = 1 M", fontsize=8, oc=L["A-TTLB"])
    page.insert_text(tb.tl + (8, 68), "SYNTHETIC SAMPLE - NOT FOR CONSTRUCTION", fontsize=7, oc=L["A-TTLB"])

    doc.save(path)
    return truth


if __name__ == "__main__":
    out = HERE / "floorplan.pdf"
    truth = build(out)
    (HERE / "floorplan.truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"wrote {out}")

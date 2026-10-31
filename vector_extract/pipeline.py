"""End-to-end: PDF page -> paths/text -> groups -> classified symbols -> rooms -> JSON."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path as FsPath

import pymupdf
from shapely.geometry import Point

from .grouping import classify, group_paths, run_centerlines, run_length_pt
from .models import BBox, ExtractionResult, Room, Sheet, Symbol
from .reader import read_paths, read_text
from .rooms import find_rooms

SCALE_PT_RE = re.compile(r"SCALE:?\s*([\d.]+)\s*PT\s*=\s*1\s*M", re.IGNORECASE)
SCALE_RATIO_RE = re.compile(r"SCALE:?\s*1\s*:\s*(\d+)", re.IGNORECASE)
PT_PER_M_AT_1_1 = 72 / 0.0254          # 1 m on paper at 1:1, in PDF points


def load_rules(path: str | FsPath) -> dict:
    return json.loads(FsPath(path).read_text(encoding="utf-8"))


def detect_scale(texts, rules: dict) -> tuple[float, str | None]:
    """Scale from the title block text, falling back to the rules file."""
    for t in texts:
        if m := SCALE_PT_RE.search(t.text):
            return float(m.group(1)), None
        if m := SCALE_RATIO_RE.search(t.text):
            return PT_PER_M_AT_1_1 / float(m.group(1)), None
    if "scale_pt_per_m" in rules:
        return float(rules["scale_pt_per_m"]), "scale not found on sheet; used rules default"
    raise ValueError("No scale on the sheet and no 'scale_pt_per_m' in the rules")


def extract_page(page: pymupdf.Page, rules: dict, source: str) -> tuple[Sheet, list]:
    warnings: list[str] = []
    paths = read_paths(page)
    texts = read_text(page)
    pt_per_m, warn = detect_scale(texts, rules)
    if warn:
        warnings.append(warn)

    wall_layers = set(rules["wall_layers"])
    ignore = set(rules.get("ignore_layers", [])) | wall_layers
    label_layers = set(rules.get("room_label_layers", []))

    room_shapes = find_rooms([p for p in paths if p.layer in wall_layers],
                             [t for t in texts if t.layer in label_layers], pt_per_m,
                             rules.get("min_room_area_m2", 1.0))

    def room_of(x: float, y: float) -> str | None:
        pt = Point(x, y)
        return next((r.name for r in room_shapes if r.polygon.contains(pt)), None)

    groups = group_paths([p for p in paths if p.layer not in ignore], rules.get("tolerance_pt", 1.0))
    symbols: list[Symbol] = []
    counters: Counter = Counter()
    per_room: dict[str, Counter] = defaultdict(Counter)
    duct_per_room: dict[str, float] = defaultdict(float)
    unclassified = 0

    for g in sorted(groups, key=lambda g: (g.bounds[1], g.bounds[0])):
        rule = classify(g, rules["symbols"])
        if rule is None:
            unclassified += 1
            continue
        kind = rule["type"]
        counters[kind] += 1
        x0, y0, x1, y1 = g.bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        length_m = None
        room = room_of(cx, cy)
        if rule.get("measure") == "length":
            length_m = round(run_length_pt(g) / pt_per_m, 2)
            room = None                                   # networks span rooms; split below
            for line in run_centerlines(g):
                for r in room_shapes:
                    duct_per_room[r.name] += line.intersection(r.polygon).length / pt_per_m
        else:
            per_room[room or "(outside rooms)"][kind] += 1
        symbols.append(Symbol(id=f"{kind}-{counters[kind]:03d}", type=kind, layer=g.layer,
                              bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), center=(cx, cy),
                              room=room, length_m=length_m))

    rooms: list[Room] = []
    tol = rules.get("area_tolerance", 0.01)
    for r in room_shapes:
        area = round(r.polygon.area / pt_per_m ** 2, 2)
        if r.label_area_m2 is None:
            check = "no_label"
        else:
            check = "ok" if abs(area - r.label_area_m2) <= tol * r.label_area_m2 else "mismatch"
        if check == "mismatch":
            warnings.append(f"{r.name}: drawn area {area} m2 != labelled {r.label_area_m2} m2")
        rooms.append(Room(name=r.name, area_m2=area, label_area_m2=r.label_area_m2,
                          area_check=check, counts=dict(per_room.get(r.name, {})),
                          duct_length_m=round(duct_per_room.get(r.name, 0.0), 2)))
    if per_room.get("(outside rooms)"):
        warnings.append(f"symbols outside any room: {dict(per_room['(outside rooms)'])}")
    if unclassified:
        warnings.append(f"{unclassified} path group(s) matched no rule")

    totals: dict[str, float] = {k: float(v) for k, v in counters.items()}
    for s in symbols:
        if s.length_m is not None:
            totals[f"{s.type}_length_m"] = round(totals.get(f"{s.type}_length_m", 0.0) + s.length_m, 2)
    totals["floor_area_m2"] = round(sum(r.area_m2 for r in rooms), 2)

    sheet = Sheet(source=source, page=page.number + 1, size_pt=(page.rect.width, page.rect.height),
                  scale_pt_per_m=round(pt_per_m, 4),
                  layers=dict(sorted(Counter(p.layer for p in paths).items())),
                  rooms=rooms, symbols=symbols, totals=totals,
                  unclassified_groups=unclassified, warnings=warnings)
    return sheet, room_shapes


def extract_pdf(pdf_path: str | FsPath, rules: dict) -> ExtractionResult:
    doc = pymupdf.open(pdf_path)
    sheets = [extract_page(page, rules, FsPath(pdf_path).name)[0] for page in doc]
    return ExtractionResult(sheets=sheets)

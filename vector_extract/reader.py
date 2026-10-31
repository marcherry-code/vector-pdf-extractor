"""Read raw vector paths and positioned text (with CAD layers) from a PDF page."""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf
from shapely.geometry import LineString, MultiLineString


@dataclass
class Path:
    """One vector path from the PDF content stream, converted to geometry."""
    index: int
    layer: str
    geom: MultiLineString
    n_lines: int = 0
    n_curves: int = 0
    n_rects: int = 0
    dashed: bool = False
    rects: list[pymupdf.Rect] = field(default_factory=list)


@dataclass
class TextSpan:
    text: str
    bbox: pymupdf.Rect
    layer: str
    size: float


def _bezier(p1, p2, p3, p4, steps: int = 8) -> list[tuple[float, float]]:
    pts = []
    for i in range(steps + 1):
        t = i / steps
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        pts.append((a * p1.x + b * p2.x + c * p3.x + d * p4.x,
                    a * p1.y + b * p2.y + c * p3.y + d * p4.y))
    return pts


def _rect_ring(r: pymupdf.Rect) -> list[tuple[float, float]]:
    return [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)]


def read_paths(page: pymupdf.Page) -> list[Path]:
    paths: list[Path] = []
    for i, d in enumerate(page.get_drawings()):
        lines, p = [], Path(index=i, layer=d.get("layer") or "0",
                            geom=MultiLineString(), dashed=d.get("dashes") not in (None, "", "[] 0"))
        for item in d["items"]:
            op = item[0]
            if op == "l":
                lines.append(LineString([tuple(item[1]), tuple(item[2])]))
                p.n_lines += 1
            elif op == "c":
                lines.append(LineString(_bezier(*item[1:5])))
                p.n_curves += 1
            elif op == "re":
                lines.append(LineString(_rect_ring(item[1])))
                p.rects.append(pymupdf.Rect(item[1]))
                p.n_rects += 1
            elif op == "qu":
                q = item[1]
                lines.append(LineString([tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll), tuple(q.ul)]))
                p.n_rects += 1
        if lines:
            p.geom = MultiLineString(lines)
            paths.append(p)
    return paths


def read_text(page: pymupdf.Page) -> list[TextSpan]:
    spans = []
    for t in page.get_texttrace():
        text = "".join(chr(c[0]) for c in t["chars"]).strip()
        if text:
            spans.append(TextSpan(text=text, bbox=pymupdf.Rect(t["bbox"]),
                                  layer=t.get("layer") or "0", size=t["size"]))
    return spans

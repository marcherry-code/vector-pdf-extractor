"""Rebuild room polygons from single-line walls and attach the printed labels."""

from __future__ import annotations

import re
from dataclasses import dataclass

from shapely import union_all
from shapely.geometry import Point, Polygon
from shapely.ops import polygonize

from .reader import Path, TextSpan

AREA_RE = re.compile(r"([\d.,]+)\s*m(?:2|²)", re.IGNORECASE)


@dataclass
class RoomShape:
    name: str
    polygon: Polygon
    label_area_m2: float | None


def find_rooms(wall_paths: list[Path], labels: list[TextSpan], pt_per_m: float,
               min_area_m2: float = 1.0) -> list[RoomShape]:
    """Polygonize the noded wall network; name each face by the label text inside it."""
    noded = union_all([p.geom for p in wall_paths])          # splits lines at T-junctions
    faces = [f for f in polygonize(noded) if f.area / pt_per_m ** 2 >= min_area_m2]

    rooms = []
    for i, face in enumerate(sorted(faces, key=lambda f: (f.bounds[1], f.bounds[0]))):
        inside = [t for t in labels if face.contains(Point(t.bbox.x0 + t.bbox.width / 2,
                                                           t.bbox.y0 + t.bbox.height / 2))]
        area_label = next((t for t in inside if AREA_RE.search(t.text)), None)
        name_label = next((t for t in inside if t is not area_label and not AREA_RE.search(t.text)), None)
        label_area = None
        if area_label:
            label_area = float(AREA_RE.search(area_label.text).group(1).replace(",", "."))
        rooms.append(RoomShape(name=name_label.text if name_label else f"ROOM {i + 1}",
                               polygon=face, label_area_m2=label_area))
    return rooms

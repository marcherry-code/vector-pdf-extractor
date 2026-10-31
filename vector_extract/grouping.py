"""Group loose vector paths into symbols and classify them with declarative rules.

A CAD export flattens blocks (symbols) into unrelated lines and curves. Paths on
the same layer with the same linetype that touch within a small tolerance are
merged back into one group, then each group is classified by its features.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from shapely import STRtree, union_all
from shapely.geometry import Polygon

from .reader import Path


@dataclass
class Group:
    layer: str
    dashed: bool
    members: list[Path]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        xs0, ys0, xs1, ys1 = zip(*(m.geom.bounds for m in self.members))
        return min(xs0), min(ys0), max(xs1), max(ys1)

    @property
    def size(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bounds
        return x1 - x0, y1 - y0

    def features(self) -> dict[str, float]:
        w, h = self.size
        return {
            "lines": sum(m.n_lines for m in self.members),
            "curves": sum(m.n_curves for m in self.members),
            "rects": sum(m.n_rects for m in self.members),
            "size": max(w, h),
            "aspect": max(w, h) / max(min(w, h), 1e-6),
        }


def group_paths(paths: list[Path], tolerance: float = 1.0) -> list[Group]:
    """Cluster paths that touch (within `tolerance` pt), per layer and linetype."""
    buckets: dict[tuple[str, bool], list[Path]] = defaultdict(list)
    for p in paths:
        buckets[(p.layer, p.dashed)].append(p)

    groups: list[Group] = []
    for (layer, dashed), members in buckets.items():
        buffered = [m.geom.buffer(tolerance) for m in members]
        merged = union_all(buffered)
        blobs = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        tree = STRtree(buffered)
        for blob in blobs:
            idx = [i for i in tree.query(blob, predicate="intersects")]
            groups.append(Group(layer=layer, dashed=dashed, members=[members[i] for i in sorted(idx)]))
    return groups


def _matches(rule: dict, g: Group, f: dict[str, float]) -> bool:
    if g.layer not in rule.get("layers", [g.layer]):
        return False
    if "dashed" in rule and rule["dashed"] != g.dashed:
        return False
    for key in ("lines", "curves", "rects", "size", "aspect"):
        if f[key] < rule.get(f"min_{key}", float("-inf")):
            return False
        if f[key] > rule.get(f"max_{key}", float("inf")):
            return False
    return True


def classify(g: Group, rules: list[dict]) -> dict | None:
    """Return the first rule that matches the group, or None."""
    f = g.features()
    return next((r for r in rules if _matches(r, g, f)), None)


def run_length_pt(g: Group) -> float:
    """Length of a linear group (e.g. a duct network) = sum of the long sides of its runs."""
    total = 0.0
    for m in g.members:
        for r in m.rects:
            total += max(r.width, r.height)
    return total


def run_centerlines(g: Group):
    """Centre line of every rectangular run, for clipping lengths to rooms."""
    from shapely.geometry import LineString
    out = []
    for m in g.members:
        for r in m.rects:
            if r.width >= r.height:
                y = (r.y0 + r.y1) / 2
                out.append(LineString([(r.x0, y), (r.x1, y)]))
            else:
                x = (r.x0 + r.x1) / 2
                out.append(LineString([(x, r.y0), (x, r.y1)]))
    return out


def bounds_polygon(b: tuple[float, float, float, float]) -> Polygon:
    x0, y0, x1, y1 = b
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

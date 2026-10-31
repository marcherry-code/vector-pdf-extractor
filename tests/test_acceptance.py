"""Acceptance tests: the extractor must reproduce the ground truth of the sample sheet."""

import json
from pathlib import Path

import pymupdf
import pytest

from vector_extract import extract_pdf
from vector_extract.models import ExtractionResult
from vector_extract.pipeline import detect_scale, load_rules
from vector_extract.reader import TextSpan

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "floorplan.pdf"
TRUTH = json.loads((ROOT / "samples" / "floorplan.truth.json").read_text(encoding="utf-8"))
RULES = load_rules(ROOT / "rules" / "floorplan.json")


@pytest.fixture(scope="module")
def sheet():
    return extract_pdf(SAMPLE, RULES).sheets[0]


def test_all_rooms_found(sheet):
    assert {r.name for r in sheet.rooms} == set(TRUTH["rooms"])


@pytest.mark.parametrize("room", list(TRUTH["rooms"]))
def test_counts_per_room(sheet, room):
    got = next(r for r in sheet.rooms if r.name == room)
    want = TRUTH["rooms"][room]
    for kind in ("outlet", "light", "diffuser"):
        assert got.counts.get(kind, 0) == want[kind], f"{room}: {kind}"
    assert got.area_m2 == pytest.approx(want["area_m2"])
    assert got.area_check == "ok"


def test_duct_length(sheet):
    assert sheet.totals["duct_length_m"] == pytest.approx(TRUTH["duct_length_m"])
    assert sum(r.duct_length_m for r in sheet.rooms) == pytest.approx(TRUTH["duct_length_m"], abs=0.05)


def test_nothing_unclassified(sheet):
    assert sheet.unclassified_groups == 0
    assert sheet.warnings == []


def test_output_roundtrips_through_schema(sheet):
    data = ExtractionResult(sheets=[sheet]).model_dump_json()
    assert ExtractionResult.model_validate_json(data).sheets[0].totals == sheet.totals


def test_scale_from_ratio_text():
    span = TextSpan(text="SCALE 1:100", bbox=pymupdf.Rect(0, 0, 1, 1), layer="0", size=8)
    pt_per_m, warn = detect_scale([span], {})
    assert pt_per_m == pytest.approx(28.3465, rel=1e-4)
    assert warn is None


def test_area_mismatch_is_flagged(tmp_path):
    """A label that disagrees with the drawn walls must raise a warning, not pass silently."""
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    wall, anno = doc.add_ocg("A-WALL"), doc.add_ocg("A-ANNO")
    page.draw_rect(pymupdf.Rect(50, 50, 250, 210), width=2, oc=wall)    # 5 m x 4 m = 20 m2
    page.insert_text((100, 120), "STORE", fontsize=9, oc=anno)
    page.insert_text((100, 132), "25.0 m2", fontsize=7, oc=anno)
    path = tmp_path / "mismatch.pdf"
    doc.save(path)

    rules = {**RULES, "symbols": []}
    s = extract_pdf(path, rules).sheets[0]
    assert s.rooms[0].area_m2 == pytest.approx(20.0)
    assert s.rooms[0].area_check == "mismatch"
    assert any("STORE" in w for w in s.warnings)

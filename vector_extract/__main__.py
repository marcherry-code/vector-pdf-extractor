"""CLI: python -m vector_extract drawing.pdf --rules rules/floorplan.json --out output/"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymupdf

from .annotate import annotate
from .models import ExtractionResult
from .pipeline import extract_page, load_rules


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vector_extract", description=__doc__)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--rules", type=Path, default=Path("rules/floorplan.json"))
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--no-image", action="store_true", help="skip the annotated PNG")
    args = ap.parse_args(argv)

    rules = load_rules(args.rules)
    args.out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(args.pdf)
    sheets = []
    for page in doc:
        sheet, room_shapes = extract_page(page, rules, args.pdf.name)
        sheets.append(sheet)
        if not args.no_image:
            png = args.out / f"{args.pdf.stem}_p{sheet.page}_annotated.png"
            annotate(args.pdf, sheet, room_shapes, png)
            print(f"image  -> {png}")

    result = ExtractionResult(sheets=sheets)
    out_json = args.out / f"{args.pdf.stem}.json"
    out_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    (args.out / "schema.json").write_text(json.dumps(ExtractionResult.model_json_schema(), indent=2),
                                          encoding="utf-8")
    print(f"json   -> {out_json}")
    for s in sheets:
        print(f"sheet {s.page}: " + ", ".join(f"{k}={v:g}" for k, v in s.totals.items()))
        for w in s.warnings:
            print(f"  WARNING: {w}")
    return 1 if any(s.warnings for s in sheets) else 0


if __name__ == "__main__":
    raise SystemExit(main())

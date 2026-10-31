"""Pydantic models: the output contract (exported as JSON Schema)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class Symbol(BaseModel):
    id: str = Field(description="Stable id, e.g. 'outlet-007'")
    type: str = Field(description="Symbol type from the rules file")
    layer: str
    bbox: BBox
    center: tuple[float, float]
    room: str | None = Field(None, description="Room the symbol centre lies in")
    length_m: float | None = Field(None, description="Measured length for linear items (ducts)")


class Room(BaseModel):
    name: str
    area_m2: float = Field(description="Area computed from wall geometry")
    label_area_m2: float | None = Field(None, description="Area printed on the drawing")
    area_check: Literal["ok", "mismatch", "no_label"]
    counts: dict[str, int] = Field(default_factory=dict)
    duct_length_m: float = 0.0


class Sheet(BaseModel):
    source: str
    page: int
    size_pt: tuple[float, float]
    scale_pt_per_m: float
    layers: dict[str, int] = Field(description="Vector paths per CAD layer")
    rooms: list[Room]
    symbols: list[Symbol]
    totals: dict[str, float] = Field(description="Bill of quantities for the sheet")
    unclassified_groups: int
    warnings: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    sheets: list[Sheet]

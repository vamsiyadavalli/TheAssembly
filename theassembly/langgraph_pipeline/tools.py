from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ToolExecutionError(RuntimeError):
    """Raised when a deterministic local tool cannot complete."""


class MovementSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    reps: str = Field(min_length=1)
    rx_weight: str | None = None
    scaled_weight: str | None = None
    notes: str | None = None
    section: str | None = None
    finisher_part: int | None = None
    finisher_part_type: str | None = None
    finisher_part_title: str | None = None
    round_group: int | None = None
    round_group_label: str | None = None
    round_group_note: str | None = None


class WorkoutSchema(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    date: str = Field(min_length=1)
    release_time: str = Field(min_length=1)
    content: str = Field(min_length=1)
    stimulus: str = Field(min_length=1)
    technical_cues: list[str]
    movements: list[MovementSchema] = Field(default_factory=list)


def _normalize_round_label_contiguity(movements: list[dict[str, Any]]) -> None:
    by_label: dict[str, list[int]] = {}
    for idx, movement in enumerate(movements):
        label = str(movement.get("round_group_label") or "").strip()
        if not label:
            continue
        by_label.setdefault(label, []).append(idx)

    for label, indices in by_label.items():
        if not indices:
            continue
        if max(indices) - min(indices) + 1 != len(indices):
            raise ToolExecutionError(
                f"round_group_label '{label}' must be contiguous; found split segments at indices {indices}."
            )


def validate_workout_schema(raw_wod: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize workout data using Pydantic and deterministic checks."""
    try:
        payload = WorkoutSchema.model_validate(raw_wod)
    except ValidationError as exc:
        raise ToolExecutionError(f"workout schema validation failed: {exc}") from exc

    normalized = payload.model_dump(exclude_none=True)
    _normalize_round_label_contiguity(normalized.get("movements", []))
    return normalized


def generate_coordinate_map(validated_wod: dict[str, Any]) -> dict[str, Any]:
    """Create deterministic 1024x1024 layout coordinates from workout structure."""
    movements = validated_wod.get("movements", [])
    finisher = [m for m in movements if str(m.get("section", "")).strip().lower() == "finisher"]
    main = [m for m in movements if str(m.get("section", "")).strip().lower() != "finisher"]

    canvas_w = 1024
    canvas_h = 1024
    header_y1 = 150
    body_y0 = 150
    body_y1 = 850
    footer_y0 = 850

    sidebar_w = int(canvas_w * 0.30) if finisher else 0
    main_w = canvas_w - sidebar_w

    if main_w <= 0:
        raise ToolExecutionError("invalid layout: main canvas width is non-positive.")

    grouped: list[tuple[str, list[int]]] = []
    consumed: set[int] = set()
    for idx, movement in enumerate(main):
        if idx in consumed:
            continue
        label = str(movement.get("round_group_label") or "").strip()
        if label:
            cluster_indices = [i for i, m in enumerate(main) if str(m.get("round_group_label") or "").strip() == label]
            for i in cluster_indices:
                consumed.add(i)
            grouped.append((label, cluster_indices))
        else:
            consumed.add(idx)
            grouped.append((f"movement-{idx+1}", [idx]))

    if not grouped:
        grouped = [("empty", [])]

    body_h = body_y1 - body_y0
    use_masonry = len(main) > 4 and len(grouped) > 2

    movement_boxes: list[dict[str, Any]] = []
    if use_masonry:
        col_w = max(1, (main_w - 60) // 2)
        left_x = 20
        right_x = left_x + col_w + 20
        left_y = body_y0 + 20
        right_y = body_y0 + 20
        for i, (label, cluster) in enumerate(grouped):
            col_x = left_x if i % 2 == 0 else right_x
            y = left_y if i % 2 == 0 else right_y
            h = max(90, int(body_h / max(2, len(grouped) // 2 + 1)) - 20)
            movement_boxes.append({
                "label": label,
                "x": col_x,
                "y": y,
                "width": col_w,
                "height": h,
                "movement_indices": cluster,
            })
            if i % 2 == 0:
                left_y += h + 20
            else:
                right_y += h + 20
    else:
        pad = 20
        box_h = max(80, (body_h - (len(grouped) + 1) * pad) // len(grouped))
        y = body_y0 + pad
        for label, cluster in grouped:
            movement_boxes.append({
                "label": label,
                "x": pad,
                "y": y,
                "width": max(1, main_w - (2 * pad)),
                "height": box_h,
                "movement_indices": cluster,
            })
            y += box_h + pad

    overflow = [box for box in movement_boxes if box["y"] + box["height"] > body_y1]
    if overflow:
        raise ToolExecutionError("layout overflow in Zone B body; unable to place all movement clusters.")

    return {
        "canvas": {"width": canvas_w, "height": canvas_h},
        "zones": {
            "header": {"x": 0, "y": 0, "width": main_w, "height": header_y1},
            "body": {"x": 0, "y": body_y0, "width": main_w, "height": body_h},
            "footer": {"x": 0, "y": footer_y0, "width": main_w, "height": canvas_h - footer_y0},
            "sidebar": {"x": main_w, "y": 0, "width": sidebar_w, "height": canvas_h} if finisher else None,
        },
        "safe_zone": 40,
        "movement_boxes": movement_boxes,
        "has_finisher": bool(finisher),
    }


def get_brand_assets(stimulus: str) -> dict[str, Any]:
    """Map stimulus text to deterministic brand styling directives."""
    text = (stimulus or "").lower()
    lighting = "rim lighting"
    mood = "gritty industrial"

    if any(token in text for token in ("aerobic", "endurance", "benchmark")):
        lighting = "natural high-key lighting"
        mood = "athletic clean"
    elif any(token in text for token in ("power", "anaerobic", "grit", "high-intensity")):
        lighting = "low-key shadows with rim lighting"
        mood = "high intensity"

    return {
        "palette": {
            "base": "#0B0F14",
            "accent": "#007BFF",
            "text_primary": "#FFFFFF",
            "text_secondary": "#C7D2E3",
        },
        "typography": {
            "family": "Bold Sans Serif",
            "header_weight": 900,
            "body_weight": 700,
        },
        "lighting": lighting,
        "mood": mood,
        "constraints": [
            "High contrast text only",
            "No overlapping text blocks",
            "Maintain 40px safe zone",
        ],
    }


def _default_extract_text(image_path: str) -> str:
    try:
        import pytesseract  # type: ignore
        from PIL import Image
    except Exception as exc:  # pragma: no cover
        raise ToolExecutionError("OCR backend unavailable. Install pytesseract and system tesseract.") from exc

    try:
        img = Image.open(image_path)
    except Exception as exc:
        raise ToolExecutionError(f"unable to open image for OCR: {exc}") from exc
    return pytesseract.image_to_string(img)


def _normalize_for_match(text: str) -> str:
    return " ".join(text.lower().split())


def verify_image_accuracy(
    image_path: str,
    expected_rows: list[dict[str, str]],
    *,
    text_extractor: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Extract text from the generated image and compare against source facts."""
    extractor = text_extractor or _default_extract_text
    extracted_raw = extractor(image_path)
    extracted = _normalize_for_match(extracted_raw)

    checks: list[str] = []
    for row in expected_rows:
        name = str(row.get("name", "")).strip()
        reps = str(row.get("reps", "")).strip()
        rx_weight = str(row.get("rx_weight", "")).strip()

        if name and reps:
            checks.append(_normalize_for_match(f"{reps} {name}"))
        if rx_weight:
            checks.append(_normalize_for_match(rx_weight))

    if not checks:
        return {
            "is_valid": True,
            "similarity_score": 1.0,
            "mismatches": [],
            "extracted_text": extracted_raw,
        }

    mismatches = [token for token in checks if token not in extracted]
    matched = len(checks) - len(mismatches)
    similarity = matched / len(checks)

    return {
        "is_valid": similarity == 1.0,
        "similarity_score": round(similarity, 4),
        "mismatches": mismatches,
        "extracted_text": extracted_raw,
    }

"""workout_poster.py — Deterministic workout-poster renderer using Pillow.

Produces a 1024×576 px sports-infographic PNG styled to match the athlete
app palette: dark navy background (#050816), orange accent (#fb923c),
bold white movement names, Rx/Scaled badges, a right-side finisher panel
with amber border, and a footer strip.

No external services required. All layout is data-driven from WorkoutRecord.

Public API:
  build_poster_spec(workout: WorkoutRecord) -> WorkoutPosterSpec
  render_poster(spec: WorkoutPosterSpec, output_path: Path) -> None
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from PIL import Image, ImageDraw, ImageFont

    _PILLOW_AVAILABLE = True
except ImportError:
    _PILLOW_AVAILABLE = False

if TYPE_CHECKING:
    from theassembly.models import WorkoutRecord

# ---------------------------------------------------------------------------
# Palette — mirrors the athlete page CSS
# ---------------------------------------------------------------------------
_BG = (5, 8, 22)                 # #050816  app main background
_BG_FINISHER = (15, 23, 42)      # #0f172a  card background
_BG_FOOTER = (2, 6, 23)          # #020617  app bottom background
_ORANGE = (251, 146, 60)         # #fb923c  primary orange accent
_ORANGE_BAND = (30, 18, 5)       # dark orange tint for subtitle band
_WHITE = (226, 232, 240)         # #e2e8f0  primary text
_GRAY = (100, 116, 139)          # #64748b  slate secondary text
_GRAY_LABEL = (148, 163, 184)    # #94a3b8  lighter labels
_GREEN = (110, 231, 183)         # #6ee7b7  Rx weight badge
_AMBER = (252, 211, 77)          # #fcd34d  Scaled weight badge
_FINISHER_BORDER = (245, 158, 11)  # #f59e0b  amber finisher border
_SEP = (30, 41, 59)              # #1e293b  separator lines

# ---------------------------------------------------------------------------
# Canvas dimensions
# ---------------------------------------------------------------------------
_W = 1024
_H = 576
_HEADER_H = 108             # title + subtitle band
_FOOTER_H = 72              # footer strip
_MAIN_H = _H - _HEADER_H - _FOOTER_H   # 396 px
_DIV_X = 665                # vertical divider: left 65% / right 35%

# ---------------------------------------------------------------------------
# Movement row image strip geometry (matches reference poster layout)
# ---------------------------------------------------------------------------
_STRIP_X = 290           # x where the photo strip starts (after rep + text columns)
_STRIP_PAD = 7           # horizontal inner padding inside strip
_STRIP_ARROW_W = 12      # width of arrow glyph between frames
_STRIP_STEP_H = 16       # height reserved for step label below each frame
_STRIP_TOP_PAD = 8       # padding from row top edge to frame top

# ---------------------------------------------------------------------------
# Local visual asset roots (no AI generation)
# ---------------------------------------------------------------------------
_ASSET_ROOT = Path(__file__).resolve().parents[2] / "TheAssemblyData" / "photos"
_MOVEMENT_ASSET_ROOT = _ASSET_ROOT / "movement_strips"
_FINISHER_ASSET_ROOT = _ASSET_ROOT / "finisher"
_REFERENCE_POSTER = _ASSET_ROOT / "ai" / "posterReference.JPG"


def _slug(text: str) -> str:
    """Normalize movement names into filesystem-safe slugs."""
    out = []
    for ch in text.lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def _load_image_if_exists(path: Path):
    """Best-effort local image loader; returns None if path is missing/unreadable."""
    if not _PILLOW_AVAILABLE or not path.exists():
        return None
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return None


def _reference_strip_crop(index: int):
    """Crop a movement strip from posterReference as deterministic fallback visuals."""
    ref = _load_image_if_exists(_REFERENCE_POSTER)
    if ref is None:
        return None

    w, h = ref.size
    # Relative boxes tuned to the supplied posterReference layout.
    boxes = [
        (0.255, 0.205, 0.69, 0.43),
        (0.255, 0.43, 0.69, 0.655),
        (0.255, 0.655, 0.69, 0.885),
    ]
    i = max(0, min(index, len(boxes) - 1))
    x1r, y1r, x2r, y2r = boxes[i]
    box = (int(w * x1r), int(h * y1r), int(w * x2r), int(h * y2r))
    return ref.crop(box)


def _reference_finisher_crop():
    """Crop the finisher hero area from posterReference as fallback visual."""
    ref = _load_image_if_exists(_REFERENCE_POSTER)
    if ref is None:
        return None
    w, h = ref.size
    box = (int(w * 0.69), int(h * 0.47), int(w * 0.985), int(h * 0.84))
    return ref.crop(box)


def _hydrate_visual_assets(spec: "WorkoutPosterSpec") -> None:
    """Attach deterministic local visuals to rows/finisher without network calls."""
    if not _PILLOW_AVAILABLE:
        return

    # Movement strips: look for curated assets first, then fallback to reference crops.
    for idx, row in enumerate(spec.rows):
        slug = _slug(row.name)
        candidates = [
            _MOVEMENT_ASSET_ROOT / f"{slug}.png",
            _MOVEMENT_ASSET_ROOT / f"{slug}.jpg",
            _MOVEMENT_ASSET_ROOT / f"{slug}.jpeg",
        ]
        img = None
        for path in candidates:
            img = _load_image_if_exists(path)
            if img is not None:
                break
        if img is None:
            img = _reference_strip_crop(idx)
        row.image_frames = [img] if img is not None else []

    # Finisher hero: local asset first, then reference crop fallback.
    for row in spec.finisher_rows:
        slug = _slug(row.name)
        candidates = [
            _FINISHER_ASSET_ROOT / f"{slug}.png",
            _FINISHER_ASSET_ROOT / f"{slug}.jpg",
            _FINISHER_ASSET_ROOT / f"{slug}.jpeg",
        ]
        hero = None
        for path in candidates:
            hero = _load_image_if_exists(path)
            if hero is not None:
                break
        if hero is None:
            hero = _reference_finisher_crop()
        row.hero_image = hero

# ---------------------------------------------------------------------------
# Font paths (macOS system fonts; renderer falls back gracefully on Linux/CI)
# ---------------------------------------------------------------------------
_AVENIR = "/System/Library/Fonts/Avenir Next Condensed.ttc"
_HELV = "/System/Library/Fonts/HelveticaNeue.ttc"
_SFNS = "/System/Library/Fonts/SFNS.ttf"

# Avenir Next Condensed TTC indices (confirmed via Pillow):
#   0=Bold, 2=Demi Bold, 5=Medium, 7=Regular, 8=Heavy
# HelveticaNeue TTC indices:
#   0=Regular, 1=Bold, 4=Condensed Bold
_FONT_VARIANTS: dict[str, list[tuple[str, int]]] = {
    "heavy": [
        (_AVENIR, 8),    # Avenir Next Condensed Heavy
        (_AVENIR, 0),    # Avenir Next Condensed Bold
        (_HELV, 4),      # HelveticaNeue Condensed Bold
        (_HELV, 1),      # HelveticaNeue Bold
        (_SFNS, 0),
    ],
    "bold": [
        (_AVENIR, 0),    # Avenir Next Condensed Bold
        (_AVENIR, 2),    # Avenir Next Condensed Demi Bold
        (_HELV, 1),      # HelveticaNeue Bold
        (_SFNS, 0),
    ],
    "demibold": [
        (_AVENIR, 2),    # Avenir Next Condensed Demi Bold
        (_AVENIR, 5),    # Avenir Next Condensed Medium
        (_HELV, 4),      # HelveticaNeue Condensed Bold
        (_HELV, 0),
        (_SFNS, 0),
    ],
    "regular": [
        (_AVENIR, 7),    # Avenir Next Condensed Regular
        (_HELV, 0),      # HelveticaNeue Regular
        (_SFNS, 0),
    ],
}

_FONT_CACHE: dict[tuple[str, int], "ImageFont.FreeTypeFont"] = {}


def _font(variant: str, size: int) -> "ImageFont.FreeTypeFont":
    """Load a named font variant at the given size, with fallbacks."""
    cache_key = (variant, size)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    for path, index in _FONT_VARIANTS.get(variant, _FONT_VARIANTS["regular"]):
        try:
            fnt = ImageFont.truetype(path, size, index=index)
            _FONT_CACHE[cache_key] = fnt
            return fnt
        except (OSError, IOError):
            continue

    # Last resort: PIL built-in bitmap font (ugly but always available)
    fallback = ImageFont.load_default()
    _FONT_CACHE[cache_key] = fallback  # type: ignore[assignment]
    return fallback  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Movement step / annotation hints
# ---------------------------------------------------------------------------
_MOVEMENT_STEPS: dict[str, list[str]] = {
    "db squat cleans":   ["Deadlift", "Clean", "Squat"],
    "db squat snatches": ["Deadlift", "Pull", "Catch"],
    "db hang cleans":    ["Hinge", "Explode", "Catch"],
    "devil presses":     ["Burpee", "Row", "Press"],
    "wall balls":        ["Squat", "Drive", "Release"],
    "db deadlifts":      ["Hinge", "Pull", "Stand"],
    "renegade rows":     ["Plank", "Row L", "Row R"],
    "db thrusters":      ["Squat", "Drive", "Press"],
    "hang power cleans": ["Hinge", "Shrug", "Catch"],
}

_MOVEMENT_ANNOTATIONS: dict[str, str] = {
    "wall balls":       "Aim for target 10 ft / 9 ft",
    "double unders":    "Rope passes under feet twice per jump",
    "box step ups":     "Alternate legs each rep",
    "group mile run":   "Stay together as a group",
    "1-mile run":       "Track your pace",
    "team wall sit":    "Hold for full duration",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class PosterRow:
    reps: str
    name: str
    rx_weight: str = ""
    scaled_weight: str = ""
    notes: str = ""
    steps: list[str] = field(default_factory=list)
    annotation: str = ""
    image_frames: list = field(default_factory=list)  # list[PIL.Image.Image], optional per-step frames
    hero_image: object = None                         # PIL.Image.Image | None, for finisher hero


@dataclass
class WorkoutPosterSpec:
    title: str          # e.g. "5 ROUNDS FOR TIME"
    subtitle: str       # e.g. "WATERFALL START + ISOMETRIC FINISHER"
    rows: list[PosterRow]
    finisher_rows: list[PosterRow]
    footer_left: str = ""
    footer_right: str = ""
    stimulus: str = ""


# ---------------------------------------------------------------------------
# Spec builder
# ---------------------------------------------------------------------------
def build_poster_spec(workout: "WorkoutRecord") -> WorkoutPosterSpec:
    """Convert a WorkoutRecord into a WorkoutPosterSpec for rendering."""
    raw = workout.workout_content

    # Split on em-dash or regular dash to get title / subtitle
    if " — " in raw:
        title, subtitle = raw.split(" — ", 1)
    elif " - " in raw:
        title, subtitle = raw.split(" - ", 1)
    else:
        title, subtitle = raw, workout.stimulus

    title = title.strip().upper()
    subtitle = subtitle.strip().upper()

    rows: list[PosterRow] = []
    finisher_rows: list[PosterRow] = []

    for m in workout.movements:
        key = m.name.strip().lower()
        steps = list(_MOVEMENT_STEPS.get(key, []))
        # Use annotation hint if available; else keep the movement notes
        annotation = _MOVEMENT_ANNOTATIONS.get(key, "")

        row = PosterRow(
            reps=m.reps,
            name=m.name.strip().upper(),
            rx_weight=m.rx_weight,
            scaled_weight=m.scaled_weight,
            notes=m.notes,
            steps=steps,
            annotation=annotation,
        )

        if m.section.strip().lower() == "finisher":
            finisher_rows.append(row)
        else:
            rows.append(row)

    # Footer content
    footer_left = ""
    footer_right = ""
    raw_lower = raw.lower()

    if "waterfall" in raw_lower:
        footer_left = (
            "WATERFALL START: athletes stagger start by 2 min — each completes all rounds"
        )
        footer_right = "GO FAST. STAY TOGETHER. FINISH STRONG."
    elif "e2mom" in raw_lower or "emom" in raw_lower:
        footer_left = f"★  {raw}"
        footer_right = workout.technical_cues[0] if workout.technical_cues else ""
    elif "for time" in raw_lower:
        footer_right = "GO FAST. FINISH STRONG."
    elif "amrap" in raw_lower:
        footer_right = "MAXIMIZE REPS. STAY MOVING."

    if not footer_left and workout.technical_cues:
        footer_left = f"★  {workout.technical_cues[0]}"

    if not footer_right and workout.stimulus:
        footer_right = workout.stimulus.upper()

    return WorkoutPosterSpec(
        title=title,
        subtitle=subtitle,
        rows=rows,
        finisher_rows=finisher_rows,
        footer_left=footer_left,
        footer_right=footer_right,
        stimulus=workout.stimulus,
    )


# ---------------------------------------------------------------------------
# Internal drawing helpers
# ---------------------------------------------------------------------------
def _tbbox(draw: "ImageDraw.ImageDraw", text: str, font: "ImageFont.FreeTypeFont") -> tuple[int, int]:
    """Return (width, height) of a single-line text string."""
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


def _shadow_text(
    draw: "ImageDraw.ImageDraw",
    xy: tuple[int, int],
    text: str,
    font: "ImageFont.FreeTypeFont",
    fill: tuple[int, int, int],
    shadow: int = 2,
) -> None:
    draw.text((xy[0] + shadow, xy[1] + shadow), text, font=font, fill=(0, 0, 0))
    draw.text(xy, text, font=font, fill=fill)


def _fit_font(draw: "ImageDraw.ImageDraw", text: str, variant: str, max_size: int, max_width: int) -> "ImageFont.FreeTypeFont":
    """Return the largest font of *variant* up to *max_size* that fits *max_width*."""
    size = max_size
    while size >= 10:
        f = _font(variant, size)
        w, _ = _tbbox(draw, text, f)
        if w <= max_width:
            return f
        size -= 2
    return _font(variant, 10)


def _draw_image_strip(
    img: "Image.Image",
    draw: "ImageDraw.ImageDraw",
    row: "PosterRow",
    row_y: int,
    row_h: int,
) -> None:
    """Draw the per-movement photo strip — real images or styled dark placeholders.

    Layout (within each row):
      strip_x → _DIV_X-4 : shared strip zone
      ├─ [frame 0] ─► [frame 1] ─► [frame 2]
      └─ step labels below each frame
    """
    inner_x = _STRIP_X + _STRIP_PAD
    inner_w = _DIV_X - _STRIP_X - _STRIP_PAD - 4

    n_steps = len(row.steps)
    n_images = len(row.image_frames)
    # No steps and no images → single wide placeholder (no arrows/labels)
    n_frames = min(max(n_steps, n_images) if (n_steps or n_images) else 1, 3)
    n_arrows = n_frames - 1

    frame_w = (inner_w - n_arrows * _STRIP_ARROW_W) // n_frames
    frame_h = row_h - _STRIP_TOP_PAD - _STRIP_STEP_H - 6
    frame_top = row_y + _STRIP_TOP_PAD
    step_y = frame_top + frame_h + 3

    f_step = _font("regular", 10)
    f_hint = _font("regular", 12)

    for i in range(n_frames):
        fx = inner_x + i * (frame_w + _STRIP_ARROW_W)

        # ── Frame: real image or dark placeholder ─────────────────────
        if i < len(row.image_frames) and row.image_frames[i] is not None:
            resized = row.image_frames[i].resize(
                (frame_w, frame_h), Image.Resampling.LANCZOS
            ).convert("RGB")
            img.paste(resized, (fx, frame_top))
        else:
            draw.rectangle(
                [(fx, frame_top), (fx + frame_w, frame_top + frame_h)],
                fill=_BG_FINISHER,
                outline=_SEP,
                width=1,
            )
            # Step hint text centred in placeholder
            hint = row.steps[i].upper() if i < n_steps else ""
            if hint:
                hw, hh = _tbbox(draw, hint, f_hint)
                draw.text(
                    (fx + (frame_w - hw) // 2, frame_top + (frame_h - hh) // 2),
                    hint, font=f_hint, fill=_GRAY,
                )

        # ── Step label below frame ─────────────────────────────────────
        if i < n_steps:
            label = f"{i + 1}. {row.steps[i].upper()}"
            lw, _ = _tbbox(draw, label, f_step)
            draw.text(
                (fx + (frame_w - lw) // 2, step_y),
                label, font=f_step, fill=_GRAY_LABEL,
            )

        # ── Orange arrow to next frame ─────────────────────────────────
        if i < n_frames - 1:
            ax = fx + frame_w + _STRIP_ARROW_W // 2
            ay = frame_top + frame_h // 2
            s = 5
            draw.polygon(
                [(ax - s, ay - s), (ax + s, ay), (ax - s, ay + s)],
                fill=_ORANGE,
            )


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------
def _draw_header(
    draw: "ImageDraw.ImageDraw", spec: WorkoutPosterSpec
) -> None:
    """Title (huge) + orange-tinted subtitle band."""
    # --- Title ---
    f_title = _fit_font(draw, spec.title, "heavy", 68, _W - 40)
    tw, th = _tbbox(draw, spec.title, f_title)
    title_y = 6
    draw.text(((_W - tw) // 2, title_y), spec.title, font=f_title, fill=_WHITE)

    # --- Subtitle band ---
    band_top = title_y + th + 4
    band_bot = _HEADER_H
    draw.rectangle([(0, band_top), (_W, band_bot)], fill=_ORANGE_BAND)
    # 2 px orange accent line on top edge of band
    draw.line([(0, band_top), (_W, band_top)], fill=_ORANGE, width=2)

    band_h = band_bot - band_top
    f_sub = _fit_font(draw, spec.subtitle, "demibold", 26, _W - 80)
    sw, sh = _tbbox(draw, spec.subtitle, f_sub)
    draw.text(
        ((_W - sw) // 2, band_top + (band_h - sh) // 2),
        spec.subtitle, font=f_sub, fill=_ORANGE,
    )


def _draw_movement_rows(
    img: "Image.Image",
    draw: "ImageDraw.ImageDraw",
    rows: list["PosterRow"],
) -> None:
    """Left panel: fixed-zone grid matching the reference poster.

    Each row is divided into three fixed columns:
      1. Rep number  (x=14…114, width~100px)
      2. Text zone   (x=118…282, width~164px) — name, badges, notes
      3. Image strip (x=290…_DIV_X) — 3 movement frames + step labels
    """
    if not rows:
        return

    n = len(rows)
    row_h = _MAIN_H // n
    y0 = _HEADER_H

    left_pad = 14
    rep_col_w = 100          # rep number column width
    name_x = left_pad + rep_col_w + 4   # text column starts at x=118
    name_col_w = _STRIP_X - name_x - 8  # ~164 px

    f_badge = _font("regular", 14)
    _, badge_lh = _tbbox(draw, "X", f_badge)
    f_note = _font("regular", 11)
    _, note_lh = _tbbox(draw, "X", f_note)

    for idx, row in enumerate(rows):
        y = y0 + idx * row_h

        if idx > 0:
            draw.line([(0, y), (_DIV_X, y)], fill=_SEP, width=1)

        # ── Rep number (vertically centred in row) ───────────────────────────
        rep_cx = left_pad + rep_col_w // 2
        f_reps = _fit_font(draw, row.reps, "heavy", min(62, row_h - 12), rep_col_w - 4)
        rw, rh = _tbbox(draw, row.reps, f_reps)
        draw.text((rep_cx - rw // 2, y + (row_h - rh) // 2), row.reps, font=f_reps, fill=_ORANGE)

        # ── Movement name: 3+ words → 2 lines, else 1 line ──────────────────
        name_words = row.name.split()
        if len(name_words) >= 3:
            mid = (len(name_words) + 1) // 2
            l1 = " ".join(name_words[:mid])
            l2 = " ".join(name_words[mid:])
            f_name = _fit_font(draw, max(l1, l2, key=len), "bold", min(26, row_h // 3), name_col_w)
            _, nh = _tbbox(draw, l1, f_name)
            name_lines = [l1, l2]
        else:
            f_name = _fit_font(draw, row.name, "bold", min(26, row_h // 3), name_col_w)
            _, nh = _tbbox(draw, row.name, f_name)
            name_lines = [row.name]

        # Measure total content block height
        total_name_h = len(name_lines) * (nh + 2)
        has_badges = bool(row.rx_weight or row.scaled_weight)
        badge_h = (badge_lh + 4) if has_badges else 0

        note_text = row.notes or row.annotation
        wrapped_notes: list[str] = []
        if note_text:
            wrapped_notes = textwrap.wrap(note_text, width=max(14, name_col_w // 7))[:2]
        note_h = len(wrapped_notes) * (note_lh + 2)

        content_h = total_name_h + (4 + badge_h if has_badges else 0) + (3 + note_h if note_h else 0)
        content_y = y + max(8, (row_h - content_h) // 2)

        # ── Draw name lines ────────────────────────────────────────────
        cur_y = content_y
        for line in name_lines:
            draw.text((name_x, cur_y), line, font=f_name, fill=_WHITE)
            cur_y += nh + 2
        cur_y += 4

        # ── Weight badges ───────────────────────────────────────────────
        if has_badges:
            dot_r = 3
            dot_cy = cur_y + badge_lh // 2
            bx = name_x
            if row.rx_weight:
                draw.ellipse(
                    [(bx, dot_cy - dot_r), (bx + dot_r * 2, dot_cy + dot_r)],
                    fill=_GREEN,
                )
                bx += dot_r * 2 + 3
                rxt, _ = _tbbox(draw, row.rx_weight, f_badge)
                draw.text((bx, cur_y), row.rx_weight, font=f_badge, fill=_GREEN)
                bx += rxt + 10
            if row.scaled_weight:
                draw.ellipse(
                    [(bx, dot_cy - dot_r), (bx + dot_r * 2, dot_cy + dot_r)],
                    outline=_AMBER,
                    width=2,
                )
                bx += dot_r * 2 + 3
                draw.text((bx, cur_y), row.scaled_weight, font=f_badge, fill=_AMBER)
            cur_y += badge_h + 2

        # ── Notes / annotation ──────────────────────────────────────────
        for line in wrapped_notes:
            draw.text((name_x, cur_y), line, font=f_note, fill=_GRAY)
            cur_y += note_lh + 2

        # ── Image strip (right portion of left panel) ─────────────────────
        _draw_image_strip(img, draw, row, y, row_h)


def _draw_finisher_panel(
    img: "Image.Image",
    draw: "ImageDraw.ImageDraw",
    rows: list["PosterRow"],
) -> None:
    """Right panel: finisher block with fixed zones — rep, name, hero image, penalty."""
    px1, py1 = _DIV_X, _HEADER_H
    px2, py2 = _W, _HEADER_H + _MAIN_H
    panel_w = px2 - px1
    cx = px1 + panel_w // 2

    draw.rectangle([(px1, py1), (px2, py2)], fill=_BG_FINISHER)
    draw.line([(px1, py1), (px1, py2)], fill=_FINISHER_BORDER, width=2)

    # ── Fixed header zone: "FINISHER" label + underline (≈50 px) ───────────
    f_label = _font("bold", 18)
    lw, lh = _tbbox(draw, "FINISHER", f_label)
    header_y = py1 + 12
    draw.text((cx - lw // 2, header_y), "FINISHER", font=f_label, fill=_ORANGE)
    underline_y = header_y + lh + 4
    draw.line([(px1 + 18, underline_y), (px2 - 18, underline_y)], fill=_ORANGE, width=1)
    content_top = underline_y + 8

    if not rows:
        f_rest = _font("bold", 30)
        rw, rh = _tbbox(draw, "REST", f_rest)
        draw.text(
            (cx - rw // 2, content_top + (py2 - content_top - rh) // 2),
            "REST", font=f_rest, fill=_GRAY,
        )
        return

    row = rows[0]

    # Fixed vertical zones (from content_top down):
    #   [rep number  60px]
    #   [name        38px]
    #   [hero image  fills remaining space]
    #   [penalty     36px if row.notes present]
    rep_zone_h = 60
    name_zone_h = 38
    has_penalty = bool(row.notes)
    penalty_zone_h = 38 if has_penalty else 0

    hero_y1 = content_top + rep_zone_h + name_zone_h
    hero_y2 = py2 - penalty_zone_h - 4
    hero_h = max(0, hero_y2 - hero_y1)
    hero_w = panel_w - 16

    # ── Rep number ───────────────────────────────────────────────────
    f_reps = _fit_font(draw, row.reps, "heavy", 56, panel_w - 20)
    rw, rh = _tbbox(draw, row.reps, f_reps)
    draw.text(
        (cx - rw // 2, content_top + (rep_zone_h - rh) // 2),
        row.reps, font=f_reps, fill=_WHITE,
    )

    # ── Movement name ───────────────────────────────────────────────
    f_name = _fit_font(draw, row.name, "bold", 26, panel_w - 20)
    nw, nh = _tbbox(draw, row.name, f_name)
    draw.text(
        (cx - nw // 2, content_top + rep_zone_h + (name_zone_h - nh) // 2),
        row.name, font=f_name, fill=_WHITE,
    )

    # ── Hero image or dark placeholder ────────────────────────────────
    hero_x = px1 + 8
    if hero_h > 20:
        if row.hero_image is not None:
            hero_resized = row.hero_image.resize(
                (hero_w, hero_h), Image.Resampling.LANCZOS
            ).convert("RGB")
            img.paste(hero_resized, (hero_x, hero_y1))
        else:
            draw.rectangle(
                [(hero_x, hero_y1), (hero_x + hero_w, hero_y2)],
                fill=(8, 14, 30),
                outline=_SEP,
                width=1,
            )
            # Show movement name as hint inside placeholder
            f_hint = _fit_font(draw, row.name, "regular", 16, hero_w - 16)
            hw, hh = _tbbox(draw, row.name, f_hint)
            draw.text(
                (hero_x + (hero_w - hw) // 2, hero_y1 + (hero_h - hh) // 2),
                row.name, font=f_hint, fill=_GRAY,
            )

    # ── Penalty / notes strip ──────────────────────────────────────
    if has_penalty:
        pz_top = hero_y2 + 4
        # Amber warning bar on left edge
        draw.rectangle(
            [(px1 + 8, pz_top + 3), (px1 + 13, py2 - 5)],
            fill=_AMBER,
        )
        f_penalty = _font("regular", 12)
        max_chars = max(12, (panel_w - 30) // 7)
        lines = textwrap.wrap(row.notes.upper(), width=max_chars)[:2]
        _, plh = _tbbox(draw, "X", f_penalty)
        total_ph = len(lines) * (plh + 2)
        py = pz_top + max(0, (py2 - pz_top - total_ph) // 2)
        for line in lines:
            plw, _ = _tbbox(draw, line, f_penalty)
            draw.text((cx - plw // 2, py), line, font=f_penalty, fill=_AMBER)
            py += plh + 2


def _draw_footer(
    draw: "ImageDraw.ImageDraw", spec: WorkoutPosterSpec
) -> None:
    """Footer strip with left note and right motto."""
    fy = _HEADER_H + _MAIN_H
    draw.rectangle([(0, fy), (_W, _H)], fill=_BG_FOOTER)
    # Orange top border matches .workout-caption border-left style
    draw.line([(0, fy), (_W, fy)], fill=_ORANGE, width=2)

    pad = 20
    inner_h = _FOOTER_H - 8

    if spec.footer_left:
        f_left = _font("regular", 13)
        max_chars = max(30, (_DIV_X - pad * 2) // 7)
        lines = textwrap.wrap(spec.footer_left, width=max_chars)[:3]
        _, line_h = _tbbox(draw, "X", f_left)
        total_h = len(lines) * (line_h + 3)
        ty = fy + max(4, (inner_h - total_h) // 2)
        for line in lines:
            draw.text((pad, ty), line, font=f_left, fill=_GRAY_LABEL)
            ty += line_h + 3

    if spec.footer_right:
        f_right = _font("bold", 14)
        fw, fh = _tbbox(draw, spec.footer_right, f_right)
        max_right_w = _W - _DIV_X - pad * 2
        if fw > max_right_w:
            f_right = _fit_font(draw, spec.footer_right, "bold", 14, max_right_w)
            fw, fh = _tbbox(draw, spec.footer_right, f_right)
        draw.text(
            (_W - fw - pad, fy + (inner_h - fh) // 2 + 4),
            spec.footer_right, font=f_right, fill=_WHITE,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_poster(spec: WorkoutPosterSpec, output_path: Path) -> None:
    """Render the workout poster PNG to *output_path*.

    Args:
        spec: A :class:`WorkoutPosterSpec` built by :func:`build_poster_spec`.
        output_path: Destination file path (parent dirs are created if needed).

    Raises:
        RuntimeError: If Pillow is not installed.
    """
    if not _PILLOW_AVAILABLE:
        raise RuntimeError(
            "Pillow is required to render workout posters. "
            "Install it with: pip install Pillow"
        )

    _hydrate_visual_assets(spec)

    img = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(img)

    _draw_header(draw, spec)
    _draw_movement_rows(img, draw, spec.rows)
    _draw_finisher_panel(img, draw, spec.finisher_rows)
    _draw_footer(draw, spec)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG", optimize=True)

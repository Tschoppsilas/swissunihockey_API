from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ..fonts import load_font
from ..tables import TableRow
from .base_card import (
    CANVAS_CENTER_X,
    CARD_BG,
    CARD_MUTED,
    CARD_RADIUS,
    CARD_TEXT,
    CONTENT_WIDTH,
    CONTENT_X,
    FONT_BOLD,
    FONT_REGULAR,
    HEADER_Y,
    HORIZONTAL_SCALE_DAMPING,
    TVO_RED,
    CARD_PADDING_X,
)
from .instagram_v1 import InstagramV1Template

TABLE_TITLE = "TABELLE"

# Geometry at scale 1.0 (the same card look as the game cards: 60 px rows, 10 px apart).
ROW_H = 60
ROW_GAP = 10
HEADER_H = 40
HEADER_GAP = 8
ROW_FONT_SIZE = 26
HEADER_FONT_SIZE = 20
COLUMN_GAP = 18

TITLE_MAX_H = 150  # the big "TABELLE"; the font is as large as fits this height
TITLE_SUBTITLE_GAP = 10
SUBTITLE_STAND_GAP = 8
TITLE_TABLE_GAP = 22

MAX_TABLE_SCALE = 1.4  # same ceiling as the game cards
MIN_TABLE_SCALE = 0.3  # a name is never cut off: below this the post would be unreadable anyway
SCALE_STEP = 0.02

TEXT_DARK = (24, 24, 24, 255)
TEXT_DARK_SOFT = (70, 70, 70, 255)


class TableTemplate(InstagramV1Template):
    """The table post (feed format): big centered "TABELLE", the league text and
    "Stand: ..." beneath it, then one dark card per table row. Every TVO row is
    drawn in the bright red of the TVO label on the game cards, all others in
    white. One uniform scale per image fits all rows on the page and is stepped
    down until the longest team name and all columns fit - names are never
    truncated."""

    def __init__(self, **kwargs) -> None:
        super().__init__(kind="results", **kwargs)

    # --- columns -----------------------------------------------------------

    @staticmethod
    def _columns(show_overtime: bool) -> list[tuple[str, str, str]]:
        """(key, header, align) in display order."""
        columns = [("rank", "Rg", "center"), ("team", "Team", "left"), ("games", "Sp", "right"), ("wins", "S", "right")]
        if show_overtime:
            columns.append(("wins_overtime", "SnV", "right"))
        columns.append(("ties", "U", "right"))
        if show_overtime:
            columns.append(("defeats_overtime", "NnV", "right"))
        columns += [
            ("defeats", "N", "right"),
            ("goals", "Tore", "right"),
            ("diff", "Diff", "right"),
            ("points", "Pkt", "right"),
        ]
        return columns

    @staticmethod
    def _cell(row: TableRow, key: str) -> str:
        entry = row.entry
        if key == "rank":
            return str(entry.place)
        if key == "team":
            return row.name.upper()
        if key == "goals":
            return f"{entry.goals_for}:{entry.goals_against}"
        if key == "diff":
            diff = entry.goal_difference
            return f"{diff:+d}" if diff else "0"
        return str(getattr(entry, key))

    # --- text helpers ---------------------------------------------------------

    @staticmethod
    def _line_height(font) -> int:
        ascent, descent = font.getmetrics()
        return ascent + descent

    def _fit_lines(self, draw, text: str, font_path, max_width: float, start: int, single_floor: int, floor: int):
        """The largest font in which `text` fits on one line (down to single_floor);
        failing that, wrapped onto two lines (down to floor); failing that, on one
        line at an ever smaller size. Never truncated."""
        for size in range(start, single_floor - 1, -2):
            font = load_font(font_path, size)
            if draw.textlength(text, font=font) <= max_width:
                return font, [text]

        words = text.split()
        for size in range(start, floor - 1, -2):
            font = load_font(font_path, size)
            best = None
            for cut in range(1, len(words)):
                first, second = " ".join(words[:cut]), " ".join(words[cut:])
                widest = max(draw.textlength(first, font=font), draw.textlength(second, font=font))
                if best is None or widest < best[0]:
                    best = (widest, [first, second])
            if best is not None and best[0] <= max_width:
                return font, best[1]

        for size in range(floor, 7, -1):
            font = load_font(font_path, size)
            if draw.textlength(text, font=font) <= max_width:
                return font, [text]
        return load_font(font_path, 8), [text]

    # --- layout ------------------------------------------------------------------

    def _layout(self, draw, rows: list[TableRow], columns, scale: float):
        """Fonts and column widths at this scale, or None if the longest name does
        not fit the team column yet."""
        h_scale = 1 + (scale - 1) * HORIZONTAL_SCALE_DAMPING
        row_font = load_font(FONT_BOLD, max(8, round(ROW_FONT_SIZE * scale)))
        header_font = load_font(FONT_BOLD, max(7, round(HEADER_FONT_SIZE * scale)))
        padding = CARD_PADDING_X * h_scale
        gap = COLUMN_GAP * h_scale

        widths: dict[str, float] = {}
        for key, header, _ in columns:
            if key == "team":
                continue
            values = [draw.textlength(self._cell(r, key), font=row_font) for r in rows]
            widths[key] = max(values + [draw.textlength(header, font=header_font)])

        numeric_gaps = max(1, len(columns) - 3)  # gaps between the numeric columns
        fixed = sum(widths.values()) + gap * (len(columns) - 1)
        widths["team"] = CONTENT_WIDTH - 2 * padding - fixed
        longest = max(draw.textlength(self._cell(r, "team"), font=row_font) for r in rows)
        if longest > widths["team"]:
            return None

        # Spare room goes partly into airier gaps between the numeric columns (the
        # team column keeps the rest, so a name never gets less than it needs).
        extra = min(0.5 * (widths["team"] - longest) / numeric_gaps, gap * 1.6)
        gaps = [gap, gap] + [gap + extra] * (len(columns) - 2)
        widths["team"] -= extra * numeric_gaps
        return {"row_font": row_font, "header_font": header_font, "padding": padding, "gaps": gaps, "widths": widths}

    # --- drawing -----------------------------------------------------------------

    def render_table(
        self, rows: list[TableRow], show_overtime: bool, subtitle: str, stand_text: str
    ) -> tuple[Image.Image, float]:
        if not rows:
            raise ValueError("Keine Zeilen fuer die Tabelle.")
        image = self.background().convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        columns = self._columns(show_overtime)

        title_font = self._fit_title_font(draw, TABLE_TITLE, CONTENT_WIDTH, TITLE_MAX_H)
        title_h = self._line_height(title_font)
        sub_font, sub_lines = self._fit_lines(draw, subtitle, FONT_BOLD, CONTENT_WIDTH, 40, 28, 18)
        sub_lh = self._line_height(sub_font)
        stand_font, stand_lines = self._fit_lines(draw, stand_text, FONT_REGULAR, CONTENT_WIDTH, 28, 20, 16)
        stand_lh = self._line_height(stand_font)
        title_block = (
            title_h + TITLE_SUBTITLE_GAP + len(sub_lines) * sub_lh + SUBTITLE_STAND_GAP + len(stand_lines) * stand_lh
        )

        region_top, region_bottom = HEADER_Y, self.profile.content_bottom
        count = len(rows)
        base_total = HEADER_H + HEADER_GAP + count * ROW_H + (count - 1) * ROW_GAP
        available = region_bottom - region_top - title_block - TITLE_TABLE_GAP

        scale = min(MAX_TABLE_SCALE, available / base_total)
        layout = None
        while scale >= MIN_TABLE_SCALE:
            layout = self._layout(draw, rows, columns, scale)
            if layout is not None:
                break
            scale -= SCALE_STEP
        if layout is None:
            raise ValueError("Die Tabelle passt auch bei kleinster Schrift nicht auf das Bild.")

        block_h = title_block + TITLE_TABLE_GAP + base_total * scale
        y = region_top + max(0.0, (region_bottom - region_top - block_h) / 2)

        # title block
        draw.text((CANVAS_CENTER_X, y), TABLE_TITLE, font=title_font, fill=TVO_RED, anchor="ma")
        y += title_h + TITLE_SUBTITLE_GAP
        for line in sub_lines:
            draw.text((CANVAS_CENTER_X, y), line, font=sub_font, fill=TEXT_DARK, anchor="ma")
            y += sub_lh
        y += SUBTITLE_STAND_GAP
        for line in stand_lines:
            draw.text((CANVAS_CENTER_X, y), line, font=stand_font, fill=TEXT_DARK_SOFT, anchor="ma")
            y += stand_lh
        y += TITLE_TABLE_GAP

        # header card, then one card per row
        radius = CARD_RADIUS * scale
        x_left = CONTENT_X
        x_right = CONTENT_X + CONTENT_WIDTH
        header_box = [x_left, y, x_right, y + HEADER_H * scale]
        draw.rounded_rectangle(
            header_box, radius=radius, fill=CARD_BG,
            outline=self.border_color, width=1 if self.border_color else 0,
        )
        self._draw_cells(draw, columns, layout, header_box, [header for _, header, _ in columns], CARD_MUTED, True)
        y += (HEADER_H + HEADER_GAP) * scale

        for row in rows:
            box = [x_left, y, x_right, y + ROW_H * scale]
            if self.shadow_offset and self.shadow_color:
                self._draw_soft_bottom_shadow(image, box, radius)
            draw.rounded_rectangle(
                box, radius=radius, fill=CARD_BG,
                outline=self.border_color, width=1 if self.border_color else 0,
            )
            color = self.tvo_label_color if row.is_tvo else CARD_TEXT
            self._draw_cells(draw, columns, layout, box, [self._cell(row, key) for key, _, _ in columns], color, False)
            y += (ROW_H + ROW_GAP) * scale

        return image, scale

    def _draw_cells(self, draw, columns, layout, box, texts, color, is_header: bool) -> None:
        font = layout["header_font"] if is_header else layout["row_font"]
        cy = (box[1] + box[3]) / 2
        cursor = box[0] + layout["padding"]
        for index, ((key, _, align), text) in enumerate(zip(columns, texts)):
            width = layout["widths"][key]
            if align == "left":
                draw.text((cursor, cy), text, font=font, fill=color, anchor="lm")
            elif align == "center":
                draw.text((cursor + width / 2, cy), text, font=font, fill=color, anchor="mm")
            else:
                draw.text((cursor + width, cy), text, font=font, fill=color, anchor="rm")
            cursor += width + layout["gaps"][index]

    def render_to(self, out_path: Path, rows, show_overtime: bool, subtitle: str, stand_text: str) -> float:
        image, scale = self.render_table(rows, show_overtime, subtitle, stand_text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(out_path)
        return scale

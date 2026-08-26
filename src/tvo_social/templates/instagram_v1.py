from __future__ import annotations

from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw

from .. import layout
from ..fonts import fit_line, load_font
from ..models import TeamGame

BACKGROUND_PATH = Path(__file__).parent / "assets" / "background_v1.png"

FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"

TVO_RED = (200, 16, 33)
BANNER_TEXT = (255, 255, 255)
CARD_BG = (24, 24, 24)
CARD_TEXT = (255, 255, 255)
CARD_MUTED = (185, 185, 185)

WIN_COLOR = (70, 200, 110)
LOSS_COLOR = (230, 65, 65)
DRAW_COLOR = (235, 180, 45)
UNKNOWN_COLOR = (255, 255, 255)

RESULT_COLORS: dict[str, tuple[int, int, int]] = {
    "win": WIN_COLOR,
    "loss": LOSS_COLOR,
    "draw": DRAW_COLOR,
    "unknown": UNKNOWN_COLOR,
}

# Safe content zone: below the top-left club logo, clear of the right margin.
CONTENT_X = 60
CONTENT_WIDTH = 960
HEADER_Y = 230
CONTENT_TOP = layout.CONTENT_TOP

BANNER_HEIGHT = layout.BANNER_HEIGHT
BANNER_RADIUS = 14
BANNER_PADDING_X = 24
BANNER_GAP_BELOW = layout.BANNER_GAP_BELOW

CARD_RADIUS = 16
CARD_PADDING_X = 24
CARD_GAP = layout.CARD_GAP
SECTION_GAP = layout.SECTION_GAP

CARD_HEIGHT_RESULTS = layout.CARD_HEIGHT["results"]
CARD_HEIGHT_ANNOUNCE = layout.CARD_HEIGHT["announce"]


class InstagramV1Template:
    canvas_size = layout.CANVAS_SIZE

    def __init__(self, kind: Literal["announce", "results"]) -> None:
        self.kind = kind

    def background(self) -> Image.Image:
        return Image.open(BACKGROUND_PATH).convert("RGB")

    def render(
        self,
        image: Image.Image,
        categorized_games: dict[str, list[TeamGame]],
        page_idx: int,
        page_count: int,
        title: str,
    ) -> None:
        draw = ImageDraw.Draw(image)

        header = title
        if page_count > 1:
            header += f" - {page_idx + 1}/{page_count}"
        header_font = load_font(FONT_BOLD, 34)
        draw.text(
            (CONTENT_X, HEADER_Y),
            fit_line(draw, header, header_font, CONTENT_WIDTH),
            font=header_font,
            fill=TVO_RED,
        )

        banner_font = load_font(FONT_BOLD, 24)
        info_font = load_font(FONT_REGULAR, 20)
        matchup_font = load_font(FONT_BOLD, 26)
        score_font = load_font(FONT_BOLD, 30)

        y = CONTENT_TOP
        for category, team_games in categorized_games.items():
            y = self._draw_category_banner(draw, category, y, banner_font)
            for tg in team_games:
                y = self._draw_card(draw, tg, y, info_font, matchup_font, score_font)
            y += SECTION_GAP - CARD_GAP

    def _draw_category_banner(self, draw: ImageDraw.ImageDraw, category: str, y: int, font) -> int:
        label = category.upper()
        text_width = draw.textlength(label, font=font)
        banner_width = min(text_width + 2 * BANNER_PADDING_X, CONTENT_WIDTH)
        draw.rounded_rectangle(
            [CONTENT_X, y, CONTENT_X + banner_width, y + BANNER_HEIGHT],
            radius=BANNER_RADIUS,
            fill=TVO_RED,
        )
        draw.text(
            (CONTENT_X + BANNER_PADDING_X, y + BANNER_HEIGHT / 2),
            fit_line(draw, label, font, banner_width - 2 * BANNER_PADDING_X),
            font=font,
            fill=BANNER_TEXT,
            anchor="lm",
        )
        return y + BANNER_HEIGHT + BANNER_GAP_BELOW

    def _draw_card(
        self, draw: ImageDraw.ImageDraw, tg: TeamGame, y: int, info_font, matchup_font, score_font
    ) -> int:
        height = CARD_HEIGHT_RESULTS if self.kind == "results" else CARD_HEIGHT_ANNOUNCE
        draw.rounded_rectangle(
            [CONTENT_X, y, CONTENT_X + CONTENT_WIDTH, y + height],
            radius=CARD_RADIUS,
            fill=CARD_BG,
        )

        if self.kind == "results":
            score_text = tg.score_text()
            score_color = RESULT_COLORS[tg.result_kind()]
            draw.text(
                (CONTENT_X + CARD_PADDING_X, y + height / 2),
                score_text,
                font=score_font,
                fill=score_color,
                anchor="lm",
            )
            score_width = draw.textlength(score_text + "  ", font=score_font)
            opponent_text = f"VS {tg.opponent.upper()}"
            remaining_width = CONTENT_WIDTH - 2 * CARD_PADDING_X - score_width
            draw.text(
                (CONTENT_X + CARD_PADDING_X + score_width, y + height / 2),
                fit_line(draw, opponent_text, matchup_font, remaining_width),
                font=matchup_font,
                fill=CARD_TEXT,
                anchor="lm",
            )
        else:
            time_str = tg.game.time or "TBD"
            info_line = f"{tg.game.date.strftime('%d.%m.')} {time_str} · {tg.game.venue}"
            draw.text(
                (CONTENT_X + CARD_PADDING_X, y + 22),
                fit_line(draw, info_line, info_font, CONTENT_WIDTH - 2 * CARD_PADDING_X),
                font=info_font,
                fill=CARD_MUTED,
                anchor="lm",
            )
            matchup_text = f"VS {tg.opponent.upper()}"
            draw.text(
                (CONTENT_X + CARD_PADDING_X, y + 58),
                fit_line(draw, matchup_text, matchup_font, CONTENT_WIDTH - 2 * CARD_PADDING_X),
                font=matchup_font,
                fill=CARD_TEXT,
                anchor="lm",
            )

        return y + height + CARD_GAP

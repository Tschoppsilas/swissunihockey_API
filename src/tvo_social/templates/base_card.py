from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter

from .. import layout
from ..fonts import fit_line, load_font
from ..grouping import format_date_range
from ..icons import draw_clock_icon, draw_pin_icon
from ..models import TeamGame

FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_REGULAR = "C:/Windows/Fonts/arial.ttf"

TVO_LABEL = "TV OBERWIL"

TVO_RED = (200, 16, 33, 255)
BANNER_TEXT = (255, 255, 255, 255)
CARD_BG = (24, 24, 24, 255)
CARD_TEXT = (255, 255, 255, 255)
CARD_MUTED = (185, 185, 185, 255)

WIN_COLOR = (70, 200, 110, 255)
LOSS_COLOR = (230, 65, 65, 255)
DRAW_COLOR = (235, 180, 45, 255)
UNKNOWN_COLOR = (255, 255, 255, 255)

RESULT_COLORS: dict[str, tuple[int, int, int, int]] = {
    "win": WIN_COLOR,
    "loss": LOSS_COLOR,
    "draw": DRAW_COLOR,
    "unknown": UNKNOWN_COLOR,
}

# TVO_RED (the brand red) is calibrated for light surfaces (banner, header) -
# on the near-black card background it's too low-contrast to read well, so
# "TV OBERWIL" in the matchup line uses this brighter, dark-background-safe
# red instead, to stay distinguishable from the opponent without a contrast
# problem.
TVO_RED_ON_DARK = (255, 64, 84, 255)

# Finalized card finish, confirmed over several draft rounds: a hairline
# white edge all around, plus a soft blurred white glow hugging the bottom
# ("draft2" of the box-shadow comparison) for a subtle lifted-card look.
DEFAULT_BORDER_COLOR: tuple[int, int, int, int] | None = (255, 255, 255, 26)  # ~0.10 alpha
DEFAULT_SHADOW_OFFSET = 3
DEFAULT_SHADOW_BLUR = 5
DEFAULT_SHADOW_COLOR: tuple[int, int, int, int] | None = (255, 255, 255, 41)  # ~0.16 alpha

# Confirmed as "spacing_draft2_plus_100" - noticeably airier than the initial
# tight layout.
DEFAULT_TIME_MATCHUP_GAP = 48

# Deliberately off-brand (amber, not red/black/white) so it reads as a
# warning/attention marker distinct from the club's own styling - a stamp
# that could be mistaken for a normal design element would defeat its point.
DEFAULT_MISSING_VENUE_TEXT = "ORT FOLGT"
STAMP_BG = (255, 176, 32, 235)
STAMP_TEXT = (20, 20, 20, 255)
STAMP_ANGLE = -10

# Safe content zone: below the top-left club logo, clear of the right margin.
# Shared by every template - both feed and story canvases are 1080px wide,
# only their available height differs (see layout.CanvasProfile). These stay
# fixed regardless of scale - only vertical sizes/fonts scale up when a page
# has few categories/games to show (see layout.compute_scale).
CONTENT_X = 60
CONTENT_WIDTH = 960
HEADER_Y = 230  # top boundary for the title zone, below the logo
CANVAS_CENTER_X = 540  # canvas width (1080) is the same for every profile

TITLE_MIN_FONT_SIZE = 34
TITLE_MAX_FONT_SIZE = 300
MIN_TITLE_GAP = 4  # tiny safety margin only, not a comfort gap - the title
# is meant to claim as much of the available space as it can.

BANNER_HEIGHT = layout.BANNER_HEIGHT
BANNER_PADDING_X = 20
BANNER_GAP_BELOW = layout.BANNER_GAP_BELOW

PILL_GAP_AFTER_BANNER = 12
PILL_PADDING_X = 16
PILL_ICON_AREA = 22
PILL_MIN_WIDTH = 40  # skip drawing the venue pill if less room than this

CARD_RADIUS = 16
CARD_PADDING_X = 24
CARD_GAP = layout.CARD_GAP
SECTION_GAP = layout.SECTION_GAP

ICON_RADIUS = 12
ICON_TEXT_GAP = 12

# Horizontal paddings/gaps grow slower than font size / vertical spacing at
# high scale, so enlarged text has more room to actually fit instead of
# padding eating into it just as fast as the text grows.
HORIZONTAL_SCALE_DAMPING = 0.4

# How far (in scale units) each step of the text-fit search backs off.
SCALE_SEARCH_STEP = 0.05


@dataclass
class Metrics:
    """All the scaled pixel sizes and fonts for one page's render, computed
    once from layout.compute_scale() so a sparse page (e.g. a home
    tournament with only 1-2 categories) draws everything proportionally
    bigger instead of clumping at the top with empty space below."""

    scale: float
    banner_height: float
    banner_padding_x: float
    banner_gap_below: float
    pill_gap: float
    pill_padding_x: float
    pill_icon_area: float
    card_radius: float
    card_padding_x: float
    card_gap: float
    section_gap: float
    card_height: float
    time_matchup_gap: float
    icon_radius: float
    icon_text_gap: float
    banner_font: object
    pill_font: object
    time_font: object
    matchup_font: object
    score_font: object
    stamp_font: object


class BaseCardTemplate:
    """Shared rendering for TVO's card-based post templates: category
    banners, venue pill, time/matchup or score cards, adaptive scaling.

    Subclasses provide `profile` (canvas geometry) and `background()`, and
    implement `_draw_title()` - the one thing that genuinely differs between
    the feed post ("HEIMSPIEL", centered, fixed text) and the story post
    ("GAME WEEKEND - date", left-aligned, per-post text).
    """

    profile: layout.CanvasProfile

    def __init__(
        self,
        kind: Literal["announce", "results"],
        border_color: tuple[int, int, int, int] | None = DEFAULT_BORDER_COLOR,
        shadow_offset: float = DEFAULT_SHADOW_OFFSET,
        shadow_blur: float = DEFAULT_SHADOW_BLUR,
        shadow_color: tuple[int, int, int, int] | None = DEFAULT_SHADOW_COLOR,
        tvo_label_color: tuple[int, int, int, int] = TVO_RED_ON_DARK,
        time_matchup_gap: int = DEFAULT_TIME_MATCHUP_GAP,
        missing_venue_text: str = DEFAULT_MISSING_VENUE_TEXT,
        section_gap: float = SECTION_GAP,
    ) -> None:
        self.kind = kind
        self.border_color = border_color
        self.tvo_label_color = tvo_label_color
        self.shadow_offset = shadow_offset
        self.shadow_blur = shadow_blur
        self.shadow_color = shadow_color
        self.time_matchup_gap = time_matchup_gap
        self.missing_venue_text = missing_venue_text
        self.section_gap = section_gap

    @property
    def canvas_size(self) -> tuple[int, int]:
        return self.profile.canvas_size

    def background(self) -> Image.Image:
        raise NotImplementedError

    def _draw_title(
        self,
        draw: ImageDraw.ImageDraw,
        content_start_y: float,
        page_idx: int,
        page_count: int,
        title: str,
    ) -> None:
        raise NotImplementedError

    def _build_metrics(self, scale: float) -> Metrics:
        # Horizontal paddings/gaps use a damped scale so they don't eat into
        # the extra width that growing text needs at high scale.
        h_scale = 1 + (scale - 1) * HORIZONTAL_SCALE_DAMPING
        return Metrics(
            scale=scale,
            banner_height=BANNER_HEIGHT * scale,
            banner_padding_x=BANNER_PADDING_X * h_scale,
            banner_gap_below=BANNER_GAP_BELOW * scale,
            pill_gap=PILL_GAP_AFTER_BANNER * scale,
            pill_padding_x=PILL_PADDING_X * h_scale,
            pill_icon_area=PILL_ICON_AREA * h_scale,
            card_radius=CARD_RADIUS * scale,
            card_padding_x=CARD_PADDING_X * h_scale,
            card_gap=CARD_GAP * scale,
            section_gap=self.section_gap * scale,
            card_height=layout.CARD_HEIGHT[self.kind] * scale,
            time_matchup_gap=self.time_matchup_gap * h_scale,
            icon_radius=ICON_RADIUS * scale,
            icon_text_gap=ICON_TEXT_GAP * h_scale,
            banner_font=load_font(FONT_BOLD, round(22 * scale)),
            pill_font=load_font(FONT_REGULAR, round(19 * scale)),
            time_font=load_font(FONT_BOLD, round(26 * scale)),
            matchup_font=load_font(FONT_BOLD, round(26 * scale)),
            score_font=load_font(FONT_BOLD, round(30 * scale)),
            stamp_font=load_font(FONT_BOLD, round(22 * scale)),
        )

    def _fits_at_scale(
        self, draw: ImageDraw.ImageDraw, categorized_games: dict[str, list[TeamGame]], scale: float
    ) -> bool:
        """Whether every venue-pill text and matchup line would render in
        full (no ellipsis) at this scale. Mirrors the geometry the actual
        drawing methods use, so it must be kept in sync with them."""
        m = self._build_metrics(scale)

        for category, team_games in categorized_games.items():
            label = category.upper()
            banner_width = min(
                draw.textlength(label, font=m.banner_font) + 2 * m.banner_padding_x, CONTENT_WIDTH
            )

            if self.kind == "announce":
                pill_x = CONTENT_X + banner_width + m.pill_gap
                pill_available = CONTENT_X + CONTENT_WIDTH - pill_x
                date_str = format_date_range([tg.date for tg in team_games])
                venues: list[str] = []
                seen: set[str] = set()
                for tg in team_games:
                    if tg.game.venue and tg.game.venue not in seen:
                        seen.add(tg.game.venue)
                        venues.append(tg.game.venue)
                venue_str = " / ".join(venues) if venues else self.missing_venue_text
                pill_text_width = draw.textlength(f"{date_str}  ·  {venue_str}", font=m.pill_font)
                if pill_text_width + m.pill_icon_area + 2 * m.pill_padding_x > pill_available:
                    return False

            for tg in team_games:
                if self.kind == "results":
                    score_width = draw.textlength(tg.score_text() + "   ", font=m.score_font)
                    needed = draw.textlength(f"VS {tg.opponent.upper()}", font=m.matchup_font)
                    available = CONTENT_WIDTH - 2 * m.card_padding_x - score_width
                else:
                    time_str = tg.game.time or "TBD"
                    time_width = draw.textlength(time_str, font=m.time_font)
                    used = (
                        m.card_padding_x
                        + m.icon_radius * 2
                        + m.icon_text_gap
                        + time_width
                        + m.time_matchup_gap
                    )
                    opponent = tg.opponent.upper()
                    full_text = (
                        f"{TVO_LABEL} VS {opponent}" if tg.is_home else f"{opponent} VS {TVO_LABEL}"
                    )
                    needed = draw.textlength(full_text, font=m.matchup_font)
                    available = CONTENT_WIDTH - m.card_padding_x - used
                if needed > available:
                    return False

        return True

    def _resolve_scale(
        self, draw: ImageDraw.ImageDraw, categorized_games: dict[str, list[TeamGame]]
    ) -> float:
        scale = layout.compute_scale(categorized_games, self.kind, self.profile, self.section_gap)
        while scale > layout.MIN_SCALE and not self._fits_at_scale(draw, categorized_games, scale):
            scale = max(layout.MIN_SCALE, scale - SCALE_SEARCH_STEP)
        return scale

    def _resolve_content_start_y(self, content_height: float) -> float:
        """Vertically center the (possibly scaled-up) content block in the
        available zone, rather than always starting flush at the top."""
        available = self.profile.page_capacity()
        return self.profile.content_top + max(0.0, (available - content_height) / 2)

    def _fit_title_font(
        self, draw: ImageDraw.ImageDraw, text: str, max_width: float, max_height: float
    ):
        """Largest bold font size (within bounds) whose rendered width AND
        line height both still fit - width alone isn't enough: when the card
        block already fills most of the page, a width-only-fit title (huge,
        since these titles are short) would be tall enough to collide with
        the first badge. Falls back to the minimum size if even that doesn't
        fit max_height, rather than shrinking to nothing."""
        lo, hi = TITLE_MIN_FONT_SIZE, TITLE_MAX_FONT_SIZE
        best = load_font(FONT_BOLD, lo)
        while lo <= hi:
            mid = (lo + hi) // 2
            font = load_font(FONT_BOLD, mid)
            width_ok = draw.textlength(text, font=font) <= max_width
            ascent, descent = font.getmetrics()
            height_ok = (ascent + descent) <= max_height
            if width_ok and height_ok:
                best = font
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def _draw_adaptive_title(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        content_start_y: float,
        align: Literal["left", "center"],
    ) -> None:
        """Draw `text` as large as possible in the zone between the top
        boundary (below the logo) and content_start_y, without colliding -
        used for both "HEIMSPIEL" (centered) and "GAME WEEKEND - ..." (left)."""
        zone_height = content_start_y - HEADER_Y
        max_title_height = max(0.0, zone_height - 2 * MIN_TITLE_GAP)
        title_font = self._fit_title_font(draw, text, CONTENT_WIDTH, max_title_height)
        ascent, descent = title_font.getmetrics()
        title_height = ascent + descent

        gap = max(0.0, (zone_height - title_height) / 2)
        title_top_y = HEADER_Y + gap

        x, anchor = (CANVAS_CENTER_X, "ma") if align == "center" else (CONTENT_X, "la")
        draw.text((x, title_top_y), text, font=title_font, fill=TVO_RED, anchor=anchor)

    def render(
        self,
        image: Image.Image,
        categorized_games: dict[str, list[TeamGame]],
        page_idx: int,
        page_count: int,
        title: str,
    ) -> Image.Image:
        # RGBA so the card border/shadow can be drawn with real alpha
        # blending instead of an approximated solid color.
        image = image.convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")

        scale = self._resolve_scale(draw, categorized_games)
        m = self._build_metrics(scale)
        content_height = (
            layout.total_content_height(categorized_games, self.kind, self.section_gap) * scale
        )
        content_start_y = self._resolve_content_start_y(content_height)

        self._draw_title(draw, content_start_y, page_idx, page_count, title)

        y = content_start_y
        for category, team_games in categorized_games.items():
            y = self._draw_category_header(draw, category, team_games, y, m)
            for tg in team_games:
                y = self._draw_card(draw, image, tg, y, m)
            y += m.section_gap - m.card_gap

        return image

    def _draw_category_header(
        self,
        draw: ImageDraw.ImageDraw,
        category: str,
        team_games: list[TeamGame],
        y: float,
        m: Metrics,
    ) -> float:
        label = category.upper()
        text_width = draw.textlength(label, font=m.banner_font)
        banner_width = min(text_width + 2 * m.banner_padding_x, CONTENT_WIDTH)
        draw.rounded_rectangle(
            [CONTENT_X, y, CONTENT_X + banner_width, y + m.banner_height],
            radius=m.banner_height / 2,
            fill=TVO_RED,
        )
        draw.text(
            (CONTENT_X + m.banner_padding_x, y + m.banner_height / 2),
            fit_line(draw, label, m.banner_font, banner_width - 2 * m.banner_padding_x),
            font=m.banner_font,
            fill=BANNER_TEXT,
            anchor="lm",
        )

        if self.kind == "announce":
            pill_x = CONTENT_X + banner_width + m.pill_gap
            available = CONTENT_X + CONTENT_WIDTH - pill_x
            if available >= PILL_MIN_WIDTH:
                self._draw_venue_pill(draw, team_games, pill_x, y, available, m)

        return y + m.banner_height + m.banner_gap_below

    def _draw_venue_pill(
        self,
        draw: ImageDraw.ImageDraw,
        team_games: list[TeamGame],
        x: float,
        y: float,
        max_width: float,
        m: Metrics,
    ) -> None:
        date_str = format_date_range([tg.date for tg in team_games])
        venues: list[str] = []
        seen: set[str] = set()
        for tg in team_games:
            venue = tg.game.venue
            if venue and venue not in seen:
                seen.add(venue)
                venues.append(venue)
        venue_str = " / ".join(venues) if venues else self.missing_venue_text
        text = f"{date_str}  ·  {venue_str}"

        text_x = x + m.pill_icon_area + m.pill_padding_x
        available_text_width = max_width - m.pill_icon_area - 2 * m.pill_padding_x
        if available_text_width < 20:
            return
        fitted = fit_line(draw, text, m.pill_font, available_text_width)
        pill_width = min(
            m.pill_icon_area + m.pill_padding_x + draw.textlength(fitted, font=m.pill_font) + m.pill_padding_x,
            max_width,
        )

        draw.rounded_rectangle(
            [x, y, x + pill_width, y + m.banner_height],
            radius=m.banner_height / 2,
            fill=CARD_BG,
        )
        draw_pin_icon(
            draw,
            x + m.pill_padding_x + 5,
            y + m.banner_height * 0.22,
            m.banner_height * 0.56,
            CARD_TEXT,
            CARD_BG,
        )
        draw.text((text_x, y + m.banner_height / 2), fitted, font=m.pill_font, fill=CARD_TEXT, anchor="lm")

    def _draw_segments(
        self, draw: ImageDraw.ImageDraw, x: float, y: float, segments: list[tuple[str, tuple]], font
    ) -> None:
        cursor = x
        for text, color in segments:
            draw.text((cursor, y), text, font=font, fill=color, anchor="lm")
            cursor += draw.textlength(text, font=font)

    def _matchup_segments(
        self, draw: ImageDraw.ImageDraw, tg: TeamGame, font, max_width: float
    ) -> list[tuple[str, tuple]]:
        """Build colored (text, color) segments for 'TV OBERWIL VS GEGNER' (or
        the reverse), always showing the home team first, TV Oberwil in red.
        For an internal TVO-vs-TVO duel, the opponent side gets the same red
        highlight - it's also us, just a different category block."""
        opponent = tg.opponent.upper()
        opponent_color = self.tvo_label_color if tg.opponent_is_tvo else CARD_TEXT
        if tg.is_home:
            fixed = f"{TVO_LABEL} VS "
            fixed_width = draw.textlength(fixed, font=font)
            fitted_opp = fit_line(draw, opponent, font, max(max_width - fixed_width, 20))
            return [(TVO_LABEL, self.tvo_label_color), (" VS ", CARD_TEXT), (fitted_opp, opponent_color)]
        else:
            fixed = f" VS {TVO_LABEL}"
            fixed_width = draw.textlength(fixed, font=font)
            fitted_opp = fit_line(draw, opponent, font, max(max_width - fixed_width, 20))
            return [(fitted_opp, opponent_color), (" VS ", CARD_TEXT), (TVO_LABEL, self.tvo_label_color)]

    def _draw_soft_bottom_shadow(
        self, image: Image.Image, box: list[float], radius: float
    ) -> None:
        """A blurred glow hugging the card's bottom edge, drawn on a small
        padded tile and composited in - a real blur, not a hard offset copy,
        so it reads as a soft shadow rather than a second card underneath."""
        x0, y0, x1, y1 = box
        margin = int(self.shadow_blur * 2) + 4
        tile_w = int(x1 - x0) + 2 * margin
        tile_h = int(y1 - y0) + int(self.shadow_offset) + 2 * margin
        tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
        tile_draw = ImageDraw.Draw(tile, "RGBA")
        shadow_box = [
            margin,
            margin + self.shadow_offset,
            margin + (x1 - x0),
            margin + self.shadow_offset + (y1 - y0),
        ]
        tile_draw.rounded_rectangle(shadow_box, radius=radius, fill=self.shadow_color)
        if self.shadow_blur > 0:
            tile = tile.filter(ImageFilter.GaussianBlur(self.shadow_blur))
        image.paste(tile, (int(x0) - margin, int(y0) - margin), tile)

    def _draw_missing_venue_stamp(
        self, image: Image.Image, box: list[float], font
    ) -> None:
        """A rotated attention banner across a card whose game has no venue
        yet - deliberately loud (off-brand amber) so it can never be missed
        when scanning a post before publishing it.

        The tile is exactly card-sized and rotated WITHOUT expanding the
        canvas, so the diagonal band is clipped to the card itself - it can
        never bleed into the category badge above or the next card below."""
        x0, y0, x1, y1 = box
        card_w = int(x1 - x0)
        card_h = int(y1 - y0)

        tile = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        tile_draw = ImageDraw.Draw(tile, "RGBA")
        band_h = max(int(card_h * 0.5), 1)
        band_top = (card_h - band_h) // 2
        tile_draw.rectangle([0, band_top, card_w, band_top + band_h], fill=STAMP_BG)
        tile_draw.text(
            (card_w / 2, band_top + band_h / 2),
            self.missing_venue_text,
            font=font,
            fill=STAMP_TEXT,
            anchor="mm",
        )

        rotated = tile.rotate(STAMP_ANGLE, resample=Image.BICUBIC)  # same size, clipped to the card
        image.paste(rotated, (int(x0), int(y0)), rotated)

    def _draw_card(
        self,
        draw: ImageDraw.ImageDraw,
        image: Image.Image,
        tg: TeamGame,
        y: float,
        m: Metrics,
    ) -> float:
        height = m.card_height
        box = [CONTENT_X, y, CONTENT_X + CONTENT_WIDTH, y + height]

        if self.shadow_offset and self.shadow_color:
            self._draw_soft_bottom_shadow(image, box, m.card_radius)

        draw.rounded_rectangle(
            box,
            radius=m.card_radius,
            fill=CARD_BG,
            outline=self.border_color,
            width=1 if self.border_color else 0,
        )

        if self.kind == "results":
            score_text = tg.score_text()
            score_color = RESULT_COLORS[tg.result_kind()]
            draw.text(
                (CONTENT_X + m.card_padding_x, y + height / 2),
                score_text,
                font=m.score_font,
                fill=score_color,
                anchor="lm",
            )
            score_width = draw.textlength(score_text + "   ", font=m.score_font)
            opponent_text = f"VS {tg.opponent.upper()}"
            remaining_width = CONTENT_WIDTH - 2 * m.card_padding_x - score_width
            draw.text(
                (CONTENT_X + m.card_padding_x + score_width, y + height / 2),
                fit_line(draw, opponent_text, m.matchup_font, remaining_width),
                font=m.matchup_font,
                fill=CARD_TEXT,
                anchor="lm",
            )
        else:
            time_str = tg.game.time or "TBD"
            icon_cx = CONTENT_X + m.card_padding_x + m.icon_radius
            draw_clock_icon(draw, icon_cx, y + height / 2, m.icon_radius, CARD_TEXT, width=2)

            time_x = icon_cx + m.icon_radius + m.icon_text_gap
            draw.text((time_x, y + height / 2), time_str, font=m.time_font, fill=CARD_TEXT, anchor="lm")

            matchup_x = time_x + draw.textlength(time_str, font=m.time_font) + m.time_matchup_gap
            remaining_width = CONTENT_X + CONTENT_WIDTH - m.card_padding_x - matchup_x
            segments = self._matchup_segments(draw, tg, m.matchup_font, remaining_width)
            self._draw_segments(draw, matchup_x, y + height / 2, segments, m.matchup_font)

            if not tg.game.venue:
                self._draw_missing_venue_stamp(image, box, m.stamp_font)

        return y + height + m.card_gap

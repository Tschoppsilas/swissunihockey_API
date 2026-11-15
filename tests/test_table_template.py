import dataclasses

import pytest
from PIL import Image, ImageDraw

from tvo_social import layout
from tvo_social.models import LeagueTable, TableEntry
from tvo_social.tables import TableRow
from tvo_social.templates.base_card import CARD_TEXT, TVO_RED_ON_DARK
from tvo_social.templates.table_card import MIN_TABLE_SCALE, TableTemplate


def entry(place, name="UHC Team", club=1, games=8, wo=0, do=0, gf=30, ga=25, team_id=None):
    return TableEntry(
        place=place, team_id=team_id or 1000 + place, club_id=club, name=name, games=games, wins=4,
        wins_overtime=wo, ties=1, defeats_overtime=do, defeats=3, goals_for=gf, goals_against=ga, points=13,
    )


def rows_of(count, tvo=(), long_name=None, **kwargs):
    rows = []
    for place in range(1, count + 1):
        is_tvo = place in tvo
        name = "TV Oberwil" if is_tvo else (long_name if long_name and place == 2 else f"UHC Team {place}")
        rows.append(TableRow(entry(place, name, **kwargs), name, is_tvo))
    return rows


def render(tmp_path, rows, overtime=False, subtitle="Junioren D Regional", stand="Stand: 15.11.2026"):
    template = TableTemplate()
    path = tmp_path / "t.png"
    scale = template.render_to(path, rows, overtime, subtitle, stand)
    return path, scale, template


def test_image_has_the_feed_size(tmp_path):
    path, _, _ = render(tmp_path, rows_of(10, tvo={3}))
    with Image.open(path) as image:
        assert image.size == layout.FEED_PROFILE.canvas_size


@pytest.mark.parametrize("count", [1, 2, 4, 8, 10, 12, 14, 16])
def test_every_row_count_fits_the_page(tmp_path, count):
    _, scale, _ = render(tmp_path, rows_of(count))
    assert MIN_TABLE_SCALE < scale <= 1.4
    if count >= 16:
        assert scale < 0.75  # dense but still rendered


def test_fewer_rows_are_scaled_up_but_capped(tmp_path):
    _, few, _ = render(tmp_path, rows_of(4))
    _, many, _ = render(tmp_path, rows_of(12))
    assert few == pytest.approx(1.4) and many < few


def test_overtime_columns_appear_only_on_request():
    plain = [key for key, _, _ in TableTemplate._columns(False)]
    with_ot = [key for key, _, _ in TableTemplate._columns(True)]
    assert plain == ["rank", "team", "games", "wins", "ties", "defeats", "goals", "diff", "points"]
    assert with_ot == [
        "rank", "team", "games", "wins", "wins_overtime", "ties", "defeats_overtime", "defeats", "goals", "diff", "points",
    ]
    headers = [h for _, h, _ in TableTemplate._columns(True)]
    assert headers == ["Rg", "Team", "Sp", "S", "SnV", "U", "NnV", "N", "Tore", "Diff", "Pkt"]


def test_cells_show_goal_difference_with_sign_and_the_full_uppercase_name():
    template = TableTemplate()
    row = TableRow(entry(1, "Unihockey Langenthal Aarwangen", gf=31, ga=20), "Unihockey Langenthal Aarwangen", False)
    assert template._cell(row, "diff") == "+11"
    assert template._cell(TableRow(entry(1, gf=20, ga=31), "x", False), "diff") == "-11"
    assert template._cell(TableRow(entry(1, gf=20, ga=20), "x", False), "diff") == "0"
    assert template._cell(row, "goals") == "31:20"
    assert template._cell(row, "team") == "UNIHOCKEY LANGENTHAL AARWANGEN"  # never shortened


def test_long_names_are_never_cut_off_the_scale_shrinks_instead(tmp_path):
    very_long = "HC Rychenberg Winterthur Oberwinterthur United III Extra"
    rows = rows_of(10, long_name=very_long)
    path, scale, template = render(tmp_path, rows, overtime=True)
    img = Image.new("RGBA", (1080, 1350))
    draw = ImageDraw.Draw(img)
    layout_info = template._layout(draw, rows, template._columns(True), scale)
    assert layout_info is not None
    name_width = draw.textlength(very_long.upper(), font=layout_info["row_font"])
    assert name_width <= layout_info["widths"]["team"] + 0.5
    _, normal_scale, _ = render(tmp_path, rows_of(10), overtime=True)
    assert scale < normal_scale  # the long name forced a smaller factor for the whole image


def test_a_name_that_cannot_fit_even_when_tiny_raises_instead_of_truncating(tmp_path):
    with pytest.raises(ValueError):
        render(tmp_path, rows_of(10, long_name="X" * 400))


def test_tvo_rows_are_red_everywhere_and_all_others_white(tmp_path, monkeypatch):
    drawn = []
    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, fill=None, *args, **kwargs):
        drawn.append((text, fill))
        return original(self, xy, text, fill, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    render(tmp_path, rows_of(6, tvo={2, 5}))

    by_text = {}
    for text, fill in drawn:
        by_text.setdefault(text, set()).add(fill)
    assert by_text["TV OBERWIL"] == {TVO_RED_ON_DARK}
    assert by_text["UHC TEAM 1"] == {CARD_TEXT} and by_text["UHC TEAM 3"] == {CARD_TEXT}
    # Rank cell "2" and "5" belong to the TVO rows only (their rank text is red too)
    assert TVO_RED_ON_DARK in by_text["2"] and TVO_RED_ON_DARK in by_text["5"]
    assert by_text["TABELLE"] and "Junioren D Regional" in by_text and "Stand: 15.11.2026" in by_text


def test_the_title_block_is_drawn_once_with_league_and_stand(tmp_path, monkeypatch):
    drawn = []
    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, *args, **kwargs):
        drawn.append(text)
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    render(tmp_path, rows_of(5), stand="Stand: 15.11.2026 · Winterpause")
    assert drawn.count("TABELLE") == 1
    assert "Stand: 15.11.2026 · Winterpause" in drawn


def test_a_very_long_league_text_is_wrapped_or_shrunk_never_cut(tmp_path):
    template = TableTemplate()
    img = Image.new("RGBA", (1080, 1350))
    draw = ImageDraw.Draw(img)
    from tvo_social.templates.base_card import FONT_BOLD

    text = "Herren Aktive Grossfeld Nationalliga B Qualifikation Gruppe Nordwestschweiz"
    font, lines = template._fit_lines(draw, text, FONT_BOLD, 960, 40, 28, 18)
    assert " ".join(lines) == text
    assert all(draw.textlength(line, font=font) <= 960 for line in lines)
    assert len(lines) == 2  # does not fit on one line at 28 px, so it is wrapped

    short_font, short_lines = template._fit_lines(draw, "Junioren D Regional", FONT_BOLD, 960, 40, 28, 18)
    assert short_lines == ["Junioren D Regional"]

    path, scale, _ = render(tmp_path, rows_of(10), subtitle=text)
    assert path.is_file() and scale > MIN_TABLE_SCALE


def test_no_rows_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        render(tmp_path, [])


def test_two_runs_with_the_same_data_are_pixel_identical(tmp_path):
    first, _, _ = render(tmp_path, rows_of(8, tvo={3}))
    data = first.read_bytes()
    second, _, _ = render(tmp_path, rows_of(8, tvo={3}))
    assert second.read_bytes() == data

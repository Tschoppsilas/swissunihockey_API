from datetime import date

from PIL import Image, ImageChops

from tvo_social import layout
from tvo_social.models import Game, TeamGame
from tvo_social.render import render_page
from tvo_social.templates.instagram_v1 import InstagramV1Template


def result_game(id, opponent, goals, is_home=True):
    game = Game(
        id=id, date=date(2026, 1, 10), time="09:00", home_team="TV Oberwil BL", away_team=opponent,
        home_team_id=1, away_team_id=2, venue="Thomasgarten (Oberwil BL)", league_text="E", category_text="E",
        played=True, goals_home=goals[0], goals_away=goals[1],
    )
    return TeamGame(
        game=game, category="E Weiss", opponent=opponent, our_goals=goals[0], opp_goals=goals[1], is_home=is_home
    )


PAGE = {
    "E Weiss": [
        result_game(1, "UHC Frenkendorf-Füllinsdorf", (6, 11)),
        result_game(2, "Griffins Muttenz-Pratteln", (14, 8), is_home=False),
        result_game(3, "UHC Basel United I", (2, 2)),
    ]
}


def render(tmp_path, name, **kwargs):
    template = InstagramV1Template(kind="results", **kwargs)
    return render_page(template, PAGE, 0, 1, "RESULTATE - 10.01.", tmp_path / name)


def test_feed_results_page_is_a_feed_sized_image(tmp_path):
    with Image.open(render(tmp_path, "a.png")) as image:
        assert image.size == layout.FEED_PROFILE.canvas_size


def test_title_variants_render_differently(tmp_path):
    with Image.open(render(tmp_path, "a.png")) as a, Image.open(
        render(tmp_path, "b.png", results_title="HEIMSPIEL RESULTATE")
    ) as b:
        assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is not None


def test_long_opponent_names_with_two_digit_scores_do_not_crash(tmp_path):
    long_page = {"E Weiss": [result_game(9, "TV Flüh-Hofstetten-Rodersdorf-Biel-Benken", (17, 10))]}
    render_page(InstagramV1Template(kind="results"), long_page, 0, 1, "x", tmp_path / "long.png")
    assert (tmp_path / "long.png").is_file()

import pytest

from tvo_social.models import Game

BASE_RAW_GAME = {
    "id": 1,
    "date": "20.12.2026",
    "time": "09:00",
    "hometeamname": "TV Oberwil BL",
    "awayteamname": "Gegner",
    "hometeamid": 1,
    "awayteamid": 2,
}


def make_raw_game(gym: dict | None) -> dict:
    return {**BASE_RAW_GAME, "gym": gym}


def test_venue_parses_normally_when_assigned():
    game = Game.from_api(make_raw_game({"content": "Thomasgarten (Oberwil BL)", "id": 123}))
    assert game.venue == "Thomasgarten (Oberwil BL)"


@pytest.mark.parametrize(
    "gym",
    [
        {"content": "-", "id": -1},  # the actual placeholder observed from the live API
        {"content": "", "id": -1},
        {"content": "  ", "id": -1},
        {"content": "TBD", "id": -1},
        None,
        {},
    ],
)
def test_venue_normalizes_all_missing_placeholders_to_empty_string(gym):
    game = Game.from_api(make_raw_game(gym))
    assert game.venue == ""
    assert not game.venue  # this is the exact check the app relies on everywhere

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import click


def _ensure_utf8_console() -> None:
    """Windows consoles default to a legacy codepage (cp1252, sometimes
    cp850/437) that can't encode a lot of Unicode - reconfigure stdout/stderr
    to UTF-8 so nothing we print can crash the process. Belt-and-suspenders:
    every literal string we print is also kept ASCII-only (see below), so
    output still works correctly even if reconfigure itself isn't available
    (e.g. output redirected to something that doesn't support it)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

from . import layout
from .api_client import ApiClient
from .config import load_config, load_team_labels
from .grouping import (
    format_weekend_title,
    group_by_category,
    group_games_by_week,
    half_season_end,
    last_completed_week,
    paginate_by_category,
    week_bounds,
)
from .models import Game, Team, TeamGame
from .render import render_batches
from .teams import get_teams, refresh_team_cache
from .templates.instagram_v1 import InstagramV1Template
from .templates.story import StoryTemplate

GAMES_FETCH_LIMIT = 200


def _fetch_team_games(
    client: ApiClient, teams: list[Team], status: str, order: str
) -> list[TeamGame]:
    """One TeamGame per (team, game) pair - fetched from each team's own
    fixture list, independently.

    Deliberately NOT deduplicated across teams: when two TVO teams play each
    other (e.g. Junioren D Blau vs. D Weiss), the same underlying game must
    show up twice - once as D Blau's fixture, once as D Weiss's - since each
    is its own category block with its own full schedule. Deduping by game
    id (as this used to do) silently dropped the game from whichever team
    was processed second.
    """
    labels = load_team_labels()
    category_by_team_id = {t.id: labels.get(t.id, t.category) for t in teams}
    tvo_team_ids = set(category_by_team_id)

    team_games: list[TeamGame] = []
    for team in teams:
        raw_games = client.get_team_games(
            team.id, status=status, limit=GAMES_FETCH_LIMIT, order=order
        )
        for raw in raw_games:
            game = Game.from_api(raw)
            if game.canceled:
                continue
            is_home = team.id == game.home_team_id
            opponent_id = game.away_team_id if is_home else game.home_team_id
            raw_opponent_name = game.away_team if is_home else game.home_team
            opponent_is_tvo = opponent_id in tvo_team_ids
            # For an internal TVO-vs-TVO duel, show the other side's mapped
            # display name too (e.g. "Junioren E Rot"), not its raw API team
            # name ("TV Oberwil BL III") - the same mapping already used for
            # category badges, just not applied to the opponent before.
            opponent = category_by_team_id[opponent_id] if opponent_is_tvo else raw_opponent_name
            team_games.append(
                TeamGame(
                    game=game,
                    category=category_by_team_id.get(
                        team.id, game.category_text or game.league_text
                    ),
                    opponent=opponent,
                    our_goals=game.goals_home if is_home else game.goals_away,
                    opp_goals=game.goals_away if is_home else game.goals_home,
                    is_home=is_home,
                    opponent_is_tvo=opponent_is_tvo,
                )
            )
    return team_games


def _week_title(kind: str, week_key_str: str, week_games: list[TeamGame]) -> str:
    if kind == "announce":
        # Games are always on a weekend, so show the actual date(s) rather
        # than a calendar week number - see grouping.format_weekend_title.
        return format_weekend_title(week_games, "GAME WEEKEND")
    monday, sunday = week_bounds(week_games[0].date)
    iso_week = week_key_str.split("-W")[1]
    return f"Resultate KW{iso_week} ({monday:%d.%m.}-{sunday:%d.%m.})"


def _generate_weeks(
    kind: str,
    grouped_weeks: dict[str, list[TeamGame]],
    out_root: Path,
    dry_run: bool,
    template_cls: type = InstagramV1Template,
    profile: layout.CanvasProfile = layout.FEED_PROFILE,
    template_kwargs: dict | None = None,
) -> None:
    template_kwargs = template_kwargs or {}
    for week_key_str, week_games in grouped_weeks.items():
        categorized = group_by_category(week_games)
        pages = paginate_by_category(categorized, kind, profile)
        title = _week_title(kind, week_key_str, week_games)
        click.echo(f"{week_key_str}: {len(week_games)} Spiele -> {len(pages)} Bild(er)")
        if dry_run:
            continue
        template = template_cls(kind=kind, **template_kwargs)
        paths = render_batches(template, pages, out_root / week_key_str, "post", title)
        for p in paths:
            click.echo(f"  geschrieben: {p}")


def _report_missing_venues(team_games: list[TeamGame]) -> None:
    """Print every game whose venue isn't assigned yet, so it can never slip
    through unnoticed even though the image itself already stamps it - grep
    for the 'FEHLENDE HALLE:' prefix to pull this into an outer script."""
    missing = [tg for tg in team_games if not tg.game.venue]
    if not missing:
        click.echo("Keine fehlenden Hallen-Zuweisungen.")
        return
    click.echo(f"\n[WARNUNG] {len(missing)} Spiel(e) ohne Hallen-Zuweisung:")
    for tg in sorted(missing, key=lambda tg: (tg.date, tg.game.time or "")):
        time_str = tg.game.time or "?"
        click.echo(f"  FEHLENDE HALLE: {tg.category} | {tg.date:%d.%m.%Y} {time_str} | vs {tg.opponent}")


@click.group()
def main() -> None:
    """TV Oberwil Instagram post preparation tool."""
    _ensure_utf8_console()


@main.command()
@click.option("--output-dir", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False, help="Only print what would be generated.")
def announce(output_dir: Path | None, dry_run: bool) -> None:
    """Generate one separate post (per week) for every week until the next half-season cutoff."""
    cfg = load_config()
    client = ApiClient(cfg.api_base)
    teams = get_teams(client, cfg)

    today = date.today()
    end_date = half_season_end(today)
    click.echo(f"Zeitraum: {today:%d.%m.%Y} - {end_date:%d.%m.%Y}")

    team_games = _fetch_team_games(client, teams, status="planned", order="ASC")
    team_games = [tg for tg in team_games if today <= tg.date <= end_date]
    # Feed post = home tournament only; away games go into the (future)
    # story template instead, see config.yaml's home_venue.
    team_games = [tg for tg in team_games if tg.game.venue == cfg.home_venue]

    if not team_games:
        click.echo("Keine anstehenden Heimspiele im Zeitraum gefunden.")
        return

    grouped_weeks = group_games_by_week(team_games)
    out_root = (output_dir or cfg.output_dir) / "announcements"
    _generate_weeks(
        "announce",
        grouped_weeks,
        out_root,
        dry_run,
        template_kwargs={"missing_venue_text": cfg.missing_venue_text},
    )
    _report_missing_venues(team_games)


@main.command()
@click.option("--output-dir", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False, help="Only print what would be generated.")
def story(output_dir: Path | None, dry_run: bool) -> None:
    """Generate the story post (all weekend games, every category, no venue
    filter) for every week until the next half-season cutoff."""
    cfg = load_config()
    client = ApiClient(cfg.api_base)
    teams = get_teams(client, cfg)

    today = date.today()
    end_date = half_season_end(today)
    click.echo(f"Zeitraum: {today:%d.%m.%Y} - {end_date:%d.%m.%Y}")

    team_games = _fetch_team_games(client, teams, status="planned", order="ASC")
    team_games = [tg for tg in team_games if today <= tg.date <= end_date]

    if not team_games:
        click.echo("Keine anstehenden Spiele im Zeitraum gefunden.")
        return

    grouped_weeks = group_games_by_week(team_games)
    out_root = (output_dir or cfg.output_dir) / "story"
    _generate_weeks(
        "announce",
        grouped_weeks,
        out_root,
        dry_run,
        template_cls=StoryTemplate,
        profile=layout.STORY_PROFILE,
        template_kwargs={"missing_venue_text": cfg.missing_venue_text},
    )
    _report_missing_venues(team_games)


@main.command()
@click.option("--week-start", type=click.DateTime(formats=["%Y-%m-%d"]), default=None)
@click.option("--week-end", type=click.DateTime(formats=["%Y-%m-%d"]), default=None)
@click.option("--output-dir", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
def results(
    week_start: datetime | None,
    week_end: datetime | None,
    output_dir: Path | None,
    dry_run: bool,
) -> None:
    """Generate the results post for one week (default: last completed Mon-Sun week)."""
    if (week_start is None) != (week_end is None):
        raise click.UsageError("--week-start und --week-end müssen zusammen angegeben werden.")

    cfg = load_config()
    client = ApiClient(cfg.api_base)
    teams = get_teams(client, cfg)

    if week_start is not None and week_end is not None:
        start_date, end_date = week_start.date(), week_end.date()
    else:
        start_date, end_date = last_completed_week(date.today())

    click.echo(f"Zeitraum: {start_date:%d.%m.%Y} - {end_date:%d.%m.%Y}")

    team_games = _fetch_team_games(client, teams, status="played", order="DESC")
    team_games = [tg for tg in team_games if start_date <= tg.date <= end_date]

    if not team_games:
        click.echo("Keine Resultate im Zeitraum gefunden.")
        return

    grouped_weeks = group_games_by_week(team_games)
    out_root = (output_dir or cfg.output_dir) / "results"
    _generate_weeks("results", grouped_weeks, out_root, dry_run)


@main.command(name="refresh-teams")
def refresh_teams() -> None:
    """Force-refetch the club's team list and overwrite the local cache."""
    cfg = load_config()
    client = ApiClient(cfg.api_base)
    teams = refresh_team_cache(client, cfg)
    click.echo(f"{len(teams)} Teams gefunden:")
    for team in teams:
        click.echo(f"  [{team.id}] {team.name} - {team.category}")


if __name__ == "__main__":
    main()

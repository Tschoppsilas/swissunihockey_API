from pathlib import Path

from tvo_social.config import Config, load_config


def test_default_is_no_exclusion(tmp_path):
    assert load_config(tmp_path / "missing.yaml").tables_exclude_categories == ()
    path = tmp_path / "c.yaml"
    path.write_text("club_id: 696\n", encoding="utf-8")
    assert load_config(path).tables_exclude_categories == ()
    assert Config().tables_exclude_categories == ()


def test_exclusion_list_is_read_from_the_tables_section(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text('tables:\n  exclude_categories:\n    - "Junioren E"\n    - Herren\n', encoding="utf-8")
    assert load_config(path).tables_exclude_categories == ("Junioren E", "Herren")


def test_an_empty_or_missing_list_means_everything_is_on(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("tables:\n  exclude_categories: []\n", encoding="utf-8")
    assert load_config(path).tables_exclude_categories == ()
    path.write_text("tables:\n", encoding="utf-8")
    assert load_config(path).tables_exclude_categories == ()


def test_the_shipped_config_excludes_the_junioren_e():
    repo_config = Path(__file__).resolve().parent.parent / "config.yaml"
    assert load_config(repo_config).tables_exclude_categories == ("Junioren E",)

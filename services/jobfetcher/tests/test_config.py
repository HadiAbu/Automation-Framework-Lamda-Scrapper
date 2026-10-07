import json

import pytest

from jobfetcher.config import load_config


def _write(tmp_path, payload):
    path = tmp_path / "boards.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_default_config_lists_the_five_starter_boards():
    config = load_config()
    assert [(b.type, b.name) for b in config.boards] == [
        ("greenhouse", "stripe"),
        ("greenhouse", "figma"),
        ("greenhouse", "cloudflare"),
        ("lever", "spotify"),
        ("lever", "palantir"),
    ]
    assert "python" in config.keywords


def test_keywords_are_lowercased(tmp_path):
    path = _write(
        tmp_path,
        {"boards": [{"type": "lever", "name": "x"}], "keywords": ["QA", "SDET"]},
    )
    assert load_config(path).keywords == ("qa", "sdet")


def test_keywords_are_optional(tmp_path):
    path = _write(tmp_path, {"boards": [{"type": "lever", "name": "x"}]})
    assert load_config(path).keywords == ()


def test_unknown_board_type_is_rejected(tmp_path):
    path = _write(tmp_path, {"boards": [{"type": "nope", "name": "x"}]})
    with pytest.raises(ValueError, match="unknown board type 'nope'"):
        load_config(path)


def test_empty_board_list_is_rejected(tmp_path):
    path = _write(tmp_path, {"boards": []})
    with pytest.raises(ValueError, match="no boards"):
        load_config(path)

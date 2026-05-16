"""Test code parsing helper used by /watch /unwatch /ai."""
import pytest

from tg_bot.handlers.watchlist import parse_code


@pytest.mark.parametrize("text,expected", [
    ("/watch 600519", "600519"),
    ("/watch  600519  ", "600519"),
    ("/watch@QuantDingerBot 600519", "600519"),
    ("/watch 000001", "000001"),
])
def test_parse_code_ok(text, expected):
    assert parse_code(text) == expected


@pytest.mark.parametrize("text", [
    "/watch",
    "/watch abc",
    "/watch 1234",          # too short
    "/watch 1234567",       # too long
    "/watch 60051a",
])
def test_parse_code_invalid(text):
    with pytest.raises(ValueError):
        parse_code(text)

"""Test banner: backend JSON → TG HTML message."""
from tg_bot.services.banner import build_banner


def test_banner_contains_core_fields(fake_analysis_json, fake_symbol_meta):
    html = build_banner(fake_analysis_json, name=fake_symbol_meta["name"],
                        telegraph_url="https://telegra.ph/600519-05-16")
    assert "中國中車" in html
    assert "601766" in html
    assert "BUY" in html
    assert "78" in html              # confidence
    assert "6.85" in html             # entry
    assert "6.52" in html             # stop loss
    assert "7.43" in html             # take profit
    assert "30" in html               # position size
    assert "https://telegra.ph/600519-05-16" in html


def test_banner_under_4096(fake_analysis_json):
    html = build_banner(fake_analysis_json, name="X",
                        telegraph_url="https://telegra.ph/x")
    assert len(html) < 4096


def test_banner_escapes_html_in_dynamic_content():
    """LLM might output strings with <, >, & — must be escaped."""
    payload = {
        "decision": "BUY", "confidence": 50,
        "summary": "Net <profit> grew & price > expected",
        "entry_price": 1.0, "stop_loss": 0.9, "take_profit": 1.2,
        "position_size_pct": 10, "timeframe": "medium",
        "symbol": "000001", "model": "x",
    }
    html = build_banner(payload, name="A&B <Co>", telegraph_url="https://telegra.ph/x")
    # No raw < > & in dynamic positions
    assert "<profit>" not in html
    assert "&lt;profit&gt;" in html
    assert "&amp;" in html
    assert "A&amp;B &lt;Co&gt;" in html


def test_summary_truncated_if_too_long():
    payload = {
        "decision": "BUY", "confidence": 50,
        "summary": "あ" * 1000,
        "entry_price": 1.0, "stop_loss": 0.9, "take_profit": 1.2,
        "position_size_pct": 10, "timeframe": "medium",
        "symbol": "000001", "model": "x",
    }
    html = build_banner(payload, name="X", telegraph_url="https://telegra.ph/x")
    assert "..." in html
    assert len(html) < 4096


def test_decision_emoji():
    for decision, emoji in (("BUY", "🟢"), ("SELL", "🔴"), ("HOLD", "🟡")):
        payload = {"decision": decision, "confidence": 50, "summary": "",
                   "entry_price": 1.0, "stop_loss": 0.9, "take_profit": 1.2,
                   "position_size_pct": 10, "timeframe": "medium",
                   "symbol": "000001", "model": "x"}
        html = build_banner(payload, name="X", telegraph_url="https://telegra.ph/x")
        assert emoji in html

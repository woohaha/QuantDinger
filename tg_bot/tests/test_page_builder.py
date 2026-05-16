"""Test page_builder: backend JSON → Telegraph Node tree."""
import json

from tg_bot.services.page_builder import build_page_title, build_page_content


def test_title_format(fake_analysis_json, fake_symbol_meta):
    title = build_page_title(fake_analysis_json, name=fake_symbol_meta["name"])
    assert "中國中車" in title
    assert "601766" in title
    assert "BUY" in title
    # Must be <= 256 chars (Telegraph limit)
    assert len(title) <= 256


def test_title_truncates_long_name():
    payload = {"decision": "BUY", "symbol": "601766"}
    title = build_page_title(payload, name="A" * 500)
    assert len(title) <= 256


def test_content_is_list_of_nodes(fake_analysis_json, fake_symbol_meta):
    nodes = build_page_content(fake_analysis_json, name=fake_symbol_meta["name"])
    assert isinstance(nodes, list)
    assert len(nodes) > 0
    # All nodes must be either str or dict with "tag"
    for n in nodes:
        assert isinstance(n, (str, dict))
        if isinstance(n, dict):
            assert "tag" in n


def test_content_includes_all_sections(fake_analysis_json, fake_symbol_meta):
    nodes = build_page_content(fake_analysis_json, name=fake_symbol_meta["name"])
    serialized = json.dumps(nodes, ensure_ascii=False)
    # All required headings present
    for heading in ("決策摘要", "技術分析", "基本面", "市場情緒",
                    "多周期趨勢", "客觀評分", "關鍵理由", "主要風險"):
        assert heading in serialized, f"missing heading: {heading}"
    # Key values present
    assert "BUY" in serialized
    assert "78" in serialized               # confidence
    assert "6.85" in serialized              # entry
    assert "MACD" in serialized              # key reason


def test_uses_only_allowed_tags(fake_analysis_json):
    """Telegraph supports a fixed tag list. We use a safe subset."""
    allowed = {"p", "h3", "h4", "ul", "ol", "li", "hr", "blockquote",
               "b", "i", "em", "strong", "a", "br"}
    nodes = build_page_content(fake_analysis_json, name="X")

    def walk(node):
        if isinstance(node, dict):
            assert node["tag"] in allowed, f"disallowed tag: {node['tag']}"
            for child in node.get("children", []):
                walk(child)

    for n in nodes:
        walk(n)


def test_serialized_under_64kb(fake_analysis_json):
    nodes = build_page_content(fake_analysis_json, name="X")
    serialized = json.dumps(nodes, ensure_ascii=False).encode("utf-8")
    assert len(serialized) < 64 * 1024


def test_missing_optional_fields(fake_analysis_json):
    # Drop trend_outlook + risks; should not crash
    payload = dict(fake_analysis_json)
    payload.pop("trend_outlook", None)
    payload["risks"] = []
    nodes = build_page_content(payload, name="X")
    serialized = json.dumps(nodes, ensure_ascii=False)
    # Should still have headings that don't depend on those
    assert "決策摘要" in serialized


def test_history_section_omitted_when_empty(fake_analysis_json):
    nodes = build_page_content(fake_analysis_json, name="X", historical_patterns=[])
    serialized = json.dumps(nodes, ensure_ascii=False)
    assert "歷史類似模式" not in serialized


def test_history_section_rendered_when_present(fake_analysis_json):
    patterns = [
        {"date": "2026-04-10", "decision": "BUY", "price": 6.45,
         "was_correct": True, "actual_return_pct": 5.2},
    ]
    nodes = build_page_content(fake_analysis_json, name="X", historical_patterns=patterns)
    serialized = json.dumps(nodes, ensure_ascii=False)
    assert "歷史類似模式" in serialized
    assert "6.45" in serialized

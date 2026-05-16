"""Convert backend /analyze JSON to Telegraph Node tree.

Telegraph Node format:
  - str: text content
  - dict: { "tag": "p" | "h3" | "ul" | ..., "attrs": {...}?, "children": [Node]? }

Limits:
  - title  <= 256 chars
  - content <= 64 KB serialized
  - allowed tags: a, aside, b, blockquote, br, code, em, figcaption, figure, h3, h4,
    hr, i, iframe, img, li, ol, p, pre, s, strong, u, ul, video
  - We use only: h3, p, hr, ul, ol, li, b, i (no images / no figures)
"""
from datetime import datetime
from typing import Any, Iterable

Node = dict | str

_DECISION_EMOJI = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}
_TREND_LABEL = {"BUY": "看多", "SELL": "看空", "HOLD": "震盪/中性"}
_STRENGTH_LABEL = {"strong": "強", "moderate": "中", "mild": "弱", "neutral": "中性"}


def _h3(text: str) -> Node:
    return {"tag": "h3", "children": [text]}


def _p(*children: Iterable[Node]) -> Node:
    return {"tag": "p", "children": list(children)}


def _hr() -> Node:
    return {"tag": "hr"}


def _ul(items: list[str]) -> Node:
    return {"tag": "ul", "children": [{"tag": "li", "children": [item]} for item in items]}


def _ol(items: list[str]) -> Node:
    return {"tag": "ol", "children": [{"tag": "li", "children": [item]} for item in items]}


def _b(text: str) -> Node:
    return {"tag": "b", "children": [text]}


def _pct(price: float, base: float) -> str:
    if not base:
        return ""
    delta = (price - base) / base * 100
    sign = "+" if delta >= 0 else ""
    return f"({sign}{delta:.1f}%)"


def build_page_title(payload: dict, name: str | None = None) -> str:
    """e.g. "中國中車 (601766) - BUY - 2026-05-16 14:32" """
    code = str(payload.get("symbol") or "")
    decision = str(payload.get("decision") or "HOLD").upper()
    label = f"{name} ({code})" if name else code
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"{label} - {decision} - {ts}"
    return title[:256]


def _build_decision_section(payload: dict) -> list[Node]:
    decision = str(payload.get("decision") or "HOLD").upper()
    emoji = _DECISION_EMOJI.get(decision, "⚪")
    confidence = payload.get("confidence", 0)
    pos = payload.get("position_size_pct", 0)
    tf = payload.get("timeframe", "")
    entry = payload.get("entry_price", 0) or 0
    sl = payload.get("stop_loss", 0) or 0
    tp = payload.get("take_profit", 0) or 0

    tf_label = {"short": "短期", "medium": "中期", "long": "長期"}.get(tf, tf)

    return [
        _h3("📊 決策摘要"),
        _p(_b(f"{emoji} {decision}"), f" · 信心 {confidence}% · 倉位 {pos}% · {tf_label}"),
        _p(f"入場 ¥{entry}  /  止損 ¥{sl} {_pct(sl, entry)}  /  止盈 ¥{tp} {_pct(tp, entry)}"),
        _p(_b("摘要："), str(payload.get("summary") or "")),
    ]


def _build_analysis_section(payload: dict) -> list[Node]:
    a = payload.get("analysis") or {}
    out: list[Node] = []
    for heading, key in (("📈 技術分析", "technical"), ("💼 基本面", "fundamental"),
                         ("📰 市場情緒", "sentiment")):
        text = str(a.get(key) or "").strip()
        if not text:
            continue
        out.append(_h3(heading))
        # Split paragraphs by double newline if present
        for para in text.split("\n\n"):
            para = para.strip()
            if para:
                out.append(_p(para))
    return out


def _build_trend_section(payload: dict) -> list[Node]:
    outlook = payload.get("trend_outlook") or {}
    if not outlook:
        return []
    rows = []
    for key, label in (("next_24h", "~24h"), ("next_3d", "~3d"),
                       ("next_1w", "~1w"), ("next_1m", "~1m")):
        item = outlook.get(key) or {}
        trend = _TREND_LABEL.get(str(item.get("trend") or "HOLD").upper(), "—")
        strength = _STRENGTH_LABEL.get(str(item.get("strength") or "neutral"), "—")
        rows.append(f"{label}：{trend}（{strength}）")
    return [_h3("🕐 多周期趨勢"), _ul(rows)]


def _build_score_section(payload: dict) -> list[Node]:
    obj = payload.get("objective_score") or {}
    if not obj:
        return []
    overall = obj.get("overall_score", 0)
    overall_label = (
        "強利多" if overall >= 70 else "中等利多" if overall >= 20
        else "強利空" if overall <= -70 else "中等利空" if overall <= -20
        else "中性"
    )
    items = [
        f"技術面：{obj.get('technical_score', 0)}/100",
        f"基本面：{obj.get('fundamental_score', 0)}/100",
        f"情緒面：{obj.get('sentiment_score', 0)}/100",
        f"宏觀面：{obj.get('macro_score', 0)}/100",
        f"總分：{overall:+.0f}（{overall_label}）",
    ]
    return [_h3("📊 客觀評分（規則計算）"), _ul(items)]


def _build_history_section(patterns: list[dict] | None) -> list[Node]:
    if not patterns:
        return []
    items = []
    for p in patterns:
        date = p.get("date", "")
        dec = p.get("decision", "")
        price = p.get("price", "")
        outcome = ""
        if p.get("was_correct") is not None:
            mark = "正確" if p["was_correct"] else "錯誤"
            ret = p.get("actual_return_pct")
            outcome = f"（{mark}{f', {ret:+.1f}%' if ret is not None else ''}）"
        items.append(f"{date} {dec} @ ¥{price}{outcome}")
    return [_h3("📚 歷史類似模式"), _ul(items)]


def _build_reasons_and_risks(payload: dict) -> list[Node]:
    out: list[Node] = []
    reasons = payload.get("key_reasons") or []
    if reasons:
        out += [_h3("💡 關鍵理由"), _ol([str(r) for r in reasons])]
    risks = payload.get("risks") or []
    if risks:
        out += [_h3("⚠️ 主要風險"), _ol([str(r) for r in risks])]
    return out


def _build_footer(payload: dict) -> list[Node]:
    model = str(payload.get("model") or "")
    note = "由 QuantDinger AI 生成 · 不構成投資建議"
    if model:
        note += f" · 模型 {model}"
    return [_hr(), _p({"tag": "i", "children": [note]})]


def build_page_content(payload: dict, name: str | None = None,
                       historical_patterns: list[dict] | None = None) -> list[Node]:
    """Compose the full Telegraph node tree."""
    nodes: list[Node] = []
    nodes += _build_decision_section(payload)
    nodes += [_hr()]
    nodes += _build_analysis_section(payload)
    nodes += [_hr()]
    nodes += _build_trend_section(payload)
    nodes += _build_score_section(payload)
    nodes += _build_history_section(historical_patterns)
    nodes += [_hr()]
    nodes += _build_reasons_and_risks(payload)
    nodes += _build_footer(payload)
    return nodes

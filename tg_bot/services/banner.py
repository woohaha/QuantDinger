"""Build a single-message TG HTML banner from /analyze JSON.

Uses HTML parse_mode. All dynamic content is HTML-escaped to defend against
LLM output containing <, >, &.

Keep total length well under 4096 (TG message limit).
"""
from html import escape

_DECISION_EMOJI = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}
_TF_LABEL = {"short": "短期", "medium": "中期", "long": "長期"}
_SUMMARY_MAX = 200   # chars; LLM summary often 1–3 sentences but can be long


def _pct(price: float, base: float) -> str:
    if not base:
        return ""
    delta = (price - base) / base * 100
    sign = "+" if delta >= 0 else ""
    return f"({sign}{delta:.1f}%)"


def _trim(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n].rstrip() + "..."


def build_banner(payload: dict, name: str | None, telegraph_url: str) -> str:
    """Return an HTML string ≤ 4096 chars for a single TG sendMessage."""
    code = str(payload.get("symbol") or "")
    decision = str(payload.get("decision") or "HOLD").upper()
    emoji = _DECISION_EMOJI.get(decision, "⚪")
    confidence = int(payload.get("confidence", 0) or 0)
    pos = int(payload.get("position_size_pct", 0) or 0)
    tf = _TF_LABEL.get(payload.get("timeframe", ""), payload.get("timeframe", ""))
    entry = float(payload.get("entry_price", 0) or 0)
    sl = float(payload.get("stop_loss", 0) or 0)
    tp = float(payload.get("take_profit", 0) or 0)
    summary = _trim(str(payload.get("summary") or ""), _SUMMARY_MAX)
    model = str(payload.get("model") or "")

    title = f"{escape(name)} ({escape(code)})" if name else escape(code)

    parts = [
        f"📊 <b>{title}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"{emoji} <b>{escape(decision)}</b> · 信心 {confidence}%",
        "",
        f"💰 入場：¥{entry}",
        f"🛡️ 止損：¥{sl}  {_pct(sl, entry)}",
        f"🎯 止盈：¥{tp}  {_pct(tp, entry)}",
        f"📦 倉位：{pos}%  ⏱ {escape(tf)}",
        "",
    ]
    if summary:
        parts.append(f"📝 <b>摘要</b>：{escape(summary)}")
        parts.append("")
    parts.append(f'🔗 <a href="{escape(telegraph_url, quote=True)}">📑 完整分析報告 →</a>')
    if model:
        parts.append("")
        parts.append(f"<i>模型 {escape(model)}</i>")

    html = "\n".join(parts)
    return html[:4096]

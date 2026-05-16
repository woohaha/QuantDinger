"""Shared pytest fixtures for tg_bot tests."""
import json
import pathlib
import sqlite3
import tempfile
from typing import Iterator

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """Temp SQLite file path; auto-cleaned by pytest."""
    return tmp_path / "test.db"


@pytest.fixture
def fake_analysis_json() -> dict:
    """A complete fixture of /api/fast-analysis/analyze response, shape stable.

    Mirrors the structure produced by FastAnalysisService.analyze() in
    backend_api_python/app/services/fast_analysis.py.
    """
    return {
        "decision": "BUY",
        "confidence": 78,
        "summary": "技術面 MACD 在零軸下方金叉重現，配合公司財報超預期，短期看多。",
        "analysis": {
            "technical": "RSI 42 走中性偏弱起，MACD 在零軸下方金叉重現，MA 趨勢看多。",
            "fundamental": "P/E 18.5 處於行業均值；最新季淨利潤年增 24%，超預期 8%。",
            "sentiment": "近 7 日新聞 7 條，5 條正面；行業景氣度回升明顯。",
        },
        "entry_price": 6.85,
        "stop_loss": 6.52,
        "take_profit": 7.43,
        "position_size_pct": 30,
        "timeframe": "medium",
        "key_reasons": [
            "MACD 在零軸下方金叉重現",
            "公司財報超預期",
            "行業景氣度回升",
        ],
        "risks": [
            "成交量持續萎縮，缺乏買盤跟進",
            "政策面不確定性",
        ],
        "technical_score": 72,
        "fundamental_score": 65,
        "sentiment_score": 58,
        "objective_score": {
            "technical_score": 72,
            "fundamental_score": 65,
            "sentiment_score": 58,
            "macro_score": 60,
            "overall_score": 38,
        },
        "trend_outlook": {
            "next_24h": {"score": 35, "trend": "BUY", "strength": "moderate"},
            "next_3d":  {"score": 65, "trend": "BUY", "strength": "moderate"},
            "next_1w":  {"score": 40, "trend": "BUY", "strength": "moderate"},
            "next_1m":  {"score": 30, "trend": "BUY", "strength": "mild"},
        },
        "consensus": {
            "consensus_score": 38.5,
            "consensus_decision": "BUY",
            "consensus_abs": 38.5,
            "agreement_ratio": 0.75,
            "quality_multiplier": 1.0,
            "market_regime": "trending",
        },
        "market": "CNStock",
        "symbol": "601766",
        "timeframe": "1D",
        "model": "moonshot-v1-8k",
        "memory_id": 12345,
        "analysis_time_ms": 48230,
    }


@pytest.fixture
def fake_symbol_meta() -> dict:
    """Optional company-name metadata layer in case banner/page need it."""
    return {"code": "601766", "name": "中國中車"}

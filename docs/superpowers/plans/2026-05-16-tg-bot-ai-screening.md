# QuantDinger AI 篩選 TG Bot 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 QuantDinger repo 加 `tg_bot/` 子專案，做一個瘦客戶端 Telegram bot：白名單群組裡發 `/ai 600519` → 即時呼叫 backend 既有 `/api/fast-analysis/analyze`，把詳細報告寫到 Telegraph 公開頁，TG 群只發精簡 banner + 連結；額外支援 `/watch /unwatch /list /scan` 操作群共享 watchlist。

**Architecture:** Python 3.11 + aiogram v3 + httpx async + SQLite。Bot 與 backend 同機部署，不同 Docker container，走 docker 內網直連。對外只用 Telegram long polling，不需 webhook / 反代。Telegraph API 免費，啟動時 auto createAccount，access_token 與 page paths 持久化到 SQLite。

**Tech Stack:** aiogram 3.x, httpx (async), pytest + pytest-asyncio + respx (HTTP mock), SQLite (內建 sqlite3), Docker。

**Spec:** [docs/superpowers/specs/2026-05-16-tg-bot-ai-screening-design.md](../specs/2026-05-16-tg-bot-ai-screening-design.md)

---

## 文件總覽（依職責劃分，互不依賴橫向）

```
tg_bot/
├── bot.py                       # entry point + dispatcher wiring
├── config.py                    # env vars → 強型別 Settings 物件
├── middlewares/whitelist.py     # group_id + user_id 雙重白名單
├── handlers/
│   ├── help.py                  # /start /help
│   ├── analyze.py               # /ai
│   ├── watchlist.py             # /watch /unwatch /list /scan
│   └── callbacks.py             # inline keyboard 切周期 / 刷新
├── services/
│   ├── storage.py               # 4 張 SQLite 表的純粹 DAO
│   ├── quantdinger.py           # backend HTTP 客戶端 (login + analyze)
│   ├── telegraph.py             # Telegraph API 客戶端
│   ├── page_builder.py          # backend JSON → Telegraph Node 樹（純函式）
│   └── banner.py                # backend JSON → TG banner HTML（純函式）
├── tests/                       # 與 services / middlewares 對應
├── data/.gitkeep                # docker volume mount 點
├── Dockerfile
├── requirements.txt
├── .dockerignore
└── README.md
```

**Modify**: `docker-compose.yml`（加 tg_bot service + tg_bot_data volume）。

**Build order**：先把所有純函式 / 純邏輯模組做完且測試齊全（任務 1–6），再做 IO 客戶端（任務 7–8），最後 handlers + entry point + 部署（任務 9–14）。每個任務獨立 commit。

---

## Task 1: 專案 scaffolding + requirements + pytest 設定

**Files:**
- Create: `tg_bot/requirements.txt`
- Create: `tg_bot/.dockerignore`
- Create: `tg_bot/.gitignore`
- Create: `tg_bot/conftest.py`
- Create: `tg_bot/pytest.ini`
- Create: `tg_bot/data/.gitkeep`
- Create: `tg_bot/__init__.py`、`tg_bot/services/__init__.py`、`tg_bot/handlers/__init__.py`、`tg_bot/middlewares/__init__.py`、`tg_bot/tests/__init__.py`

- [ ] **Step 1: Create directory structure and empty `__init__.py` files**

```bash
mkdir -p tg_bot/services tg_bot/handlers tg_bot/middlewares tg_bot/tests tg_bot/data
touch tg_bot/__init__.py tg_bot/services/__init__.py tg_bot/handlers/__init__.py tg_bot/middlewares/__init__.py tg_bot/tests/__init__.py tg_bot/data/.gitkeep
```

- [ ] **Step 2: Write `tg_bot/requirements.txt`**

```
aiogram>=3.4,<4
httpx>=0.27,<1
python-dotenv>=1.0
pydantic>=2.5,<3
pydantic-settings>=2.1

# dev / test
pytest>=8.0
pytest-asyncio>=0.23
respx>=0.20
```

- [ ] **Step 3: Write `tg_bot/.dockerignore`**

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.coverage
tests/
data/*
!data/.gitkeep
.git/
.gitignore
.dockerignore
README.md
```

- [ ] **Step 4: Write `tg_bot/.gitignore`**

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
data/*.db
data/*.db-journal
.env
```

- [ ] **Step 5: Write `tg_bot/pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
addopts = -ra
```

- [ ] **Step 6: Write `tg_bot/conftest.py`**

```python
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
```

- [ ] **Step 7: Verify pytest discovers nothing yet but exits clean**

Run: `cd tg_bot && python -m pytest -q`
Expected: `no tests ran in 0.NNs`, exit code 5 (no tests collected) — acceptable.

- [ ] **Step 8: Commit**

```bash
git add tg_bot/
git commit -m "feat(tg_bot): scaffold project structure and pytest config"
```

---

## Task 2: `config.py` — env vars 載入

**Files:**
- Create: `tg_bot/config.py`
- Test: `tg_bot/tests/test_config.py`

- [ ] **Step 1: Write failing test `tg_bot/tests/test_config.py`**

```python
"""Test config loading from env."""
import pytest
from pydantic import ValidationError

from tg_bot.config import Settings


def test_parses_required_env(monkeypatch):
    monkeypatch.setenv("TG_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("WHITELIST_GROUP_IDS", "-100111,-100222")
    monkeypatch.setenv("WHITELIST_USER_IDS", "111,222,333")
    monkeypatch.setenv("QUANTDINGER_API_URL", "http://backend:5000")
    monkeypatch.setenv("QUANTDINGER_USERNAME", "user")
    monkeypatch.setenv("QUANTDINGER_PASSWORD", "pw")

    s = Settings()

    assert s.tg_bot_token == "123:abc"
    assert s.whitelist_group_ids == {-100111, -100222}
    assert s.whitelist_user_ids == {111, 222, 333}
    assert str(s.quantdinger_api_url).rstrip("/") == "http://backend:5000"
    assert s.telegraph_author_name == "QuantDinger Bot"   # default
    assert s.telegraph_reuse_page is False
    assert s.db_path.name == "bot.db"


def test_missing_required_raises(monkeypatch):
    for key in ("TG_BOT_TOKEN", "WHITELIST_GROUP_IDS", "WHITELIST_USER_IDS",
                "QUANTDINGER_API_URL", "QUANTDINGER_USERNAME", "QUANTDINGER_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_telegraph_optional(monkeypatch):
    for key in ("TG_BOT_TOKEN", "WHITELIST_GROUP_IDS", "WHITELIST_USER_IDS",
                "QUANTDINGER_API_URL", "QUANTDINGER_USERNAME", "QUANTDINGER_PASSWORD"):
        monkeypatch.setenv(key, "x" if "URL" not in key else "http://backend:5000")
    monkeypatch.setenv("WHITELIST_GROUP_IDS", "-100111")
    monkeypatch.setenv("WHITELIST_USER_IDS", "111")
    monkeypatch.setenv("TELEGRAPH_ACCESS_TOKEN", "")
    s = Settings()
    assert s.telegraph_access_token is None or s.telegraph_access_token == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_config.py -v`
Expected: ImportError / FAIL (`config.Settings` does not exist).

- [ ] **Step 3: Write `tg_bot/config.py`**

```python
"""Bot settings loaded from environment variables."""
from pathlib import Path
from typing import Set

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_int_set(value: str) -> Set[int]:
    if not value:
        return set()
    out: Set[int] = set()
    for chunk in value.replace(" ", "").split(","):
        if chunk:
            out.add(int(chunk))
    return out


class Settings(BaseSettings):
    """Bot runtime configuration."""
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore")

    # --- Telegram ---
    tg_bot_token: str = Field(..., alias="TG_BOT_TOKEN")
    whitelist_group_ids: Set[int] = Field(..., alias="WHITELIST_GROUP_IDS")
    whitelist_user_ids: Set[int] = Field(..., alias="WHITELIST_USER_IDS")

    # --- Backend ---
    quantdinger_api_url: HttpUrl = Field(..., alias="QUANTDINGER_API_URL")
    quantdinger_username: str = Field(..., alias="QUANTDINGER_USERNAME")
    quantdinger_password: str = Field(..., alias="QUANTDINGER_PASSWORD")

    # --- Telegraph ---
    telegraph_access_token: str | None = Field(default=None, alias="TELEGRAPH_ACCESS_TOKEN")
    telegraph_author_name: str = Field(default="QuantDinger Bot", alias="TELEGRAPH_AUTHOR_NAME")
    telegraph_author_url: str = Field(default="", alias="TELEGRAPH_AUTHOR_URL")
    telegraph_reuse_page: bool = Field(default=False, alias="TELEGRAPH_REUSE_PAGE")

    # --- Storage ---
    db_path: Path = Field(default=Path("/data/bot.db"), alias="DB_PATH")

    @field_validator("whitelist_group_ids", "whitelist_user_ids", mode="before")
    @classmethod
    def _split_ids(cls, v):
        if isinstance(v, str):
            return _parse_int_set(v)
        return v

    @field_validator("telegraph_access_token", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v == "":
            return None
        return v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_config.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/config.py tg_bot/tests/test_config.py
git commit -m "feat(tg_bot): config.Settings reads env vars with whitelist parsing"
```

---

## Task 3: `services/storage.py` — SQLite DAO（4 張表）

**Files:**
- Create: `tg_bot/services/storage.py`
- Test: `tg_bot/tests/test_storage.py`

- [ ] **Step 1: Write failing tests `tg_bot/tests/test_storage.py`**

```python
"""Test SQLite storage layer (sync, single-process)."""
import pytest

from tg_bot.services.storage import Storage


@pytest.fixture
def storage(tmp_db_path):
    s = Storage(tmp_db_path)
    s.init_schema()
    yield s
    s.close()


def test_watchlist_add_and_list(storage):
    storage.watchlist_add("600519", "貴州茅台", added_by=111)
    storage.watchlist_add("000001", "平安銀行", added_by=222)
    rows = storage.watchlist_list()
    codes = {r["code"] for r in rows}
    assert codes == {"600519", "000001"}


def test_watchlist_add_dup_is_noop(storage):
    storage.watchlist_add("600519", "貴州茅台", added_by=111)
    storage.watchlist_add("600519", "新名字", added_by=222)   # ignored
    rows = storage.watchlist_list()
    assert len(rows) == 1
    # original name kept
    assert rows[0]["name"] == "貴州茅台"


def test_watchlist_remove(storage):
    storage.watchlist_add("600519", "貴州茅台", added_by=111)
    removed = storage.watchlist_remove("600519")
    assert removed is True
    assert storage.watchlist_list() == []


def test_watchlist_remove_missing_returns_false(storage):
    assert storage.watchlist_remove("999999") is False


def test_auth_cache_roundtrip(storage):
    assert storage.auth_cache_get() is None
    storage.auth_cache_set("token-abc")
    assert storage.auth_cache_get() == "token-abc"
    storage.auth_cache_set("token-xyz")
    assert storage.auth_cache_get() == "token-xyz"


def test_telegraph_account_roundtrip(storage):
    assert storage.telegraph_account_get() is None
    storage.telegraph_account_set(
        access_token="tok",
        short_name="QD",
        author_name="QuantDinger Bot",
        author_url="https://t.me/x",
        auth_url="https://edit.telegra.ph/auth/abc",
    )
    acc = storage.telegraph_account_get()
    assert acc["access_token"] == "tok"
    assert acc["short_name"] == "QD"
    assert acc["author_name"] == "QuantDinger Bot"


def test_telegraph_page_add_and_latest(storage):
    storage.telegraph_page_add(
        code="600519", path="600519-05-16",
        url="https://telegra.ph/600519-05-16",
        title="t", timeframe="1D", decision="BUY")
    storage.telegraph_page_add(
        code="600519", path="600519-05-17",
        url="https://telegra.ph/600519-05-17",
        title="t2", timeframe="1D", decision="SELL")
    latest = storage.telegraph_page_latest("600519")
    assert latest["path"] == "600519-05-17"
    assert latest["decision"] == "SELL"


def test_telegraph_page_latest_missing(storage):
    assert storage.telegraph_page_latest("999999") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_storage.py -v`
Expected: ImportError (`storage.Storage` not defined).

- [ ] **Step 3: Implement `tg_bot/services/storage.py`**

```python
"""SQLite DAO for watchlist + auth_cache + telegraph_account + telegraph_pages.

Sync stdlib sqlite3; bot is single-process and storage calls are fast.
Wrap in `asyncio.to_thread` from async handlers if blocking matters.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import sqlite3


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    code        TEXT PRIMARY KEY,
    name        TEXT,
    added_by    INTEGER NOT NULL,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_cache (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    token     TEXT NOT NULL,
    saved_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegraph_account (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    short_name   TEXT,
    author_name  TEXT,
    author_url   TEXT,
    auth_url     TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegraph_pages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL,
    path       TEXT NOT NULL UNIQUE,
    url        TEXT NOT NULL,
    title      TEXT,
    timeframe  TEXT,
    decision   TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telegraph_pages_code_time
    ON telegraph_pages(code, created_at DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    def init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    # ---- watchlist ----
    def watchlist_add(self, code: str, name: str | None, added_by: int) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO watchlist(code, name, added_by, added_at) VALUES (?,?,?,?)",
                (code, name, added_by, _now_iso()),
            )

    def watchlist_remove(self, code: str) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM watchlist WHERE code = ?", (code,))
            return cur.rowcount > 0

    def watchlist_list(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT code, name, added_by, added_at FROM watchlist ORDER BY added_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- auth cache ----
    def auth_cache_get(self) -> Optional[str]:
        row = self._conn.execute("SELECT token FROM auth_cache WHERE id = 1").fetchone()
        return row["token"] if row else None

    def auth_cache_set(self, token: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO auth_cache(id, token, saved_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET token = excluded.token, saved_at = excluded.saved_at",
                (token, _now_iso()),
            )

    # ---- telegraph account ----
    def telegraph_account_get(self) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT access_token, short_name, author_name, author_url, auth_url, created_at "
            "FROM telegraph_account WHERE id = 1"
        ).fetchone()
        return dict(row) if row else None

    def telegraph_account_set(self, *, access_token: str, short_name: str | None,
                              author_name: str | None, author_url: str | None,
                              auth_url: str | None) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO telegraph_account(id, access_token, short_name, author_name, "
                "author_url, auth_url, created_at) VALUES (1, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET access_token = excluded.access_token, "
                "short_name = excluded.short_name, author_name = excluded.author_name, "
                "author_url = excluded.author_url, auth_url = excluded.auth_url",
                (access_token, short_name, author_name, author_url, auth_url, _now_iso()),
            )

    # ---- telegraph pages ----
    def telegraph_page_add(self, *, code: str, path: str, url: str,
                           title: str | None, timeframe: str | None,
                           decision: str | None) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO telegraph_pages(code, path, url, title, timeframe, decision, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, path, url, title, timeframe, decision, _now_iso()),
            )

    def telegraph_page_latest(self, code: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT code, path, url, title, timeframe, decision, created_at "
            "FROM telegraph_pages WHERE code = ? ORDER BY created_at DESC LIMIT 1",
            (code,),
        ).fetchone()
        return dict(row) if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_storage.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/services/storage.py tg_bot/tests/test_storage.py
git commit -m "feat(tg_bot): SQLite Storage DAO with 4 tables"
```

---

## Task 4: `services/page_builder.py` — JSON → Telegraph Node 樹

**Files:**
- Create: `tg_bot/services/page_builder.py`
- Test: `tg_bot/tests/test_page_builder.py`

- [ ] **Step 1: Write failing test `tg_bot/tests/test_page_builder.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_page_builder.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tg_bot/services/page_builder.py`**

```python
"""Convert backend /analyze JSON to Telegraph Node tree.

Telegraph Node format:
  - str: text content
  - dict: { "tag": "p" | "h3" | "ul" | ..., "attrs": {...}?, "children": [Node]? }

Limits:
  - title  ≤ 256 chars
  - content ≤ 64 KB serialized
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_page_builder.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/services/page_builder.py tg_bot/tests/test_page_builder.py
git commit -m "feat(tg_bot): page_builder converts /analyze JSON to Telegraph Node tree"
```

---

## Task 5: `services/banner.py` — JSON → TG HTML banner

**Files:**
- Create: `tg_bot/services/banner.py`
- Test: `tg_bot/tests/test_banner.py`

- [ ] **Step 1: Write failing test `tg_bot/tests/test_banner.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_banner.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tg_bot/services/banner.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_banner.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/services/banner.py tg_bot/tests/test_banner.py
git commit -m "feat(tg_bot): banner builds HTML-escaped TG message with Telegraph link"
```

---

## Task 6: `middlewares/whitelist.py` — group + user 雙重白名單

**Files:**
- Create: `tg_bot/middlewares/whitelist.py`
- Test: `tg_bot/tests/test_whitelist.py`

- [ ] **Step 1: Write failing test `tg_bot/tests/test_whitelist.py`**

```python
"""Test WhitelistMiddleware."""
from types import SimpleNamespace

import pytest

from tg_bot.middlewares.whitelist import WhitelistMiddleware


@pytest.fixture
def mw():
    return WhitelistMiddleware(allowed_group_ids={-100111}, allowed_user_ids={111, 222})


def _make_event(chat_id: int, user_id: int, chat_type: str = "supergroup"):
    """Mock aiogram TelegramObject with chat + from_user."""
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncRecorder(),
    )


class AsyncRecorder:
    def __init__(self):
        self.calls = []
    async def __call__(self, text, **kw):
        self.calls.append((text, kw))


async def _handler_noop(event, data):
    data.setdefault("handler_called", True)
    return "ok"


async def test_allows_whitelisted_combo(mw):
    event = _make_event(chat_id=-100111, user_id=111)
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    assert result == "ok"
    assert data.get("handler_called") is True


async def test_silently_blocks_unknown_group(mw):
    event = _make_event(chat_id=-100999, user_id=111)
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    assert result is None
    assert "handler_called" not in data


async def test_blocks_unknown_user_in_known_group(mw):
    event = _make_event(chat_id=-100111, user_id=999)
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    # Unknown user gets a polite reply (not silent), per spec §10
    assert result is None
    assert len(event.answer.calls) == 1
    assert "白名單" in event.answer.calls[0][0]


async def test_blocks_private_chat(mw):
    event = _make_event(chat_id=111, user_id=111, chat_type="private")
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    assert result is None
    assert len(event.answer.calls) == 1
    assert "群組" in event.answer.calls[0][0]


async def test_handles_event_without_user(mw):
    """Some updates (e.g. channel posts) have no from_user."""
    event = SimpleNamespace(chat=SimpleNamespace(id=-100111, type="supergroup"),
                            from_user=None, answer=AsyncRecorder())
    data: dict = {}
    result = await mw(_handler_noop, event, data)
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_whitelist.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tg_bot/middlewares/whitelist.py`**

```python
"""Aiogram middleware: enforce group_id + user_id whitelist."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class WhitelistMiddleware(BaseMiddleware):
    """Drops events that aren't from a (whitelisted group, whitelisted user).

    Behaviour matches spec §10:
      - non-whitelisted group  → silent drop
      - whitelisted group, non-whitelisted user → polite reply
      - private chat → polite reply
      - event without chat/user → silent drop
    """

    def __init__(self, allowed_group_ids: set[int], allowed_user_ids: set[int]):
        super().__init__()
        self.groups = set(allowed_group_ids)
        self.users = set(allowed_user_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = getattr(event, "chat", None)
        user = getattr(event, "from_user", None)

        if chat is None or user is None:
            return None

        chat_type = getattr(chat, "type", "")
        if chat_type == "private":
            answer = getattr(event, "answer", None)
            if answer:
                await answer("本 bot 只在指定群組工作")
            return None

        if chat.id not in self.groups:
            return None        # silent

        if user.id not in self.users:
            answer = getattr(event, "answer", None)
            if answer:
                await answer("你不在白名單，找管理員加你")
            return None

        return await handler(event, data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_whitelist.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/middlewares/whitelist.py tg_bot/tests/test_whitelist.py
git commit -m "feat(tg_bot): WhitelistMiddleware for group+user double check"
```

---

## Task 7: `services/quantdinger.py` — backend HTTP 客戶端

**Files:**
- Create: `tg_bot/services/quantdinger.py`
- Test: `tg_bot/tests/test_quantdinger.py`

- [ ] **Step 1: Write failing test `tg_bot/tests/test_quantdinger.py`**

```python
"""Test QuantDingerClient using respx to mock backend HTTP."""
import httpx
import pytest
import respx

from tg_bot.services.quantdinger import QuantDingerClient, BackendError


BASE = "http://backend:5000"


@pytest.fixture
def client():
    return QuantDingerClient(base_url=BASE, username="u", password="pw", timeout=5)


@respx.mock
async def test_login_success(client):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        200, json={"code": 1, "msg": "ok",
                   "data": {"token": "TKN", "userinfo": {"id": 1}}}))
    token = await client.login()
    assert token == "TKN"
    assert client.token == "TKN"
    await client.aclose()


@respx.mock
async def test_login_invalid_credentials(client):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        401, json={"code": 0, "msg": "Invalid credentials", "data": None}))
    with pytest.raises(BackendError) as exc:
        await client.login()
    assert "Invalid credentials" in str(exc.value)
    await client.aclose()


@respx.mock
async def test_analyze_success(client, fake_analysis_json):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        200, json={"code": 1, "data": {"token": "TKN"}}))
    respx.post(f"{BASE}/api/fast-analysis/analyze").mock(return_value=httpx.Response(
        200, json={"code": 1, "msg": "success", "data": fake_analysis_json}))

    result = await client.analyze(market="CNStock", symbol="601766",
                                  language="zh-TW", timeframe="1D")
    assert result["decision"] == "BUY"
    assert result["symbol"] == "601766"
    await client.aclose()


@respx.mock
async def test_analyze_relogin_on_401(client, fake_analysis_json):
    """Token expired mid-flight: client should re-login transparently."""
    respx.post(f"{BASE}/api/auth/login").mock(side_effect=[
        httpx.Response(200, json={"code": 1, "data": {"token": "OLD"}}),
        httpx.Response(200, json={"code": 1, "data": {"token": "NEW"}}),
    ])
    respx.post(f"{BASE}/api/fast-analysis/analyze").mock(side_effect=[
        httpx.Response(401, json={"code": 401, "msg": "Token invalid"}),
        httpx.Response(200, json={"code": 1, "data": fake_analysis_json}),
    ])
    result = await client.analyze(market="CNStock", symbol="601766",
                                  language="zh-TW", timeframe="1D")
    assert result["decision"] == "BUY"
    assert client.token == "NEW"
    await client.aclose()


@respx.mock
async def test_analyze_429_inflight_raises(client):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        200, json={"code": 1, "data": {"token": "TKN"}}))
    respx.post(f"{BASE}/api/fast-analysis/analyze").mock(return_value=httpx.Response(
        429, json={"code": 0, "msg": "Analysis already in progress",
                   "data": {"in_progress": True}}))
    with pytest.raises(BackendError) as exc:
        await client.analyze(market="CNStock", symbol="601766",
                             language="zh-TW", timeframe="1D")
    assert "in_progress" in str(exc.value).lower() or "已有" in str(exc.value) or "in progress" in str(exc.value).lower()
    await client.aclose()


@respx.mock
async def test_analyze_insufficient_credits(client):
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(
        200, json={"code": 1, "data": {"token": "TKN"}}))
    respx.post(f"{BASE}/api/fast-analysis/analyze").mock(return_value=httpx.Response(
        400, json={"code": 0, "msg": "Insufficient credits",
                   "data": {"required": 10, "current": 3, "shortage": 7}}))
    with pytest.raises(BackendError) as exc:
        await client.analyze(market="CNStock", symbol="601766",
                             language="zh-TW", timeframe="1D")
    assert "credits" in str(exc.value).lower()
    await client.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_quantdinger.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tg_bot/services/quantdinger.py`**

```python
"""HTTP client wrapping QuantDinger backend.

Two endpoints used:
  POST /api/auth/login            — get JWT
  POST /api/fast-analysis/analyze — synchronous AI screening (30–90 s)

Handles transparent re-login on 401, surfaces credits/in-progress errors.
"""
from typing import Optional

import httpx


class BackendError(Exception):
    """Surface to handler so it can show a user-friendly message."""
    def __init__(self, msg: str, *, code: int | None = None, data: dict | None = None):
        super().__init__(msg)
        self.code = code
        self.data = data or {}


class QuantDingerClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 150.0):
        self.base = str(base_url).rstrip("/")
        self.username = username
        self.password = password
        self._client = httpx.AsyncClient(timeout=timeout)
        self.token: Optional[str] = None

    def set_initial_token(self, token: str | None) -> None:
        """Seed from auth_cache so we skip first login if possible."""
        self.token = token

    async def aclose(self) -> None:
        await self._client.aclose()

    async def login(self) -> str:
        resp = await self._client.post(
            f"{self.base}/api/auth/login",
            json={"username": self.username, "password": self.password},
        )
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code != 200 or payload.get("code") != 1:
            raise BackendError(payload.get("msg") or f"Login HTTP {resp.status_code}",
                               code=resp.status_code, data=payload.get("data"))
        token = (payload.get("data") or {}).get("token")
        if not token:
            raise BackendError("Login response missing token", code=200, data=payload)
        self.token = token
        return token

    async def _ensure_token(self) -> str:
        if not self.token:
            await self.login()
        return self.token  # type: ignore[return-value]

    async def analyze(self, *, market: str, symbol: str, language: str = "zh-TW",
                      timeframe: str = "1D", model: str | None = None) -> dict:
        body = {"market": market, "symbol": symbol, "language": language,
                "timeframe": timeframe}
        if model:
            body["model"] = model

        resp = await self._post_authed("/api/fast-analysis/analyze", json=body)
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        code = payload.get("code")

        if resp.status_code == 200 and code == 1:
            return payload.get("data") or {}

        msg = payload.get("msg") or f"HTTP {resp.status_code}"
        data = payload.get("data") or {}

        if resp.status_code == 429:
            raise BackendError(f"in_progress: {msg}", code=429, data=data)
        if resp.status_code == 400 and "Insufficient credits" in msg:
            raise BackendError(
                f"credits insufficient (need {data.get('required')}, "
                f"have {data.get('current')})",
                code=400, data=data,
            )
        raise BackendError(msg, code=resp.status_code, data=data)

    async def _post_authed(self, path: str, *, json: dict) -> httpx.Response:
        """POST that auto re-logins once on 401."""
        token = await self._ensure_token()
        url = f"{self.base}{path}"
        resp = await self._client.post(url, json=json,
                                       headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 401:
            self.token = None
            token = await self.login()
            resp = await self._client.post(url, json=json,
                                           headers={"Authorization": f"Bearer {token}"})
        return resp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_quantdinger.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/services/quantdinger.py tg_bot/tests/test_quantdinger.py
git commit -m "feat(tg_bot): QuantDingerClient with login + analyze + 401 retry"
```

---

## Task 8: `services/telegraph.py` — Telegraph API 客戶端

**Files:**
- Create: `tg_bot/services/telegraph.py`
- Test: `tg_bot/tests/test_telegraph.py`

- [ ] **Step 1: Write failing test `tg_bot/tests/test_telegraph.py`**

```python
"""Test TelegraphClient against the api.telegra.ph contract using respx."""
import httpx
import pytest
import respx

from tg_bot.services.telegraph import TelegraphClient, TelegraphError


BASE = "https://api.telegra.ph"


@respx.mock
async def test_create_account_returns_token():
    respx.post(f"{BASE}/createAccount").mock(return_value=httpx.Response(
        200, json={"ok": True, "result": {
            "access_token": "ATK",
            "auth_url": "https://edit.telegra.ph/auth/abc",
            "short_name": "QD",
            "author_name": "QuantDinger Bot",
            "author_url": "https://t.me/x",
        }}))
    c = TelegraphClient()
    result = await c.create_account(short_name="QD",
                                    author_name="QuantDinger Bot",
                                    author_url="https://t.me/x")
    assert result["access_token"] == "ATK"
    assert result["short_name"] == "QD"
    await c.aclose()


@respx.mock
async def test_create_page_returns_url():
    respx.post(f"{BASE}/createPage").mock(return_value=httpx.Response(
        200, json={"ok": True, "result": {
            "path": "Title-05-16",
            "url": "https://telegra.ph/Title-05-16",
            "title": "Title",
            "description": "",
            "author_name": "QuantDinger Bot",
        }}))
    c = TelegraphClient(access_token="ATK")
    result = await c.create_page(title="Title",
                                 content=[{"tag": "p", "children": ["hi"]}],
                                 author_name="QuantDinger Bot",
                                 author_url="")
    assert result["url"] == "https://telegra.ph/Title-05-16"
    assert result["path"] == "Title-05-16"
    await c.aclose()


@respx.mock
async def test_edit_page_returns_url():
    respx.post(f"{BASE}/editPage/foo-05-16").mock(return_value=httpx.Response(
        200, json={"ok": True, "result": {
            "path": "foo-05-16",
            "url": "https://telegra.ph/foo-05-16",
        }}))
    c = TelegraphClient(access_token="ATK")
    result = await c.edit_page(path="foo-05-16", title="Title",
                               content=[{"tag": "p", "children": ["hi"]}],
                               author_name="QD", author_url="")
    assert result["url"] == "https://telegra.ph/foo-05-16"
    await c.aclose()


@respx.mock
async def test_create_page_error_raises():
    respx.post(f"{BASE}/createPage").mock(return_value=httpx.Response(
        200, json={"ok": False, "error": "ACCESS_TOKEN_INVALID"}))
    c = TelegraphClient(access_token="bad")
    with pytest.raises(TelegraphError) as exc:
        await c.create_page(title="T", content=[{"tag": "p", "children": ["x"]}],
                            author_name="QD", author_url="")
    assert "ACCESS_TOKEN_INVALID" in str(exc.value)
    await c.aclose()


@respx.mock
async def test_create_page_serializes_content_to_json():
    """Telegraph requires content as JSON string, not nested form."""
    captured = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["data"] = dict(request.url.params) if request.url.params else None
        body = request.read().decode("utf-8")
        captured["body"] = body
        return httpx.Response(200, json={
            "ok": True, "result": {"path": "p", "url": "https://telegra.ph/p"}
        })

    respx.post(f"{BASE}/createPage").mock(side_effect=_handler)

    c = TelegraphClient(access_token="ATK")
    await c.create_page(title="T",
                        content=[{"tag": "p", "children": ["hi"]}],
                        author_name="QD", author_url="")
    # content field should appear as a JSON-encoded string within the form body
    assert "content=" in captured["body"]
    assert "%22tag%22" in captured["body"] or '"tag"' in captured["body"]
    await c.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_telegraph.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tg_bot/services/telegraph.py`**

```python
"""Telegraph API client (https://telegra.ph/api).

Methods used:
  POST /createAccount   (no token)  → bootstrap once on first run
  POST /createPage      (token)     → write a new article
  POST /editPage/<path> (token)     → optional re-publish under same path

All requests are POST with form-encoded body. `content` is a JSON-encoded
string. Returns dict on success; raises TelegraphError on `ok: false`.
"""
import json
from typing import Any

import httpx


BASE = "https://api.telegra.ph"


class TelegraphError(Exception):
    pass


class TelegraphClient:
    def __init__(self, access_token: str | None = None, timeout: float = 30.0):
        self.access_token = access_token
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_account(self, *, short_name: str, author_name: str,
                             author_url: str) -> dict:
        form = {"short_name": short_name[:32],
                "author_name": author_name[:128],
                "author_url":  (author_url or "")[:512]}
        return await self._call("createAccount", form)

    async def create_page(self, *, title: str, content: list, author_name: str,
                          author_url: str, return_content: bool = False) -> dict:
        form = self._build_page_form(title=title, content=content,
                                     author_name=author_name, author_url=author_url,
                                     return_content=return_content)
        return await self._call("createPage", form)

    async def edit_page(self, *, path: str, title: str, content: list,
                        author_name: str, author_url: str,
                        return_content: bool = False) -> dict:
        form = self._build_page_form(title=title, content=content,
                                     author_name=author_name, author_url=author_url,
                                     return_content=return_content)
        return await self._call(f"editPage/{path}", form)

    def _build_page_form(self, *, title: str, content: list, author_name: str,
                         author_url: str, return_content: bool) -> dict[str, Any]:
        if not self.access_token:
            raise TelegraphError("access_token required")
        return {
            "access_token": self.access_token,
            "title": title[:256],
            "content": json.dumps(content, ensure_ascii=False),
            "author_name": (author_name or "")[:128],
            "author_url":  (author_url or "")[:512],
            "return_content": "true" if return_content else "false",
        }

    async def _call(self, method: str, form: dict) -> dict:
        resp = await self._client.post(f"{BASE}/{method}", data=form)
        if resp.status_code != 200:
            raise TelegraphError(f"HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as e:
            raise TelegraphError(f"bad JSON: {e}") from e
        if not payload.get("ok"):
            raise TelegraphError(payload.get("error") or "unknown telegraph error")
        return payload.get("result") or {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_telegraph.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/services/telegraph.py tg_bot/tests/test_telegraph.py
git commit -m "feat(tg_bot): TelegraphClient with createAccount/createPage/editPage"
```

---

## Task 9: `handlers/help.py` — /start /help

**Files:**
- Create: `tg_bot/handlers/help.py`

(No unit test; trivial static reply, covered by manual smoke test.)

- [ ] **Step 1: Implement `tg_bot/handlers/help.py`**

```python
"""/start /help handlers."""
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

router = Router(name="help")


_HELP_TEXT = (
    "📊 <b>QuantDinger AI 篩選 Bot</b>\n\n"
    "支援 A 股（6 位代碼）。所有命令僅在白名單群組生效。\n\n"
    "<b>命令</b>\n"
    "/ai &lt;code&gt;       — 即時 AI 分析（30–90 秒，結果含 Telegraph 連結）\n"
    "/watch &lt;code&gt;    — 加入群共享 watchlist\n"
    "/unwatch &lt;code&gt;  — 從 watchlist 移除\n"
    "/list             — 顯示 watchlist\n"
    "/scan             — 對 watchlist 全跑 AI\n"
    "/help             — 顯示本說明\n\n"
    "範例：<code>/ai 600519</code>"
)


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(_HELP_TEXT, parse_mode="HTML", disable_web_page_preview=True)
```

- [ ] **Step 2: Commit**

```bash
git add tg_bot/handlers/help.py
git commit -m "feat(tg_bot): /start and /help handler"
```

---

## Task 10: `handlers/watchlist.py` — /watch /unwatch /list

**Files:**
- Create: `tg_bot/handlers/watchlist.py`
- Test: `tg_bot/tests/test_watchlist_handlers.py`

- [ ] **Step 1: Write failing test `tg_bot/tests/test_watchlist_handlers.py`**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_watchlist_handlers.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tg_bot/handlers/watchlist.py`**

```python
"""/watch /unwatch /list /scan handlers.

Note: /scan delegates back to analyze handler — defined in Task 12 where the
shared `run_analysis_flow()` helper exists.
"""
import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from tg_bot.services.storage import Storage

router = Router(name="watchlist")

_CODE_RE = re.compile(r"^\d{6}$")


def parse_code(text: str) -> str:
    """Extract the 6-digit code from a command message text. Raises ValueError."""
    parts = (text or "").strip().split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        raise ValueError("缺少代碼")
    code = parts[1].strip().split()[0]
    if not _CODE_RE.match(code):
        raise ValueError("代碼必須為 6 位數字")
    return code


def _err(msg: Message, text: str) -> "Coroutine":
    return msg.answer(f"❌ {text}\n用法：<code>/ai 600519</code>", parse_mode="HTML")


@router.message(Command("watch"))
async def cmd_watch(msg: Message, storage: Storage):
    try:
        code = parse_code(msg.text or "")
    except ValueError as e:
        await _err(msg, str(e))
        return
    storage.watchlist_add(code, name=None, added_by=msg.from_user.id)
    await msg.answer(f"✅ 已加入 watchlist：<code>{code}</code>", parse_mode="HTML")


@router.message(Command("unwatch"))
async def cmd_unwatch(msg: Message, storage: Storage):
    try:
        code = parse_code(msg.text or "")
    except ValueError as e:
        await _err(msg, str(e))
        return
    removed = storage.watchlist_remove(code)
    if removed:
        await msg.answer(f"✅ 已移除：<code>{code}</code>", parse_mode="HTML")
    else:
        await msg.answer(f"⚠️ 不在 watchlist：<code>{code}</code>", parse_mode="HTML")


@router.message(Command("list"))
async def cmd_list(msg: Message, storage: Storage):
    rows = storage.watchlist_list()
    if not rows:
        await msg.answer("📭 Watchlist 為空。用 <code>/watch 600519</code> 加入。",
                         parse_mode="HTML")
        return
    lines = ["📋 <b>群共享 Watchlist</b>"]
    for r in rows:
        name = r["name"] or "—"
        lines.append(f"• <code>{r['code']}</code>  {name}")
    await msg.answer("\n".join(lines), parse_mode="HTML")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_watchlist_handlers.py -v`
Expected: 4 PASS (parametrize → 4 ok cases) + 5 invalid → 9 PASS total.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/handlers/watchlist.py tg_bot/tests/test_watchlist_handlers.py
git commit -m "feat(tg_bot): /watch /unwatch /list handlers + parse_code"
```

---

## Task 11: `handlers/analyze.py` — /ai 流程（核心）

This task ties everything together: banner + Telegraph + storage + backend.

**Files:**
- Create: `tg_bot/handlers/analyze.py`
- Test: `tg_bot/tests/test_analyze_flow.py`

- [ ] **Step 1: Write failing test `tg_bot/tests/test_analyze_flow.py`**

```python
"""Test the high-level analyze flow: run_analysis(code, ...) end-to-end with
all external deps mocked. We test the orchestration, not aiogram routing.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.handlers.analyze import run_analysis


@pytest.fixture
def storage_mock():
    m = MagicMock()
    m.telegraph_page_latest.return_value = None
    return m


@pytest.fixture
def qd_mock(fake_analysis_json):
    m = MagicMock()
    m.analyze = AsyncMock(return_value=fake_analysis_json)
    return m


@pytest.fixture
def tg_mock():
    m = MagicMock()
    m.create_page = AsyncMock(return_value={
        "path": "601766-05-16",
        "url": "https://telegra.ph/601766-05-16",
    })
    m.edit_page = AsyncMock()
    return m


async def test_happy_path_creates_page_and_returns_banner(
        storage_mock, qd_mock, tg_mock, fake_analysis_json):
    banner, url = await run_analysis(
        code="601766", name="中國中車", timeframe="1D",
        storage=storage_mock, quantdinger=qd_mock, telegraph=tg_mock,
        telegraph_author_name="QD", telegraph_author_url="",
        reuse_page=False,
    )
    qd_mock.analyze.assert_awaited_once_with(
        market="CNStock", symbol="601766", language="zh-TW", timeframe="1D")
    tg_mock.create_page.assert_awaited_once()
    tg_mock.edit_page.assert_not_awaited()
    storage_mock.telegraph_page_add.assert_called_once()
    storage_mock.watchlist_list.assert_not_called()    # not part of /ai
    assert url == "https://telegra.ph/601766-05-16"
    assert "中國中車" in banner
    assert "BUY" in banner
    assert "https://telegra.ph/601766-05-16" in banner


async def test_reuse_page_calls_edit_when_prior_exists(
        storage_mock, qd_mock, tg_mock):
    storage_mock.telegraph_page_latest.return_value = {
        "code": "601766", "path": "601766-old", "url": "https://telegra.ph/601766-old"
    }
    tg_mock.edit_page = AsyncMock(return_value={
        "path": "601766-old", "url": "https://telegra.ph/601766-old"
    })
    banner, url = await run_analysis(
        code="601766", name="中國中車", timeframe="1D",
        storage=storage_mock, quantdinger=qd_mock, telegraph=tg_mock,
        telegraph_author_name="QD", telegraph_author_url="",
        reuse_page=True,
    )
    tg_mock.edit_page.assert_awaited_once()
    tg_mock.create_page.assert_not_awaited()
    assert url == "https://telegra.ph/601766-old"


async def test_telegraph_failure_returns_degraded_banner(
        storage_mock, qd_mock, fake_analysis_json):
    from tg_bot.services.telegraph import TelegraphError
    tg = MagicMock()
    tg.create_page = AsyncMock(side_effect=TelegraphError("ACCESS_TOKEN_INVALID"))
    tg.edit_page = AsyncMock(side_effect=TelegraphError("ACCESS_TOKEN_INVALID"))

    banner, url = await run_analysis(
        code="601766", name="中國中車", timeframe="1D",
        storage=storage_mock, quantdinger=qd_mock, telegraph=tg,
        telegraph_author_name="QD", telegraph_author_url="",
        reuse_page=False,
    )
    assert url == ""
    # Banner still has the core fields plus an explicit failure note
    assert "BUY" in banner
    assert "詳細報告生成失敗" in banner


async def test_backend_error_bubbles_up(storage_mock, tg_mock):
    from tg_bot.services.quantdinger import BackendError
    qd = MagicMock()
    qd.analyze = AsyncMock(side_effect=BackendError("credits insufficient (need 10, have 3)"))
    with pytest.raises(BackendError):
        await run_analysis(
            code="601766", name=None, timeframe="1D",
            storage=storage_mock, quantdinger=qd, telegraph=tg_mock,
            telegraph_author_name="QD", telegraph_author_url="",
            reuse_page=False,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tg_bot && python -m pytest tests/test_analyze_flow.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tg_bot/handlers/analyze.py`**

```python
"""/ai handler + reusable run_analysis() helper.

run_analysis(): pure orchestration, all I/O via injected clients — easy to test.
cmd_ai():       aiogram glue around run_analysis().
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tg_bot.handlers.watchlist import parse_code
from tg_bot.services.banner import build_banner
from tg_bot.services.page_builder import build_page_content, build_page_title
from tg_bot.services.quantdinger import BackendError, QuantDingerClient
from tg_bot.services.storage import Storage
from tg_bot.services.telegraph import TelegraphClient, TelegraphError

router = Router(name="analyze")


async def run_analysis(*, code: str, name: str | None, timeframe: str,
                       storage: Storage, quantdinger: QuantDingerClient,
                       telegraph: TelegraphClient,
                       telegraph_author_name: str,
                       telegraph_author_url: str,
                       reuse_page: bool) -> tuple[str, str]:
    """Run the full analysis flow and return (banner_html, telegraph_url).

    Raises BackendError if the backend call fails (caller decides how to render).
    Telegraph failures are swallowed — banner is returned with a degraded note
    and url is "".
    """
    payload = await quantdinger.analyze(
        market="CNStock", symbol=code, language="zh-TW", timeframe=timeframe,
    )

    title = build_page_title(payload, name=name)
    content = build_page_content(payload, name=name)

    page_url = ""
    page_path = ""
    try:
        if reuse_page:
            existing = storage.telegraph_page_latest(code)
            if existing:
                result = await telegraph.edit_page(
                    path=existing["path"], title=title, content=content,
                    author_name=telegraph_author_name,
                    author_url=telegraph_author_url,
                )
            else:
                result = await telegraph.create_page(
                    title=title, content=content,
                    author_name=telegraph_author_name,
                    author_url=telegraph_author_url,
                )
        else:
            result = await telegraph.create_page(
                title=title, content=content,
                author_name=telegraph_author_name,
                author_url=telegraph_author_url,
            )
        page_url = str(result.get("url") or "")
        page_path = str(result.get("path") or "")
    except TelegraphError:
        # Degraded — banner will display a failure note
        pass

    if page_path:
        storage.telegraph_page_add(
            code=code, path=page_path, url=page_url, title=title,
            timeframe=timeframe, decision=str(payload.get("decision") or "").upper(),
        )

    if page_url:
        banner = build_banner(payload, name=name, telegraph_url=page_url)
    else:
        banner = (
            build_banner(payload, name=name, telegraph_url="about:blank")
            + "\n\n⚠️ <i>詳細報告生成失敗，請稍後 /ai 重試</i>"
        )

    return banner, page_url


def _timeframe_keyboard(code: str) -> "InlineKeyboardMarkup":
    kb = InlineKeyboardBuilder()
    for tf, label in (("1H", "切 1H"), ("4H", "切 4H"),
                      ("1W", "切 1W"), ("1D", "刷新")):
        kb.button(text=label, callback_data=f"tf:{code}:{tf}")
    kb.adjust(4)
    return kb.as_markup()


@router.message(Command("ai"))
async def cmd_ai(msg: Message,
                 storage: Storage,
                 quantdinger: QuantDingerClient,
                 telegraph: TelegraphClient,
                 telegraph_author_name: str,
                 telegraph_author_url: str,
                 reuse_page: bool):
    try:
        code = parse_code(msg.text or "")
    except ValueError as e:
        await msg.answer(f"❌ {e}\n用法：<code>/ai 600519</code>",
                         parse_mode="HTML")
        return

    pending = await msg.answer(f"🔍 正在分析 <code>{code}</code>...（約 30–90 秒）",
                                parse_mode="HTML")

    # Look up name from watchlist if present
    name = None
    for r in storage.watchlist_list():
        if r["code"] == code:
            name = r["name"]
            break

    try:
        banner, _url = await run_analysis(
            code=code, name=name, timeframe="1D",
            storage=storage, quantdinger=quantdinger, telegraph=telegraph,
            telegraph_author_name=telegraph_author_name,
            telegraph_author_url=telegraph_author_url,
            reuse_page=reuse_page,
        )
    except BackendError as e:
        await pending.edit_text(f"❌ 分析失敗：{e}", parse_mode="HTML")
        return
    except Exception as e:    # network / unexpected
        await pending.edit_text(f"❌ 分析異常：{type(e).__name__}: {e}",
                                parse_mode="HTML")
        return

    await pending.edit_text(banner, parse_mode="HTML",
                             disable_web_page_preview=False,
                             reply_markup=_timeframe_keyboard(code))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tg_bot && python -m pytest tests/test_analyze_flow.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tg_bot/handlers/analyze.py tg_bot/tests/test_analyze_flow.py
git commit -m "feat(tg_bot): /ai handler with run_analysis orchestration"
```

---

## Task 12: `handlers/callbacks.py` + /scan

**Files:**
- Create: `tg_bot/handlers/callbacks.py`
- Modify: `tg_bot/handlers/watchlist.py` (add /scan)

- [ ] **Step 1: Implement `tg_bot/handlers/callbacks.py`**

```python
"""Inline keyboard callbacks — currently only timeframe switching.

callback_data format: "tf:<code>:<timeframe>"
"""
import asyncio

from aiogram import Router, F
from aiogram.types import CallbackQuery

from tg_bot.handlers.analyze import run_analysis, _timeframe_keyboard
from tg_bot.services.quantdinger import BackendError, QuantDingerClient
from tg_bot.services.storage import Storage
from tg_bot.services.telegraph import TelegraphClient

router = Router(name="callbacks")


@router.callback_query(F.data.startswith("tf:"))
async def on_timeframe(cb: CallbackQuery,
                       storage: Storage,
                       quantdinger: QuantDingerClient,
                       telegraph: TelegraphClient,
                       telegraph_author_name: str,
                       telegraph_author_url: str,
                       reuse_page: bool):
    try:
        _, code, tf = (cb.data or "").split(":")
    except ValueError:
        await cb.answer("無效操作")
        return

    await cb.answer(f"重新分析 {code} ({tf})...")

    # Show pending state
    await cb.message.edit_text(
        f"🔍 正在以 <b>{tf}</b> 周期分析 <code>{code}</code>...",
        parse_mode="HTML",
    )

    name = None
    for r in storage.watchlist_list():
        if r["code"] == code:
            name = r["name"]
            break

    try:
        banner, _ = await run_analysis(
            code=code, name=name, timeframe=tf,
            storage=storage, quantdinger=quantdinger, telegraph=telegraph,
            telegraph_author_name=telegraph_author_name,
            telegraph_author_url=telegraph_author_url,
            reuse_page=reuse_page,
        )
    except BackendError as e:
        await cb.message.edit_text(f"❌ 分析失敗：{e}", parse_mode="HTML")
        return

    await cb.message.edit_text(banner, parse_mode="HTML",
                                disable_web_page_preview=False,
                                reply_markup=_timeframe_keyboard(code))
```

- [ ] **Step 2: Add `/scan` to `tg_bot/handlers/watchlist.py`**

Append after `cmd_list`:

```python


@router.message(Command("scan"))
async def cmd_scan(msg: Message,
                   storage: Storage,
                   quantdinger,                          # QuantDingerClient
                   telegraph,                            # TelegraphClient
                   telegraph_author_name: str,
                   telegraph_author_url: str,
                   reuse_page: bool):
    import asyncio
    from tg_bot.handlers.analyze import run_analysis, _timeframe_keyboard
    from tg_bot.services.quantdinger import BackendError

    rows = storage.watchlist_list()
    if not rows:
        await msg.answer("📭 Watchlist 為空，沒東西可掃。", parse_mode="HTML")
        return

    await msg.answer(f"🔁 開始 /scan，共 {len(rows)} 檔...", parse_mode="HTML")

    for r in rows:
        code = r["code"]
        try:
            banner, _ = await run_analysis(
                code=code, name=r.get("name"), timeframe="1D",
                storage=storage, quantdinger=quantdinger, telegraph=telegraph,
                telegraph_author_name=telegraph_author_name,
                telegraph_author_url=telegraph_author_url,
                reuse_page=reuse_page,
            )
            await msg.answer(banner, parse_mode="HTML",
                             disable_web_page_preview=False,
                             reply_markup=_timeframe_keyboard(code))
        except BackendError as e:
            await msg.answer(f"❌ {code} 分析失敗：{e}", parse_mode="HTML")
        except Exception as e:
            await msg.answer(f"❌ {code} 異常：{type(e).__name__}: {e}",
                             parse_mode="HTML")
        await asyncio.sleep(2)
```

- [ ] **Step 3: Commit**

```bash
git add tg_bot/handlers/callbacks.py tg_bot/handlers/watchlist.py
git commit -m "feat(tg_bot): inline keyboard timeframe switch + /scan watchlist runner"
```

---

## Task 13: `bot.py` — entry point + dispatcher wiring

**Files:**
- Create: `tg_bot/bot.py`

- [ ] **Step 1: Implement `tg_bot/bot.py`**

```python
"""Bot entry point.

Wires everything: settings → storage → clients → dispatcher → polling.
All clients are passed to handlers via aiogram's `data` dict
(workflow_data mechanism), so handlers receive them as kwargs.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from tg_bot.config import Settings
from tg_bot.handlers import analyze, callbacks, help as help_h, watchlist
from tg_bot.middlewares.whitelist import WhitelistMiddleware
from tg_bot.services.quantdinger import QuantDingerClient
from tg_bot.services.storage import Storage
from tg_bot.services.telegraph import TelegraphClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tg_bot")


async def _bootstrap_telegraph(storage: Storage, settings: Settings) -> TelegraphClient:
    """Return a TelegraphClient with a usable access_token.

    Precedence: env var > sqlite cache > create new account.
    """
    if settings.telegraph_access_token:
        token = settings.telegraph_access_token
    else:
        acc = storage.telegraph_account_get()
        if acc:
            token = acc["access_token"]
        else:
            tmp = TelegraphClient()
            try:
                result = await tmp.create_account(
                    short_name="QuantDinger",
                    author_name=settings.telegraph_author_name,
                    author_url=settings.telegraph_author_url,
                )
            finally:
                await tmp.aclose()
            token = result["access_token"]
            storage.telegraph_account_set(
                access_token=token,
                short_name=result.get("short_name"),
                author_name=result.get("author_name"),
                author_url=result.get("author_url"),
                auth_url=result.get("auth_url"),
            )
            log.info("Telegraph account created. auth_url=%s",
                     result.get("auth_url"))
    return TelegraphClient(access_token=token)


async def main():
    settings = Settings()
    storage = Storage(settings.db_path)
    storage.init_schema()

    qd = QuantDingerClient(
        base_url=str(settings.quantdinger_api_url),
        username=settings.quantdinger_username,
        password=settings.quantdinger_password,
    )
    qd.set_initial_token(storage.auth_cache_get())
    try:
        await qd.login()
        storage.auth_cache_set(qd.token)
        log.info("Backend login OK")
    except Exception as e:
        log.error("Backend login failed at startup: %s", e)

    telegraph = await _bootstrap_telegraph(storage, settings)

    bot = Bot(token=settings.tg_bot_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Whitelist middleware on messages + callbacks
    mw = WhitelistMiddleware(allowed_group_ids=settings.whitelist_group_ids,
                             allowed_user_ids=settings.whitelist_user_ids)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)

    # Make services available to handlers as kwargs
    dp["storage"] = storage
    dp["quantdinger"] = qd
    dp["telegraph"] = telegraph
    dp["telegraph_author_name"] = settings.telegraph_author_name
    dp["telegraph_author_url"] = settings.telegraph_author_url
    dp["reuse_page"] = settings.telegraph_reuse_page

    dp.include_router(help_h.router)
    dp.include_router(analyze.router)
    dp.include_router(watchlist.router)
    dp.include_router(callbacks.router)

    log.info("Bot starting long polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await qd.aclose()
        await telegraph.aclose()
        storage.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify the module imports without runtime errors (no env set)**

Run: `cd tg_bot && python -c "import bot"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add tg_bot/bot.py
git commit -m "feat(tg_bot): bot.py entry point with full dispatcher wiring"
```

---

## Task 14: Dockerfile

**Files:**
- Create: `tg_bot/Dockerfile`

- [ ] **Step 1: Write `tg_bot/Dockerfile`**

```dockerfile
# Slim base, no extras
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Non-root user
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app && \
    mkdir -p /data && chown -R app:app /app /data

COPY --chown=app:app . /app

USER app

# Persistent SQLite lives here; mounted as docker volume in compose
VOLUME ["/data"]

# Run bot via module path so relative imports work
CMD ["python", "-u", "-m", "bot"]
```

Note: `python -m bot` requires `bot.py` at WORKDIR root and a top-level `__init__.py` is not needed for `-m` if invoked from the file. Confirmed: `python -m bot` from `/app` runs `/app/bot.py` as `__main__`. The internal imports `from tg_bot.xxx` won't work because there's no `tg_bot/` package inside the container — we need to adjust either the imports or the COPY layout.

- [ ] **Step 2: Fix import paths for in-container layout**

Two options. We pick option B (preserve `tg_bot` package name) so module paths match local dev exactly:

Replace the last two lines of Dockerfile with:

```dockerfile
# Mount the whole package one level up so `from tg_bot.x import y` resolves
WORKDIR /
COPY --chown=app:app . /tg_bot

USER app
VOLUME ["/data"]
ENV PYTHONPATH=/

CMD ["python", "-u", "-m", "tg_bot.bot"]
```

And earlier change `COPY requirements.txt` to:

```dockerfile
COPY tg_bot/requirements.txt /tg_bot/requirements.txt
RUN pip install -r /tg_bot/requirements.txt
```

So full Dockerfile becomes:

```dockerfile
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/

WORKDIR /

# Build context is repo root; this Dockerfile sits in tg_bot/ but the
# docker-compose `context:` is project root so `COPY tg_bot/...` works.
COPY tg_bot/requirements.txt /tg_bot/requirements.txt
RUN pip install -r /tg_bot/requirements.txt

RUN groupadd -r app && useradd -r -g app -d /tg_bot -s /sbin/nologin app && \
    mkdir -p /data && chown -R app:app /tg_bot /data

COPY --chown=app:app tg_bot/ /tg_bot/

USER app
VOLUME ["/data"]

CMD ["python", "-u", "-m", "tg_bot.bot"]
```

- [ ] **Step 3: Local build smoke test**

Run from project root:
```bash
docker build -f tg_bot/Dockerfile -t quantdinger-tg-bot:dev .
```
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add tg_bot/Dockerfile
git commit -m "feat(tg_bot): Dockerfile with non-root user and PYTHONPATH"
```

---

## Task 15: docker-compose integration

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Insert tg_bot service**

In `docker-compose.yml`, after the `frontend` service block (before the top-level `volumes:` key), add:

```yaml
  # ========================
  # Telegram Bot
  # ========================
  tg_bot:
    build:
      context: .
      dockerfile: tg_bot/Dockerfile
    container_name: quantdinger-tg-bot
    restart: unless-stopped
    depends_on:
      backend:
        condition: service_healthy
    environment:
      - TG_BOT_TOKEN=${TG_BOT_TOKEN}
      - WHITELIST_GROUP_IDS=${WHITELIST_GROUP_IDS}
      - WHITELIST_USER_IDS=${WHITELIST_USER_IDS}
      - QUANTDINGER_API_URL=${QUANTDINGER_API_URL:-http://backend:5000}
      - QUANTDINGER_USERNAME=${QUANTDINGER_USERNAME}
      - QUANTDINGER_PASSWORD=${QUANTDINGER_PASSWORD}
      - TELEGRAPH_ACCESS_TOKEN=${TELEGRAPH_ACCESS_TOKEN:-}
      - TELEGRAPH_AUTHOR_NAME=${TELEGRAPH_AUTHOR_NAME:-QuantDinger Bot}
      - TELEGRAPH_AUTHOR_URL=${TELEGRAPH_AUTHOR_URL:-}
      - TELEGRAPH_REUSE_PAGE=${TELEGRAPH_REUSE_PAGE:-false}
      - DB_PATH=/data/bot.db
      - TZ=${TZ:-Asia/Shanghai}
    volumes:
      - tg_bot_data:/data
    networks:
      - quantdinger-network
```

- [ ] **Step 2: Add tg_bot_data volume**

In the top-level `volumes:` section, add:

```yaml
  tg_bot_data:
    driver: local
```

So the final `volumes:` block looks like:

```yaml
volumes:
  postgres_data:
    driver: local
  backend_logs:
    driver: local
  backend_data:
    driver: local
  tg_bot_data:
    driver: local
```

- [ ] **Step 3: Validate compose syntax**

```bash
docker compose config > /dev/null
```
Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(tg_bot): add tg_bot service and volume to docker-compose"
```

---

## Task 16: `README.md`

**Files:**
- Create: `tg_bot/README.md`

- [ ] **Step 1: Write `tg_bot/README.md`**

```markdown
# QuantDinger Telegram Bot

Whitelist-only Telegram bot that exposes QuantDinger's homepage AI screening
(`/api/fast-analysis/analyze`) to a single Telegram group. Detailed reports
are published to Telegraph; the group only sees a concise banner + link.

A-share only (6-digit codes), e.g. `/ai 600519`.

## Commands

| Command | Purpose |
|---|---|
| `/ai <code>` | Run AI analysis on a 6-digit A-share code |
| `/watch <code>` | Add to group-shared watchlist |
| `/unwatch <code>` | Remove from watchlist |
| `/list` | Show watchlist |
| `/scan` | Run AI on every code in the watchlist |
| `/start` `/help` | Show help |

Inline keyboard on each result lets you re-run with `1H` / `4H` / `1W` / refresh.

## Setup

1. Create a bot via @BotFather → get `TG_BOT_TOKEN`.
2. Add the bot to your group → make it admin or at least allow it to read
   messages (`/setprivacy` → Disable).
3. Get your group's chat ID (forward any group message to @userinfobot, or
   use `getUpdates`). It will be a negative number like `-1001234567890`.
4. Get each member's TG user ID similarly.
5. Add these to project-root `.env`:
   ```
   TG_BOT_TOKEN=...
   WHITELIST_GROUP_IDS=-1001234567890
   WHITELIST_USER_IDS=111,222,333
   QUANTDINGER_USERNAME=quantdinger
   QUANTDINGER_PASSWORD=...
   TELEGRAPH_AUTHOR_NAME=QuantDinger Bot
   TELEGRAPH_AUTHOR_URL=https://t.me/yourgroup
   ```
6. Bring up:
   ```
   docker compose up -d --build tg_bot
   docker compose logs -f tg_bot
   ```

On first start the bot calls Telegraph `createAccount`, stores the
`access_token` in `/data/bot.db`, and logs the one-time `auth_url` —
**save this URL** if you want to edit pages from the Telegraph web UI later.

## Development

```bash
cd tg_bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v
```

## Architecture

See [the spec](../docs/superpowers/specs/2026-05-16-tg-bot-ai-screening-design.md).
```

- [ ] **Step 2: Commit**

```bash
git add tg_bot/README.md
git commit -m "docs(tg_bot): README with setup and command reference"
```

---

## Task 17: End-to-end smoke test (manual, not in test suite)

**Files:** none

This is operational verification, executed by the operator (you), not by an automated test.

- [ ] **Step 1: Set env vars in project-root `.env`** (per Task 16 README).

- [ ] **Step 2: Build and start**

```bash
docker compose up -d --build tg_bot
docker compose logs -f tg_bot
```

Expected log lines:
- `Backend login OK`
- `Telegraph account created. auth_url=...` (only first run) **or** silence (subsequent runs)
- `Bot starting long polling...`

Save the `auth_url` somewhere safe on first run.

- [ ] **Step 3: In the whitelisted group**

Send `/help` — expect command list reply within seconds.

- [ ] **Step 4: Run an analysis**

Send `/ai 600519`.
- Within 1 s: "🔍 正在分析 `600519`..."
- Within 30–90 s: that message is replaced with the banner including Telegraph link.
- Click Telegraph link → full report renders with all sections.
- Inline buttons: tap "切 4H" → message updates to "正在以 4H 周期分析..." then to the 4H banner.

- [ ] **Step 5: Test watchlist**

```
/watch 600519
/watch 000001
/list             → both codes shown
/scan             → two analyses come back over ~3 minutes
/unwatch 600519
/list             → only 000001 shown
```

- [ ] **Step 6: Test error handling**

- `/ai abc` → "❌ 代碼必須為 6 位數字 ..."
- `/ai 600519` from a private DM (not the group) → "本 bot 只在指定群組工作"
- From a non-whitelisted user in the whitelisted group → "你不在白名單..."
- (Optional) stop the backend container, run `/ai 600519` → "❌ 分析失敗：..." within timeout.

- [ ] **Step 7: Persistence**

```bash
docker compose restart tg_bot
docker compose logs tg_bot | head -20
```

Expected:
- `Backend login OK` (no re-bootstrap)
- No new `Telegraph account created` log
- `/list` still shows the codes from before restart

If all of the above pass, the MVP is shipped.

---

## Self-Review Notes

Run after the plan author finishes — no separate task.

- **Spec §3 architecture** → Tasks 13, 14, 15 (bot wiring + Dockerfile + compose)
- **Spec §4 commands** → Tasks 9, 10, 11, 12 (one handler each, /scan in 12)
- **Spec §5 output** → Tasks 4, 5 (page_builder + banner) and verified in Task 11 integration test
- **Spec §6 backend protocol** → Task 7 (login flow + 401 retry + sync analyze)
- **Spec §6.4 Telegraph protocol** → Task 8 + Task 13 bootstrap
- **Spec §7 SQLite 4 tables** → Task 3
- **Spec §8 file layout** → Task 1 scaffolding; per-file tasks own each file
- **Spec §9 env vars + compose** → Tasks 2, 14, 15
- **Spec §10 error handling matrix** → Coverage in Tasks 6 (whitelist), 7 (BackendError types), 10 (parse_code errors), 11 (TelegraphError swallow + BackendError surfacing), 12 (/scan continue-on-error)
- **Spec §11 testing** → Tasks 2, 3, 4, 5, 6, 7, 8, 10, 11 (unit tests where applicable; integration test in 17)
- **Spec §13 risks** → Backend 401 retry (Task 7), Telegraph fail degradation (Task 11), watchlist mutability (Task 3)
- **Spec §14 acceptance** → Task 17 steps 4–7 map 1:1 to the 8 acceptance items

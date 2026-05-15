# QuantDinger AI 篩選 Telegram Bot — 設計文件

- 日期：2026-05-16
- 作者：admin@fredyun.com
- 狀態：草案（待批准）

## 1. 背景與目標

QuantDinger 首頁的「AI 篩選 / AI 快速分析」功能（後端 `POST /api/fast-analysis/analyze`）會：

1. 並行採集多周期市場數據（價格、K 線、技術指標、宏觀、新聞、基本面、Crypto 衍生品）
2. 用強約束 prompt 呼叫一次 LLM，輸出結構化 JSON（決策、信心、入場/止損/止盈、三段分析、評分、風險）
3. 再用規則計算的客觀評分 + 多周期共識，校準 LLM 輸出
4. 把結果存入 `analysis_memory`，下次相似條件時可被檢索

本專案的目標是把這個功能透過 Telegram bot 暴露給一個小型白名單群組使用，**不重寫核心邏輯**，bot 純粹是個瘦的 HTTP 客戶端 + 訊息格式化層。

## 2. 範圍

### 包含
- 在 QuantDinger repo 加一個獨立的 `tg_bot/` 子專案
- 與既有 `quantdinger-backend` 同機部署，不同 Docker container，共享 `quantdinger-network`
- 命令：`/ai`、`/watch`、`/unwatch`、`/list`、`/scan`、`/help`
- 只支援 A 股（CNStock 市場），輸入 6 位數股票代碼
- TG `group_id` + `user_id` 雙重白名單
- 群共享 watchlist + 群共享後端 credits 池（不額外限流）
- 詳細多段訊息輸出（每次分析 4 條訊息）

### 不包含（後續可加）
- 定時自動推送（每日開盤前自動分析 watchlist）
- 多市場（Crypto、US Stock、Forex）
- 多語言（暫只繁中輸出；後端 `language` 參數固定 `zh-TW`）
- 用戶各自 watchlist
- 每用戶限流 / credits 隔離
- 圖表 / 截圖
- Webhook 模式（用 long polling 即可）

## 3. 架構

```
        ┌──────────────┐
        │  Telegram    │
        │   群組聊天    │
        └──────┬───────┘
               │ long poll
               ▼
   ┌──────────────────────┐        Docker network: quantdinger-network
   │   tg_bot container   │ ───────────────────────────────────┐
   │ (Python 3.11 +       │                                    │
   │  aiogram v3 + httpx) │                                    ▼
   │                      │           ┌──────────────────────────────┐
   │  /data/watchlist.db  │           │ quantdinger-backend (Flask)  │
   │  (SQLite, mounted)   │           │   :5000                      │
   └──────────────────────┘           │   POST /api/auth/login       │
                                      │   POST /api/fast-analysis/   │
                                      │        analyze               │
                                      │   GET  /api/fast-analysis/   │
                                      │        history               │
                                      └──────────────────────────────┘
```

### 為什麼是這個架構
- **同機不同 container**：與 backend 隔離部署，崩了不影響主服務；走 docker 內網不必對外開 port
- **long polling**：不需要對外 HTTPS / 反代，最簡單
- **單獨 SQLite**：watchlist 只是 1~50 條記錄的列表，沒必要碰 postgres
- **HTTP 客戶端薄殼**：分析邏輯、LLM、credits、memory 全部沿用 backend，bot 永遠跟著 backend 升級

## 4. 命令詳細

| 命令 | 形式 | 行為 |
|---|---|---|
| `/start` `/help` | 直接呼叫 | 回機器人簡介 + 命令列表 |
| `/ai <code>` | `/ai 600519` 或群裡 `/ai@BotName 600519` | 即時對該 A 股執行 AI 分析，回 4 條訊息 |
| `/watch <code>` | 同上 | 加入群共享 watchlist；如已在列表回提示 |
| `/unwatch <code>` | 同上 | 從 watchlist 移除 |
| `/list` | 無參數 | 列出群共享 watchlist（含每檔股票名稱） |
| `/scan` | 無參數 | 對 watchlist 中每一檔依序呼叫 AI 分析；每個結果 4 條訊息發出，分析間用 2 秒間隔避免 backend 過載 |

**輸入驗證**：所有 `<code>` 必須是 6 位純數字；否則回 "請輸入 6 位 A 股代碼，例如 /ai 600519"。

**白名單檢查**：
- 中間件先檢查 `chat.id ∈ WHITELIST_GROUP_IDS` 且 `user.id ∈ WHITELIST_USER_IDS`
- 失敗：靜默忽略（不回覆，避免 bot 在非白名單群組刷屏）
- 私聊（非群組）：一律忽略

## 5. 輸出格式（每次 /ai 出 4 條訊息）

用 HTML parse_mode（TG 對 HTML 比 Markdown 容錯好）。

### 訊息 1 — Banner（簡潔可一眼看完）
```
📊 <b>中國中車 (601766)</b>
━━━━━━━━━━━━━━━━━━
🟢 <b>BUY</b> · 信心 78%

💰 入場：¥6.85
🛡️ 止損：¥6.52  (-4.8%)
🎯 止盈：¥7.43  (+8.5%)
📦 倉位：30%  ⏱ 中期
━━━━━━━━━━━━━━━━━━
數據時間：2026-05-16 14:32
模型：moonshot-v1-8k
```

### 訊息 2 — 三段分析（LLM 原文）
```
📈 <b>技術分析</b>
（LLM analysis.technical 全文）

💼 <b>基本面</b>
（LLM analysis.fundamental 全文）

📰 <b>市場情緒</b>
（LLM analysis.sentiment 全文）
```

### 訊息 3 — 數據面
```
🕐 <b>多周期趨勢</b>
~24h：看多（中）
~3d：看多（強）
~1w：看多（中）
~1m：看多（中）

📊 <b>客觀評分</b>
技術面：72/100
基本面：65/100
情緒面：58/100
宏觀面：60/100
總分：+38（中等利多）

📚 <b>歷史類似模式</b>
- 2026-04-10 BUY @ ¥6.45（正確，+5.2%）
- 2026-03-22 BUY @ ¥6.30（正確，+3.1%）
- 2026-02-15 HOLD @ ¥6.10（—）
```

如果 `analysis_memory` 沒有類似模式，這段隱藏。

### 訊息 4 — 風險清單 + 按鈕
```
⚠️ <b>主要風險</b>
1. 成交量持續萎縮，缺乏買盤跟進
2. 政策面不確定性

💡 <b>關鍵理由</b>
1. MACD 在零軸下方金叉重現
2. 公司財報超預期
3. 行業景氣度回升

[切 1H] [切 4H] [切 1W] [刷新]
```

按鈕為 Inline Keyboard，callback_data 含 `code` 和 `timeframe`，按下時觸發新的 /ai 流程。

### 訊息分段為什麼是 4 條
TG 訊息 4096 字元限制；分 4 條讓用戶在手機上滾動方便，也避免單條超限被截斷。

## 6. 與 Backend 的協議

### 6.1 鑒權

- 環境變數：`QUANTDINGER_USERNAME`、`QUANTDINGER_PASSWORD`
- bot 啟動時 `POST /api/auth/login`，body `{"username": ..., "password": ...}`，回 `{code:1, data:{token, userinfo}}`
- token 緩存到內存；每次 backend 請求帶 `Authorization: Bearer <token>`
- 任一 API 回 401 → 自動 re-login 一次後重試；二次仍 401 → 給群裡提示 "後端登入失敗，請聯絡管理員"

### 6.2 分析呼叫流程

分析耗時 30–60 秒，群組訊息不能阻塞太久。採用同步模式 + 進度提示：

```
1. bot 收到 /ai 600519
2. bot 立即回 "🔍 正在分析 600519...（約 30-90 秒）"（記下 message_id）
3. bot async httpx POST /api/fast-analysis/analyze
   body: {
     "market": "CNStock",
     "symbol": "600519",
     "language": "zh-TW",
     "timeframe": "1D"
   }
   timeout: 150 秒
   回 { code:1, data: {decision, confidence, summary, analysis, entry_price,
                       stop_loss, take_profit, position_size_pct, key_reasons,
                       risks, objective_score, consensus, trend_outlook, ...} }
4. 拿到結果後 editMessageText 把「正在分析...」改為訊息 1 banner
5. 接著 sendMessage 發訊息 2、3、4
6. 超時 / 異常 → editMessageText 為 "❌ 分析失敗：{原因}"
```

**為什麼用同步模式而非 async_submit**：
- bot 與 backend 在同一 Docker 網路，無 nginx / 雲商 proxy timeout 困擾
- async_submit 需要輪詢 history 拿結果，多一輪複雜度
- aiogram 是 async；httpx async 等 60 秒不阻塞其他 update handler
- backend 本身對重複請求有 90 秒 inflight 鎖（`_acquire_inflight`），多人同時 /ai 同一檔會回 429，bot 解析後告知群裡

**並發**：aiogram 每個 update handler 用 asyncio task，bot 同時能處理多檔分析；單一 httpx client 已可 keep-alive。

### 6.3 /scan 流程
- 取得 watchlist 後依序對每檔 code 跑一次上面的流程
- 每檔之間 sleep 2 秒
- 一條分析（4 訊息）失敗不影響下一檔

## 7. 資料儲存

### SQLite schema（`/data/watchlist.db`）

```sql
CREATE TABLE IF NOT EXISTS watchlist (
    code        TEXT PRIMARY KEY,            -- 6 位 A 股代碼
    name        TEXT,                         -- 中文名（從 /api/markets/symbols 或快速分析回傳填）
    added_by    INTEGER NOT NULL,             -- TG user_id
    added_at    TEXT NOT NULL                 -- ISO datetime
);

CREATE TABLE IF NOT EXISTS auth_cache (
    id         INTEGER PRIMARY KEY CHECK (id = 1),  -- 單行
    token      TEXT NOT NULL,
    saved_at   TEXT NOT NULL
);
```

`auth_cache` 表雖然多此一舉（內存夠用），但讓 bot 重啟不必馬上 re-login，能稍微減少對 backend `/auth/login` 的呼叫頻次。

## 8. 文件結構

```
tg_bot/
├── bot.py                       # aiogram Dispatcher 入口
├── config.py                    # 從 env 讀取所有設定
├── middlewares/
│   ├── __init__.py
│   └── whitelist.py             # group_id + user_id 雙重白名單
├── handlers/
│   ├── __init__.py
│   ├── analyze.py               # /ai
│   ├── watchlist.py             # /watch /unwatch /list /scan
│   ├── help.py                  # /start /help
│   └── callbacks.py             # inline keyboard callback（切周期、刷新）
├── services/
│   ├── __init__.py
│   ├── quantdinger.py           # HTTP client (login, analyze, poll, history)
│   ├── storage.py               # SQLite watchlist + auth_cache
│   └── formatter.py             # backend JSON → 4 段 HTML + 按鈕
├── data/                        # docker volume mount 點
│   └── .gitkeep
├── tests/
│   ├── test_formatter.py        # 給 fake JSON，驗證 HTML 輸出正確
│   └── test_storage.py          # watchlist CRUD
├── Dockerfile
├── requirements.txt
├── .dockerignore
└── README.md
```

### 模組依賴方向
- `bot.py` → middlewares + handlers
- handlers → services
- services 互不依賴（formatter 不需要 quantdinger，storage 不需要 quantdinger）
- 任一模組可獨立單測

## 9. 部署

### 9.1 環境變數（新增 `.env` 區段）

```
# === Telegram Bot ===
TG_BOT_TOKEN=123456:ABC-DEF...                # @BotFather 給的
WHITELIST_GROUP_IDS=-1001234567890            # 逗號分隔；群組 id 是負數
WHITELIST_USER_IDS=111111,222222,333333       # 逗號分隔 TG user id

# === Bot 連 QuantDinger Backend ===
QUANTDINGER_API_URL=http://backend:5000        # 同 compose 網路內名稱
QUANTDINGER_USERNAME=quantdinger
QUANTDINGER_PASSWORD=123456
```

### 9.2 docker-compose.yml 新增 service

```yaml
  # ========================
  # Telegram Bot
  # ========================
  tg_bot:
    build:
      context: ./tg_bot
      dockerfile: Dockerfile
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
      - TZ=${TZ:-Asia/Shanghai}
    volumes:
      - tg_bot_data:/data
    networks:
      - quantdinger-network
```

並在 `volumes:` 區段加：
```yaml
volumes:
  ...
  tg_bot_data:
    driver: local
```

### 9.3 Dockerfile（要點）

- Base：`python:3.11-slim`
- 安裝 `aiogram>=3.4`, `httpx`, `pydantic`, `python-dotenv`
- COPY 後 `CMD ["python", "-u", "bot.py"]`
- 不裸跑 root；建立 `appuser`

## 10. 錯誤處理

| 情境 | 行為 |
|---|---|
| 非白名單群組裡 @ bot | 靜默忽略（不發任何訊息） |
| 非白名單用戶在白名單群組裡 /ai | 回 "你不在白名單，找管理員加你" |
| 私聊 bot | 回 "本 bot 只在指定群組工作" |
| 輸入非 6 位數字 | "請輸入 6 位 A 股代碼，例如 /ai 600519" |
| backend 連不上 | "後端服務不可達，請稍後再試" |
| backend 401 二次失敗 | "後端登入失敗，請聯絡管理員" |
| 分析超時（>120s） | editMessage 為 "❌ 分析超時，請稍後再試" |
| 分析回 error | editMessage 為 "❌ 分析失敗：{error msg}" |
| /scan 中某檔失敗 | 對該檔輸出錯誤訊息，繼續下一檔 |
| credits 不足 | 解析回應的 `{required, current, shortage}`，群組裡明示 "credits 不足，需 X 當前 Y" |

## 11. 測試策略

- **單測**：
  - `test_formatter.py`：餵 fake JSON（從真實 /analyze 抓一份 fixture），驗證 4 條 HTML 文字結構符合預期、特殊字元被 escape
  - `test_storage.py`：watchlist add/remove/list 邏輯
  - `test_whitelist.py`：白名單中間件對各種 update 類型的判斷
- **整合測試**：手動，在測試群組裡跑 `/ai 600519` 驗證端到端
- **不做**：對 backend API 的 mock 測試（依賴太多，容易 drift；用真實 backend 整測）

## 12. 後續可擴展（不在本次 MVP）

1. APScheduler 定時跨 watchlist push 分析（每日開盤前 9:00、收盤後 15:30）
2. 接 `/api/fast-analysis/feedback` — 給每條分析訊息加 👍👎 按鈕，使用者回饋寫入 backend
3. 支援其他市場：`/ai BTC` 自動辨識為 Crypto；`/ai AAPL` 辨識為 USStock
4. 多語言：按用戶 TG language code 傳 `zh-CN/zh-TW/en-US`
5. 圖表：呼叫 backend kline + matplotlib 出 PNG 附加在訊息 3
6. 每用戶 credits 隔離：在 backend 加「子帳號 / API key」端點，每個 TG user 對應一個 key

## 13. 風險與緩解

| 風險 | 緩解 |
|---|---|
| backend 升級導致 `/analyze` 回傳結構變動 | formatter 對所有欄位用 `.get()` + 預設值；fixture 測試會抓到結構斷裂 |
| TG bot token 洩漏 | `.env` 不入版本控制；compose 從 host env 注入 |
| 群組裡多人同時 /ai 同一檔 | backend 已有 90 秒 inflight 鎖，會回 429；bot 解析後回 "已有人在分析此檔，請稍候" |
| SQLite 損壞 | watchlist 是 best-effort 資料；docker volume 備份即可 |
| 群組被陌生人加入機器人 | `WHITELIST_GROUP_IDS` 嚴格白名單，未列入的群一律不回應 |

## 14. 驗收標準

MVP 完成需滿足：

1. 在白名單群組裡發 `/ai 600519`，30–90 秒內收到 4 條訊息，內容齊全
2. `/watch 600519` 後 `/list` 看到該檔；`/unwatch 600519` 後消失
3. `/scan` 對 3 檔股票按順序輸出 3 組（共 12 條）訊息
4. 非白名單群組裡發 `/ai` 完全沒反應
5. backend 重啟後 bot 自動 re-login 並能繼續工作
6. bot 容器重啟後 watchlist 不丟失

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

本專案的目標是把這個功能透過 Telegram bot 暴露給一個小型白名單群組使用，**不重寫核心邏輯**，bot 純粹是個瘦的 HTTP 客戶端 + 訊息格式化層。詳細報告承載在 Telegraph 上，TG 群裡只發精簡 banner + 連結。

## 2. 範圍

### 包含
- 在 QuantDinger repo 加一個獨立的 `tg_bot/` 子專案
- 與既有 `quantdinger-backend` 同機部署，不同 Docker container，共享 `quantdinger-network`
- 命令：`/ai`、`/watch`、`/unwatch`、`/list`、`/scan`、`/help`
- 只支援 A 股（CNStock 市場），輸入 6 位數股票代碼
- TG `group_id` + `user_id` 雙重白名單
- 群共享 watchlist + 群共享後端 credits 池（不額外限流）
- **詳細報告承載在 Telegraph 公開頁**；TG 訊息只發精簡 banner + 連結
- 啟動自動 createAccount 拿 Telegraph access_token；page path 緩存到 SQLite 供日後 editPage

### 不包含（後續可加）
- 定時自動推送（每日開盤前自動分析 watchlist）
- 多市場（Crypto、US Stock、Forex）
- 多語言（暫只繁中輸出；後端 `language` 參數固定 `zh-TW`）
- 用戶各自 watchlist
- 每用戶限流 / credits 隔離
- 圖表 / 截圖（Telegraph 支援 uploadFile，可日後加 K 線 PNG）
- Webhook 模式（用 long polling 即可）
- Telegraph 失敗的「降級成多條 TG 訊息」備援（群友都能訪問 Telegraph，不做）

## 3. 架構

```
        ┌──────────────┐
        │  Telegram    │
        │   群組聊天    │◄─── banner + Telegraph 連結
        └──────┬───────┘
               │ long poll
               ▼
   ┌──────────────────────┐        Docker network: quantdinger-network
   │   tg_bot container   │ ───────────────────────────────────┐
   │ (Python 3.11 +       │                                    │
   │  aiogram v3 + httpx) │                                    ▼
   │                      │           ┌──────────────────────────────┐
   │  /data/bot.db        │           │ quantdinger-backend (Flask)  │
   │  (watchlist +        │           │   :5000                      │
   │   auth_cache +       │           │   POST /api/auth/login       │
   │   telegraph_account +│           │   POST /api/fast-analysis/   │
   │   telegraph_pages)   │           │        analyze               │
   └────────┬─────────────┘           └──────────────────────────────┘
            │
            │ HTTPS
            ▼
   ┌──────────────────────┐
   │  api.telegra.ph      │ ← createAccount / createPage / editPage
   │  (公開頁面，無權限)   │
   └──────────────────────┘
```

### 為什麼是這個架構
- **同機不同 container**：與 backend 隔離部署，崩了不影響主服務；走 docker 內網不必對外開 port
- **long polling**：不需要對外 HTTPS / 反代，最簡單
- **單獨 SQLite**：watchlist 只是 1~50 條記錄的列表，沒必要碰 postgres
- **HTTP 客戶端薄殼**：分析邏輯、LLM、credits、memory 全部沿用 backend，bot 永遠跟著 backend 升級
- **Telegraph 承載詳細報告**：群組噪音降到一條訊息；報告可分享、可存檔；自動 createAccount 零配置；page path 緩存可日後 editPage（同一檔股票重跑 /ai 時更新而非新建頁）

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

## 5. 輸出格式

### 5.1 TG 端 — 一條精簡 banner

用 HTML parse_mode。可一眼掃完。

```
📊 <b>中國中車 (601766)</b>
━━━━━━━━━━━━━━━━━━
🟢 <b>BUY</b> · 信心 78%

💰 入場：¥6.85
🛡️ 止損：¥6.52  (-4.8%)
🎯 止盈：¥7.43  (+8.5%)
📦 倉位：30%  ⏱ 中期

📝 <b>摘要</b>：(LLM summary，限 200 字)

🔗 <a href="https://telegra.ph/600519-05-16">📑 完整分析報告 →</a>

<i>數據時間：2026-05-16 14:32 · 模型：moonshot-v1-8k</i>
[切 1H] [切 4H] [切 1W] [刷新]
```

Inline keyboard 按鈕，callback_data 含 `code` 和 `timeframe`，按下時觸發新的 /ai 流程，會新建一個 Telegraph 頁（或 editPage 同一頁，視 §6.4 策略）。

### 5.2 Telegraph 頁面結構

Title 格式：`{股票名} ({code}) - {decision} - {YYYY-MM-DD HH:mm}`
例：`中國中車 (601766) - BUY - 2026-05-16 14:32`

頁面內容（從上到下）：

```
[h3]  📊 決策摘要
[p]   BUY · 信心 78% · 建議倉位 30% · 中期持有
[p]   入場 ¥6.85  /  止損 ¥6.52 (-4.8%)  /  止盈 ¥7.43 (+8.5%)

[hr]

[h3]  📈 技術分析
[p]   (LLM analysis.technical 全文)

[h3]  💼 基本面
[p]   (LLM analysis.fundamental 全文)

[h3]  📰 市場情緒
[p]   (LLM analysis.sentiment 全文)

[hr]

[h3]  🕐 多周期趨勢
[ul]
  - ~24h：看多（中）
  - ~3d：看多（強）
  - ~1w：看多（中）
  - ~1m：看多（中）

[h3]  📊 客觀評分（規則計算）
[ul]
  - 技術面：72/100
  - 基本面：65/100
  - 情緒面：58/100
  - 宏觀面：60/100
  - 總分：+38（中等利多）

[h3]  📚 歷史類似模式
[ul]
  - 2026-04-10 BUY @ ¥6.45（正確，+5.2%）
  - ...
（無資料時隱藏整段）

[hr]

[h3]  💡 關鍵理由
[ol]
  1. MACD 在零軸下方金叉重現
  2. 公司財報超預期
  3. 行業景氣度回升

[h3]  ⚠️ 主要風險
[ol]
  1. 成交量持續萎縮，缺乏買盤跟進
  2. 政策面不確定性

[hr]

[p]   <i>由 QuantDinger AI 生成 · 不構成投資建議 · 模型 moonshot-v1-8k</i>
```

Telegraph 的 Node 樹格式範例：
```json
[
  {"tag": "h3", "children": ["📊 決策摘要"]},
  {"tag": "p", "children": ["BUY · 信心 78% ..."]},
  {"tag": "hr"},
  {"tag": "h3", "children": ["📈 技術分析"]},
  {"tag": "p", "children": ["(技術分析文字)"]},
  {"tag": "ul", "children": [
    {"tag": "li", "children": ["~24h：看多（中）"]},
    {"tag": "li", "children": ["~3d：看多（強）"]}
  ]}
]
```

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
- 一檔分析（banner + Telegraph 頁）失敗不影響下一檔

### 6.4 Telegraph 整合

**API 端點**：`https://api.telegra.ph/<method>`，全部 GET/POST 表單，不需要 OAuth。

**啟動時 access_token 取得**：
```
1. bot 啟動，從 SQLite telegraph_account 表讀 access_token
2. 若無記錄：
   - POST https://api.telegra.ph/createAccount
     form: { short_name: "QuantDinger",
             author_name: TELEGRAPH_AUTHOR_NAME,
             author_url:  TELEGRAPH_AUTHOR_URL }
   - 回 { ok: true, result: { access_token, auth_url, short_name, ... } }
   - 寫入 SQLite
3. 若有記錄：直接用
4. 若 env 設了 TELEGRAPH_ACCESS_TOKEN 覆寫，則優先用 env 那個
```

**createPage 呼叫**：
```
POST https://api.telegra.ph/createPage
form: {
  access_token: <cached>,
  title: "中國中車 (601766) - BUY - 2026-05-16 14:32",   # 最長 256 字
  author_name: TELEGRAPH_AUTHOR_NAME,
  author_url:  TELEGRAPH_AUTHOR_URL,
  content: <Node 樹的 JSON 字串>,                         # 64 KB 上限
  return_content: false
}
回 { ok: true, result: { path, url, ... } }
```

**editPage 策略**：每次 /ai 同一個 code 是否複用前一個 page？
- **預設 false（每次新建 page）**：保留歷史軌跡；同一檔多次分析在 telegraph_pages 表都有記錄；最新一條供 banner 連結
- 後續可加 env `TELEGRAPH_REUSE_PAGE=true` 改成 editPage 同一頁，省連結數但會覆蓋歷史

**page 緩存**：每次 createPage 成功後，寫入 telegraph_pages 表（memory_id, path, url, symbol, created_at），方便日後 /history 命令快速查歷史 page。

**失敗處理**：
- API 回 `{ok: false, error: ...}` → 重試 1 次（exponential backoff 1s）
- 二次失敗 → editMessageText 為 "🟢 BUY · 信心 78% ...（簡 banner）⚠️ 詳細報告生成失敗"
- access_token 失效（極少見） → 自動重新 createAccount

**Telegraph 限制**：
- title ≤ 256 字元
- author_name ≤ 128 字元
- content ≤ 64 KB（折合約 2 萬中文字，遠超我們需要）
- 速率限制官方未公開，實測幾秒一頁無壓力

## 7. 資料儲存

### SQLite schema（`/data/bot.db`）

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

CREATE TABLE IF NOT EXISTS telegraph_account (
    id           INTEGER PRIMARY KEY CHECK (id = 1),  -- 單行
    access_token TEXT NOT NULL,
    short_name   TEXT,
    author_name  TEXT,
    author_url   TEXT,
    auth_url     TEXT,                                -- Telegraph 提供的後台網址（一次性）
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegraph_pages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL,
    path       TEXT NOT NULL UNIQUE,                  -- telegra.ph 的 path 段
    url        TEXT NOT NULL,
    title      TEXT,
    timeframe  TEXT,                                  -- 該頁對應的分析周期
    decision   TEXT,                                  -- BUY/SELL/HOLD
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telegraph_pages_code_time
    ON telegraph_pages(code, created_at DESC);
```

- `auth_cache`：讓 bot 重啟不必馬上 re-login backend
- `telegraph_account`：access_token 永不過期但僅此一份，必須持久化否則重啟後失去所有以前頁面的編輯權
- `telegraph_pages`：每次 createPage 寫一筆，供日後 history 查詢或 editPage 復用

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
│   ├── quantdinger.py           # HTTP client (login, analyze, history)
│   ├── storage.py               # SQLite (watchlist + auth_cache + telegraph_*)
│   ├── telegraph.py             # Telegraph API client (createAccount / createPage / editPage)
│   ├── page_builder.py          # backend JSON → Telegraph Node 樹
│   └── banner.py                # backend JSON → TG banner HTML（含 Telegraph 連結）
├── data/                        # docker volume mount 點
│   └── .gitkeep
├── tests/
│   ├── test_banner.py           # 給 fake JSON，驗證 banner HTML 正確
│   ├── test_page_builder.py     # 給 fake JSON，驗證 Node 樹結構合法且完整
│   └── test_storage.py          # 各表 CRUD
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

# === Telegraph 報告承載 ===
TELEGRAPH_ACCESS_TOKEN=                       # 留空則首次啟動自動 createAccount 並寫入 SQLite
TELEGRAPH_AUTHOR_NAME=QuantDinger Bot
TELEGRAPH_AUTHOR_URL=https://t.me/yourgroup   # 可空；點 author 跳到群連結
TELEGRAPH_REUSE_PAGE=false                    # true 則同一 code 重跑時 editPage 而非新建
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
      - TELEGRAPH_ACCESS_TOKEN=${TELEGRAPH_ACCESS_TOKEN:-}
      - TELEGRAPH_AUTHOR_NAME=${TELEGRAPH_AUTHOR_NAME:-QuantDinger Bot}
      - TELEGRAPH_AUTHOR_URL=${TELEGRAPH_AUTHOR_URL:-}
      - TELEGRAPH_REUSE_PAGE=${TELEGRAPH_REUSE_PAGE:-false}
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
| Telegraph createPage 失敗 | 重試 1 次；仍失敗 → banner 末尾改為 "⚠️ 詳細報告生成失敗" 並輸出 LLM summary 全文 |
| Telegraph access_token 失效 | 自動 createAccount 取新 token 並覆寫 telegraph_account 表，記錄 warn 日誌 |
| Telegraph 內容超 64 KB（極端情況） | 把 analysis 三段做 1500 字截斷 + 末尾加 "...(報告過長已截斷)" |

## 11. 測試策略

- **單測**：
  - `test_banner.py`：餵 fake JSON（從真實 /analyze 抓一份 fixture），驗證 banner HTML 結構正確、含 Telegraph 連結、特殊字元被 escape
  - `test_page_builder.py`：驗證 Node 樹結構符合 Telegraph 規範（tag 列舉、children 為 list、無禁用屬性）；驗證所有欄位都被渲染
  - `test_storage.py`：所有 4 張表的 CRUD（watchlist / auth_cache / telegraph_account / telegraph_pages）
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
| Telegraph 是公開頁面，URL 可被搜尋 | URL 含時間戳難猜，但仍是公開；分析觀點外洩可接受（個股技術分析非機密）；若日後需保密改自架頁 |
| Telegraph API 偶發不可用 | 重試 + 降級為 banner only；不阻斷後續分析 |

## 14. 驗收標準

MVP 完成需滿足：

1. 在白名單群組裡發 `/ai 600519`，30–90 秒內收到 1 條 banner 訊息，含可點的 Telegraph 連結
2. 點 Telegraph 連結後在瀏覽器看到完整報告，含三段分析、多周期、評分、風險，排版正確
3. `/watch 600519` 後 `/list` 看到該檔；`/unwatch 600519` 後消失
4. `/scan` 對 3 檔股票按順序輸出 3 條 banner（每條都有獨立 Telegraph 連結）
5. 非白名單群組裡發 `/ai` 完全沒反應
6. backend 重啟後 bot 自動 re-login 並能繼續工作
7. bot 容器重啟後 watchlist 不丟失；Telegraph access_token 不丟失（不會重新 createAccount）
8. 模擬 Telegraph API 失敗（斷網或假 token），banner 仍正確發送並提示「詳細報告生成失敗」

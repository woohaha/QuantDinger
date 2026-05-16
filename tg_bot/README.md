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

If Python isn't installed locally, use a one-off Docker container instead
(from the project root):

```bash
docker run --rm -v "$(pwd):/app" -w /app/tg_bot \
  qd-tg-bot-test:latest python -m pytest -v
```

## Architecture

See the spec at
[`docs/superpowers/specs/2026-05-16-tg-bot-ai-screening-design.md`](../docs/superpowers/specs/2026-05-16-tg-bot-ai-screening-design.md)
and the implementation plan at
[`docs/superpowers/plans/2026-05-16-tg-bot-ai-screening.md`](../docs/superpowers/plans/2026-05-16-tg-bot-ai-screening.md).

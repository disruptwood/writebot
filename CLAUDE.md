# WriteBot — Daily Writing Channel Bot

## What is this
Telegram bot for managing a private daily writing channel. Tracks who posts, counts streaks, posts daily summaries, and lets admins manage inactive members.

## Architecture
- **Bot**: Python 3.12, aiogram 3.x (webhook mode), aiohttp server
- **DB**: SQLite via aiosqlite, file at `data/writebot.db`
- **Scheduler**: asyncio background task for daily summaries
- **CI/CD**: GitHub Actions → GCE e2-micro VM

## Project Structure
```
writebot/
  bot/
    __init__.py
    __main__.py         — entry point: python -m bot
    main.py             — aiohttp app, webhook, scheduler setup
    config.py           — env vars, UI strings (Russian)
    handlers/
      channel.py        — channel_post handler (track daily writes)
      group.py          — discussion group commands (/stats, /streak, etc.)
      private.py        — /start, /mystats in DM
      admin.py          — admin commands (/addadmin, /kick_inactive)
      membership.py     — join request + member status lifecycle
    db/
      models.py         — SQLite schema init + migrations
      queries.py        — all DB queries (parameterized)
    services/
      streaks.py        — pure streak calculation (testable, no I/O)
      scheduler.py      — evening warnings + midnight enforcement loop
      enforcement.py    — compliance rules (grace period, kick logic)
      channel_members.py — member promotion, invite links, formatting
  tests/
    conftest.py                  — fixtures (temp DB, Telegram mock factories)
    test_streaks.py              — unit: streak calculation logic
    test_enforcement.py          — unit: compliance rules (missing, kick eligibility)
    test_queries.py              — integration: all DB queries
    test_channel_handler.py      — handler: channel post tracking with mocked Telegram
    test_group_handler.py        — handler: /stats, /missing, /streak, /leaderboard
    test_private_handler.py      — handler: /start, /mystats
    test_admin_handler.py        — handler: /addadmin, /removeadmin, /invite_link
    test_membership_handler.py   — handler: join requests, member status changes
    test_channel_members_service.py — service: promotion, invite links, sync
    test_scheduler.py            — unit: job scheduling logic (monkeypatched)
    test_scheduler_full.py       — integration: warnings + kicks with real DB
  .github/workflows/
    ci.yml              — lint + test on push/PR
    deploy.yml          — deploy to GCE on push to main
```

## Commands
### Discussion group commands (anyone)
- `/stats` — today's writers count and names
- `/missing` — who hasn't written today
- `/streak` — your current streak
- `/leaderboard` — top streaks

### Admin commands (discussion group)
- `/addadmin` — reply to a message to make user admin
- `/removeadmin` — reply to remove admin
- `/kick_inactive [days]` — list inactive members (default 7 days)
- `/kick_inactive [days] confirm` — actually kick them

### Private commands
- `/start` — welcome message
- `/mystats` — personal streak

## DB Schema
- `admins`: bot-level admins (not Telegram admins)
- `channel_posts`: raw log of every channel post
- `daily_participation`: one row per user per day (aggregated)
- `streaks`: cached current/longest streak per user
- `members`: tracked channel members (with status lifecycle: pending → active → left/kicked)
- `bot_state`: key-value store for scheduler state and cached data
- `member_events`: audit log of all member status changes

## Environment variables (.env)
```
BOT_TOKEN=...
CHANNEL_ID=-100...          # private channel ID
DISCUSSION_GROUP_ID=-100... # linked discussion group ID
WEBAPP_URL=https://your-domain.example
DB_PATH=data/writebot.db
PORT=8080
TZ=Asia/Jerusalem
DAILY_SUMMARY_HOUR=23
INITIAL_ADMIN_ID=0          # your Telegram user ID for bootstrap
```

## Running locally
```bash
cp .env.example .env
# Edit .env with real values
pip install -r requirements.txt
python -m bot
```

## Running tests
```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

### Test architecture
Tests use **mock Telegram objects** so the full bot logic can be tested without
a real Telegram account or network. Key design:

- `conftest.py` provides factories: `make_user()`, `make_message()`, `make_bot()`,
  `make_chat()`, `make_join_request()`, `make_chat_member_updated()`
- Each test gets a **fresh temporary SQLite DB** (via `setup_db` auto-fixture)
- Handlers are called directly (not through aiogram dispatcher), with mock
  `message.answer()` / `bot.send_message()` to verify responses
- No network calls — all Bot API methods are `AsyncMock`

### What's covered (115 tests)
| Area | Tests | What's verified |
|------|-------|-----------------|
| Streak calculation | 12 | Consecutive days, gaps, duplicates, edge cases |
| DB queries | 15 | CRUD for admins, posts, members, streaks, state |
| Enforcement rules | 8 | Missing today, grace period, kick eligibility |
| Channel post handler | 7 | Post tracking, author resolution, wrong channel, bots |
| Group commands | 9 | /stats, /missing, /streak, /leaderboard |
| Private commands | 3 | /start, /mystats |
| Admin commands | 7 | /addadmin, /removeadmin, /invite_link, bootstrap |
| Membership handler | 7 | Join requests, joins, leaves, kicks, edge cases |
| Channel members service | 11 | Formatting, promotion, sync, invite links |
| Scheduler | 5 | Job timing, warnings, enforcement with real DB |

## Key behaviors
- Bot must be **admin** in both channel and discussion group
- Channel posts are tracked via `channel_post` updates (not `message`)
- Anonymous "post as channel" posts are skipped
- Streaks are calculated in configured timezone (default: Asia/Jerusalem)
- Daily summary posts at configured hour to discussion group
- First admin is bootstrapped via `INITIAL_ADMIN_ID` env var

## Deploy
- GCE e2-micro (free tier): 2 vCPU burst, 1 GB RAM — more than enough
- GitHub Actions deploys on push to main
- Secrets needed: `GCP_SA_KEY`, `GCE_VM_NAME`, `GCE_VM_ZONE`, `GCP_PROJECT_ID`, `GCE_USER`

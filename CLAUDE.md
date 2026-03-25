# WriteBot — Daily Writing Channel Bot

## What is this
Telegram bot for managing **multiple** private daily writing channels. Tracks who posts, counts streaks, posts daily summaries, and lets admins manage inactive members. Each channel is fully independent (separate members, streaks, enforcement).

## Multi-channel architecture
The bot serves multiple channels simultaneously via a single bot instance and single SQLite DB. Data is partitioned by `channel_id` in all relevant tables.

### Channel configuration
Channels are defined via `CHANNELS_JSON` env var (JSON array). Each channel has:
- `slug` — short identifier (used in state keys, logs)
- `channel_id` / `discussion_group_id` — Telegram chat IDs
- `reminder_chat_id` — where warnings/kick messages go (defaults to discussion group)
- `private_commands` — if true, /mystats in DM queries this channel's data
- `invite_link_name` / `manual_member_ids` — per-channel settings

Fallback: if `CHANNELS_JSON` is not set, legacy `CHANNEL_ID`/`DISCUSSION_GROUP_ID` env vars create a single-channel config.

### Current channels
1. **"Общество писем 2"** (slug: `pisma2`) — existing small uncensored channel, uses @vdokhvykhod as discussion group. Existing DB data belongs to this channel.
2. **"Общество писем the Walks"** (slug: `walks`) — new channel for broader audience including teenagers. `private_commands: true`. To be set up later.

## Architecture
- **Bot**: Python 3.12, aiogram 3.x (polling mode), aiohttp server
- **DB**: SQLite via aiosqlite, file at `data/writebot.db`
- **Scheduler**: asyncio background task — runs per-channel independently
- **CI/CD**: GitHub Actions → GCE e2-micro VM

## Project Structure
```
writebot/
  bot/
    __init__.py
    __main__.py         — entry point: python -m bot
    main.py             — polling/webhook mode, scheduler setup
    config.py           — ChannelConfig dataclass, CHANNELS_JSON parsing, lookup helpers
    handlers/
      channel.py        — channel_post handler (track daily writes, multi-channel)
      group.py          — discussion group commands (/stats, /streak, etc.)
      private.py        — /start (with command list), /mystats in DM
      admin.py          — admin commands (/addadmin, /invite_link, /debug_channel)
      membership.py     — join request + member status lifecycle
    db/
      models.py         — SQLite schema init + multi-channel migration
      queries.py        — all DB queries (parameterized, channel_id scoped)
    services/
      streaks.py        — pure streak calculation (testable, no I/O)
      scheduler.py      — evening warnings + midnight enforcement loop (per-channel)
      enforcement.py    — compliance rules (grace period, kick logic)
      channel_members.py — member promotion, invite links, formatting
  tests/
    conftest.py                  — fixtures (temp DB, test ChannelConfig, mock factories)
    test_streaks.py              — unit: streak calculation logic
    test_enforcement.py          — unit: compliance rules
    test_queries.py              — integration: all DB queries with channel_id
    test_channel_handler.py      — handler: channel post tracking
    test_group_handler.py        — handler: /stats, /missing, /streak, /leaderboard
    test_private_handler.py      — handler: /start, /mystats
    test_admin_handler.py        — handler: /addadmin, /removeadmin, /invite_link
    test_membership_handler.py   — handler: join requests, member status changes
    test_channel_members_service.py — service: promotion, invite links, sync
    test_scheduler.py            — unit: job scheduling logic
    test_scheduler_full.py       — integration: warnings + kicks with real DB
  .github/workflows/
    ci.yml              — lint + test on push/PR
    deploy.yml          — deploy to GCE on push to main
```

## Commands
### Discussion group commands (anyone, per-channel)
- `/stats` — today's writers count and names
- `/missing` — who hasn't written today
- `/streak` — your current streak
- `/leaderboard` — top streaks

### Admin commands (discussion group, global admins)
- `/addadmin` — reply to a message to make user admin
- `/removeadmin` — reply to remove admin
- `/invite_link` — show join-request invite link for this channel
- `/debug_channel` — diagnostic info

### Private commands
- `/start` — welcome message with command list
- `/mystats` — personal streak (primary channel only, configured via `private_commands`)

## DB Schema
All tables except `admins` have `channel_id` column for multi-channel isolation:
- `admins`: bot-level admins — **global** across all channels
- `channel_posts`: raw log of every channel post — PK `(channel_id, message_id)`
- `daily_participation`: one row per user per day — PK `(channel_id, user_id, date)`
- `streaks`: cached current/longest streak — PK `(channel_id, user_id)`
- `members`: tracked channel members — PK `(channel_id, user_id)`, status lifecycle: pending → active → left/kicked
- `bot_state`: key-value store, keys prefixed with channel slug (e.g., `pisma2:last_evening_warning_date`)
- `member_events`: audit log, has `channel_id` column

### Migration
`init_db()` automatically migrates old single-channel DBs: adds `channel_id` columns, backfills with first channel's ID, recreates tables with composite PKs, prefixes bot_state keys.

## Environment variables (.env)
```
BOT_TOKEN=...

# Multi-channel (recommended):
CHANNELS_JSON='[{"slug":"pisma2","channel_id":-100...,"discussion_group_id":-100...,"name":"Общество писем 2","private_commands":false},{"slug":"walks","channel_id":-100...,"discussion_group_id":-100...,"name":"The Walks","private_commands":true}]'

# Legacy single-channel fallback:
CHANNEL_ID=-100...
DISCUSSION_GROUP_ID=-100...

DB_PATH=data/writebot.db
PORT=8080
TZ=Asia/Jerusalem
INITIAL_ADMIN_ID=0
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
Tests use **mock Telegram objects** — no network calls. Key design:
- `conftest.py` provides `TEST_CHANNEL` (ChannelConfig), `TEST_CHANNEL_ID`, mock factories
- Each test gets a **fresh temporary SQLite DB** (via `setup_db` auto-fixture)
- All query calls pass `channel_id` as first parameter
- 115 tests covering all areas

## Key behaviors
- Bot must be **admin** in both channel and discussion group (for each channel)
- Channel posts are tracked via `channel_post` updates (not `message`)
- Anonymous "post as channel" posts are skipped
- Streaks are calculated in configured timezone (default: Asia/Jerusalem)
- Scheduler runs independently per channel (22:30 warning, 00:00 enforcement)
- First admin is bootstrapped via `INITIAL_ADMIN_ID` env var
- A user in two channels = two independent member records with separate streaks

## Deploy
- GCE e2-micro (free tier): 2 vCPU burst, 1 GB RAM
- GitHub Actions deploys on push to main
- Secrets: `GCP_SA_KEY`, `GCE_VM_NAME`, `GCE_VM_ZONE`, `GCP_PROJECT_ID`, `GCE_USER`

## Known issues / notes
- When adding a new channel, update `CHANNELS_JSON` on the VM's `.env` and restart the service
- The first channel in `CHANNELS_JSON` receives existing data during migration
- Bot state keys are prefixed with channel slug to avoid collisions

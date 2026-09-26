# 🌊 Searendipity

> **The serendipitous NationStates recruitment and analytics suite.**

**Searendipity** is an all-in-one suite for [NationStates](https://www.nationstates.net) recruitment, offering real-time nation event streaming, interactive Discord manual recruitment with browser container support, automated background API recruitment, intelligent puppet filtering, and campaign analytics dashboards.

Inspired by and compatible with [Merethin/Moonlark](https://github.com/Merethin/Moonlark), Searendipity uses traditional message prefix commands (`!` or `?`, e.g. `!recruit 60` or `?recruit 60`) with optimized stream parsing, memory-efficient data dump processing, and modern DaisyUI/Tailwind CSS reporting.

---

## ✨ Key Features

- **⚡ Real-Time NationStates Event Streaming**: Connects directly to NationStates Server-Sent Events (SSE) for `founding` and `member` (WA join). Features automatic reconnection and a 5-minute inactivity watchdog.
- **🛡️ Smart Puppet & Quality Filtering**:
  - Compares name prefix similarity across recent joins to skip puppet cascades.
  - Verifies `tgcanrecruit` via the NationStates API to skip nations that disable recruitment telegrams.
  - Excludes seasoned nations (>500M population) and known jump point regions (`suspicious`, `artificial_solar_system`).
- **👥 Discord Bot Manual Recruitment (Prefix: `!` or `?`)**:
  - **Shared Queues**: Fairly distributes nations across recruiters working concurrently in the same guild.
  - **A/B Testing**: Automatically alternates through multiple configured templates for each category (`wa`, `newfound`, `refound`).
  - **1-Click Dispatch**: Generates Discord embeds with clickable URL buttons that pre-populate the NationStates compose window with up to 8 targets and template tags.
  - **Containerise Support**: Optional browser container support opens links in specific Firefox Multi-Account Containers.
- **🤖 Automated API Recruitment**:
  - Delivers background recruitment telegrams via the NationStates Telegram API (`tag:api`).
  - Strict compliance with NationStates rate limits using `sans.TelegramLimiter(recruitment=True)` (180s cooldown).
  - Owner-only access controls and persistent state saved to `api.json`.
- **📊 Analytics & Report Generator (`genreport.py`)**:
  - Automatically downloads and stream-parses daily nation XML data dumps into an indexed SQLite database.
  - Computes faithful player retention (active in region within threshold days), WA retention, traitor migrations, and uninterested destinations.
  - Generates rich, responsive dark-mode HTML dashboards and JSON exports.
- **📥 Browser Userscript (`masstgexport.user.js`)**:
  - Adds a 1-click "Export JSON" button to NationStates telegram statistics pages (`/page=tg/tgid=*`).

---

## 🚀 Installation & Setup

### Prerequisites

- Python 3.11+ (tested on Python 3.13 and Python 3.14)
- A Discord Application Token with **Server Members Intent** and **Message Content Intent** enabled.
- A main NationStates nation name (for API User-Agent compliance).

### 1. Clone & Set Up Virtual Environment

```bash
cd /home/pmitra/Projects/Searendipity

# Activate the existing virtual environment
source .venv/bin/activate

# Or create a new virtual environment if needed
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env`:

```ini
TOKEN="your_discord_bot_token"
OWNER_ID="your_discord_user_id"
DEFAULT_NATION="your_main_nation_name"
COMMAND_PREFIX="!,?"
```

---

## 🎮 Running the Discord Recruitment Bot

Start Searendipity with your main nation name:

```bash
python searendipity.py -n "My_Nation"
```

You can optionally specify a custom prefix with `-p` (e.g. `python searendipity.py -n "My_Nation" -p "?"`). Both `!` and `?` are supported by default.

### Discord Bot Commands (`!` or `?`)

#### Server Administration
- `!config <@AdminRole> <@RecruitRole> [recruit_wa] [recruit_newfounds] [recruit_refounds]`: Configures roles and enabled categories for the server (Server Owner only).

#### Template Management
- `!setup <tgid>`: Registers a generic template (e.g. `!setup %TEMPLATE-12345%` or `!setup 12345`) across all destinations (WA, newfounds, refounds).
- `!add <destination> <category> <tgid>`: Registers a template for a specific destination (`wa`, `newfound`, or `refound`). E.g. `!add wa greeting_a 12345`.
- `!templates`: Lists your active registered templates in the server with quick links.
- `!remove <category>`: Removes templates belonging to a specific category. E.g. `!remove greeting_a`.
- `!clear`: Clears all your registered templates in the current server.

#### Manual Recruitment
- `!recruit [interval] [container]`: Starts an active recruitment session. Dispatches embeds every `interval` seconds (default 60s). Optionally pass container name for Containerise (e.g. `!recruit 60 MyContainer`).
- `!stop`: Stops your active recruitment session.
- `!forcestop <@User>`: As an administrator, terminates an idle or abandoned user session.
- `!queue`: Displays real-time backlog queue counts for the server.
- `!timer`: Shows recommended cooldown intervals based on nation age.
- `!stats [since]`: Displays paginated recruiter leaderboard for the server (all-time or last N days, e.g. `!stats 7`).

#### Automated API Recruitment (Bot Owner Only)
- `!apiguild`: Binds API recruitment to the current server's queues.
- `!apiclient <client_key>`: Sets the NationStates API client key.
- `!apisetup <tgid> <key>`: Registers a generic API template across all destinations.
- `!apiadd <destination> <category> <tgid> <key>`: Adds an API template with its secret key.
- `!apistart`: Starts the background API telegram loop.
- `!apistop`: Stops background API recruitment.
- `!apirestart`: Restarts the API loop.
- `!apistatus`: Displays API recruitment status, uptime, and telegram counters.
- `!apitemplates`: Lists registered API templates and secret keys (sent to DM for security).
- `!apiremove <category>`: Removes API templates by category.
- `!apiclear`: Clears all registered API templates.

---

## 📈 Generating Recruitment Reports

Searendipity includes `genreport.py` to evaluate the effectiveness of recruitment campaigns.

### Step 1: Install the Userscript
Install `userscripts/masstgexport.user.js` in Tampermonkey or Violentmonkey. When viewing telegram statistics on NationStates (`/page=tg/tgid=...`), click **"Export JSON (Searendipity)"**. Place downloaded `.json` files into the `telegrams/` directory.

### Step 2: Generate the Report

```bash
python genreport.py -n "My_Nation" --region "My_Region"
```

Optional flags:
- `-a <days>`: Activity threshold for faithful recruits (default: 7 days).
- `-r`: Force re-download of daily `nations.xml.gz`.
- `-o <dir>`: Output folder (default: `reports`).
- `-i <report.json>`: Render HTML from existing JSON report without re-downloading dumps.
- `-t <dir>`: Folder containing exported telegram JSON files (default: `telegrams`).

Open `reports/index.html` in your browser to view the interactive dashboard!

---

## 📜 NationStates API Compliance

Searendipity is designed to strictly follow all [NationStates Scripting Rules](https://www.nationstates.net/pages/api.html):
- **User-Agent**: Automatically identified with every HTTP request.
- **API Recruitment**: Strictly limited to 1 telegram every 180 seconds via `sans.TelegramLimiter(recruitment=True)`.
- **Manual Recruitment**: Uses standard `compose_telegram` URLs with `generated_by` attribution parameters.

---

## 📄 License

Released under the **BSD-2-Clause License**.

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
  - **⚡ Parallel Queueing (Multi-Recruiter)**: Multiple team members can manually recruit simultaneously! Incoming nations are fairly distributed round-robin across active recruiter sessions in parallel queues.
  - **Zero Duplicate Telegrams**: Each nation is routed to exactly one recruiter so teammates never step on each other's toes or send duplicate telegrams.
  - **Safe Queue Recycling**: When a recruiter stops, un-dispatched nations automatically return to the guild backlog for other recruiters to claim.
  - **A/B Testing**: Automatically alternates through multiple configured templates for each category (`wa`, `newfound`, `refound`).
  - **1-Click Dispatch**: Generates Discord embeds with clickable URL buttons that pre-populate the NationStates compose window with up to 8 targets and template tags.
  - **Strict Cooldown & Verified Progression**: Eliminates automatic message spam. Enforces strict wait times, verifies the previous list was marked as sent, and requires the recruiter to manually click `[Get Next List]` when ready.
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


---

### 🖥️ Interactive GUI Dashboard (`?start` or `!start`)

You only need **one command**:

```
?start
```
*(or `!start`, `?panel`, `?gui`, `?menu`)*

This displays the **Searendipity Control Panel**, giving 1-click access to all features via interactive Discord buttons and pop-up modal dialogs:

```
==================================================
           🌊 SEARENDIPITY CONTROL PANEL
==================================================
Welcome! Use the buttons below to manage templates,
monitor live queues, and start recruiting.

📡 Live Queues:
• WA Joins: 15  • Newfounds: 84  • Refounds: 42
👤 Your Status:
• Session: 🟢 Active (60s)  • Templates: 2 WA, 1 New, 1 Refound
==================================================
```

#### 🎮 Control Panel Buttons & Modals

##### Row 0 — Recruitment Controls
- **`▶️ Start Recruiting`**: Opens a pop-up modal to enter cooldown interval (seconds, default 60s) and optional browser container name (e.g. for Containerise). Launches session and delivers your first dispatch embed to the channel.
- **`⏹️ Stop Recruiting`**: Immediately terminates your active recruitment session.
- **`📊 View Queue`**: Shows live backlog numbers for WA admissions, newly founded, and refounded nations.
- **`⏱️ Cooldown Guide`**: Displays official NationStates recruitment rate limits by nation age.

###### 📬 Strict Batch Dispatch & Progression Flow
When recruiting starts or the next list is requested, an interactive dispatch embed is sent to the channel with four action buttons:

1. **`[Click to Send TG]`** (Link button): Opens the NationStates compose window pre-populated with up to 8 targets, your rotating template ID tag (`%TEMPLATE-#####%`), and tracking parameters.
2. **`[✅ Mark as Sent]`**: After sending your telegram on NationStates, click this button to confirm delivery.
   - Updates your stats on the recruiter leaderboard.
   - Activates your strict cooldown timer and updates the embed with a dynamic countdown `<t:ready_at:R>`.
   - Cannot be clicked multiple times.
3. **`[⏭️ Get Next List]`**: Request the next recipient batch once your cooldown ends.
   - **Verification Check**: Fails if you haven't clicked `Mark as Sent` yet (*"⚠️ Check Failed: You have not marked the current list as sent yet!"*).
   - **Strict Wait Time**: Fails if the cooldown is still active (*"⏳ Strict Cooldown Active! You must wait another X seconds..."*).
   - **Manual Progression**: The bot **never** automatically posts new batches when timers expire. You have full control over when to pull the next list.
4. **`[⏹️ Stop Session]`**: Immediately cancels your recruitment session and disables the action buttons.

###### ⚡ Parallel Queueing & Multi-Recruiter Support
- **Simultaneous Recruitment**: Multiple members of your server can recruit concurrently at their own pace.
- **Round-Robin Split**: Arriving nations (from WA joins, new foundings, and refounds) are divided round-robin across all active recruiters in the server, ensuring equal distribution with **zero overlap** (no duplicate telegrams).
- **Personal Parallel Buffers**: Each recruiter has their own parallel queue. A recruiter on a 60s cooldown will not drain incoming nations from a recruiter on a 180s cooldown.
- **Guild Backlog Fallback**: When starting recruitment or when incoming stream volume is low, recruiters automatically draw available nations from the shared guild backlog.
- **Automatic Recycling**: If a recruiter stops (`?stop` or `[Stop Session]`), any un-dispatched nations in their personal queue are safely returned to the guild backlog for other active recruiters to claim.
- **Queue Transparency**: Both `?queue` and the `?start` dashboard show the count of active parallel recruiters and the user's personal queue depth.

##### Row 1 — Template Management
- **`📋 My Templates`**: Sends an embed listing all your registered templates with clickable links to their NationStates stats pages.
- **`➕ Add Template`**: Opens a modal to register a template for a specific destination (`wa`, `newfound`, or `refound`), category label, and template ID (`%TEMPLATE-12345%` or `12345`).
- **`⚡ Quick Setup`**: Opens a modal to set a single template ID across all three destinations with one click.
- **`🗑️ Clear Templates`**: Clears all your registered templates in this server.

##### Row 2 — Recruiter Statistics
- **`🏆 Recruiter Leaderboard`**: Displays the server recruitment rankings and category breakdown with interactive pagination buttons.

##### Row 3 — Server Administration & API Automation
- **`⚙️ Server Config`**: *(Server Owner / Admin)* Opens a modal to configure Admin Role, Recruiter Role, and destination toggles.
- **`🛑 Force Stop User`**: *(Server Owner / Admin)* Opens a modal to stop another member's idle or abandoned recruitment session.
- **`🤖 API Recruiter`**: *(Bot Owner)* Opens the automated API recruitment sub-panel with buttons to bind the server, set client key, configure templates, and start/stop background API telegramming.

---

### ⌨️ Fallback Text Commands (Optional)

If you prefer typing commands directly, all text commands remain supported:
- **Administration**: `?config <@AdminRole> <@RecruitRole> [wa] [newfounds] [refounds]`
- **Templates**: `?templates`, `?add <wa|newfound|refound> <category> <tgid>`, `?setup <tgid>`, `?remove <category>`, `?clear`
- **Recruitment**: `?recruit [interval] [container]`, `?stop`, `?forcestop <@User>`, `?queue`, `?timer`
- **Leaderboard**: `?stats [since_days]`
- **API Recruitment**: `?apiguild`, `?apiclient <key>`, `?apistart`, `?apistop`, `?apirestart`, `?apistatus`, `?apitemplates`, `?apiadd`, `?apisetup`, `?apiremove`, `?apiclear`


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

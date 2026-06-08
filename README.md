# IDP Command Center

A private operations dashboard for Jeremy Yost / IDP / Ironhold Asset Management.
Pulls live data from Notion, Xero, Gmail, and Claude AI.

## Quick Start (new machine)

```bash
git clone git@github.com:jry007/IDP_Command_Center.git
cd IDP_Command_Center
python3 setup_wizard.py
```

The wizard installs dependencies, saves API keys, authorizes Gmail and Xero, installs the scheduled agents, and launches the dashboard.

---

## Dashboard Panels

| Panel | Data Source | Refresh |
|---|---|---|
| 📊 Dashboard | All sources | On load |
| 🏨 HGI Night Audit | Notion → HGI Daily Metrics | Agent 7:45 AM |
| 💰 Cash Position | Notion → Cash Position Daily | Agent 8:00 AM |
| 📋 Deal Pipeline | Notion → Deal Pipeline | Real-time |
| ✅ Action Items | Notion → Action Items | Real-time |
| 📁 Portfolio Reports | Notion → Weekly Portfolio Log | Agent (Fri/Mon) |

---

## Scheduled Agents

| Agent | File | Schedule | Purpose |
|---|---|---|---|
| HGI Audit | `agents/hgi_audit_agent.py` | 7:45 AM daily | Gmail PDF → Claude → Notion |
| Xero Cash | `agents/xero_cash_agent.py` | 8:00 AM daily | Xero BankSummary → Notion |
| Leasing | `agents/leasing_followup_agent.py` | 8:30 AM Monday | AppFolio/Gmail → Notion actions |
| Gardant AL | `agents/gardant_al_agent.py` | 9:00 AM daily | Gmail reports → Notion actions |
| Portfolio | `agents/portfolio_report_agent.py` | Fri 6 PM + Mon 8 AM | Kim's reports → Notion actions |

Logs are written to `logs/` (gitignored).

---

## Manual Agent Runs

```bash
python3 agents/hgi_audit_agent.py
python3 agents/xero_cash_agent.py
python3 agents/gardant_al_agent.py
python3 agents/portfolio_report_agent.py
python3 agents/leasing_followup_agent.py
```

---

## Setup (step by step)

### 1. Clone and install
```bash
git clone git@github.com:jry007/IDP_Command_Center.git
cd IDP_Command_Center
pip3 install -r requirements.txt
```

### 2. Create .env
```bash
cp .env.example .env
# Edit .env with your keys
```

Required keys:
- `NOTION_TOKEN` — from notion.so/my-integrations
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `XERO_CLIENT_ID` / `XERO_CLIENT_SECRET` — from developer.xero.com
- `GMAIL_CREDENTIALS_PATH` — path to OAuth JSON from Google Cloud Console
- `KIM_EMAIL` — Kim's email for portfolio report detection

### 3. Authorize Gmail
```bash
python3 agents/gmail_auth.py
```
- Requires `credentials/gmail_credentials.json` from Google Cloud Console
- Creates `agents/gmail_token.json` (gitignored)

### 4. Authorize Xero
```bash
python3 agents/xero_auth.py
```
- Opens browser OAuth flow
- Creates `agents/xero_tokens.json` and `agents/xero_tenants.json` (gitignored)

### 5. Install scheduled agents
```bash
bash launchd/install_launchd.sh
```

### 6. Run dashboard
```bash
python3 -m streamlit run app.py
```

---

## Syncing Between Machines

```bash
# After changes on any machine:
git add -A && git commit -m "update" && git push

# On other machine:
git pull
```

API tokens (`.env`, `agents/*.json`, `credentials/`) are gitignored and must be set up on each machine using the wizard.

---

## Project Structure

```
IDP_Command_Center/
├── app.py                          # Streamlit dashboard
├── config.py                       # Notion DB IDs, field maps
├── setup_wizard.py                 # One-command setup
├── requirements.txt
├── .env.example                    # Template (copy to .env)
├── agents/
│   ├── gmail_auth.py               # Shared Gmail OAuth helper
│   ├── xero_auth.py                # Xero OAuth + tenant discovery
│   ├── hgi_audit_agent.py          # HGI night audit parser
│   ├── xero_cash_agent.py          # Xero cash position sync
│   ├── gardant_al_agent.py         # Gardant AL report parser
│   ├── portfolio_report_agent.py   # Kim's weekly report parser
│   └── leasing_followup_agent.py   # AppFolio/leasing follow-up
├── launchd/
│   ├── *.plist                     # macOS scheduler configs
│   ├── install_launchd.sh          # Install all agents
│   └── uninstall_launchd.sh        # Remove all agents
├── credentials/                    # gitignored — OAuth JSONs
└── logs/                           # gitignored — agent logs
```

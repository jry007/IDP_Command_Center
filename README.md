# IDP Command Center

A personal Streamlit dashboard for tracking IDP goals, milestones, and AI agent tasks — synced via Git.

## Setup

```bash
# 1. Install dependencies
pip3 install -r requirements.txt

# 2. Run the dashboard
streamlit run app.py
```

## Sync to another machine

```bash
# On this machine (after making changes)
git add -A && git commit -m "update" && git push

# On desktop
git pull
streamlit run app.py
```

## Structure

```
IDP_Command_Center/
├── app.py            # Main Streamlit app
├── requirements.txt
├── data/
│   ├── goals.json    # Your goals & milestones (auto-saved)
│   └── tasks.json    # Your AI agent tasks (auto-saved)
└── README.md
```

"""
IDP Command Center — Setup Wizard
Run once on a new machine to configure all credentials and authorize all services.

Usage:
    python3 setup_wizard.py
"""
import os, sys, subprocess, pathlib, json

ROOT = pathlib.Path(__file__).parent
ENV_FILE = ROOT / ".env"


def banner(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)


def ask(prompt, default=None, secret=False):
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    if secret:
        import getpass
        val = getpass.getpass(prompt)
    else:
        val = input(prompt).strip()
    return val or default or ""


def check_installed(package):
    try:
        __import__(package.replace("-","_").split(">=")[0])
        return True
    except ImportError:
        return False


def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}")
    return result


# ── Step 1: Install dependencies ─────────────────────────────────────────────

banner("Step 1 of 6 — Installing Python dependencies")
print("Installing packages from requirements.txt...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"), "-q"],
    capture_output=False
)
if result.returncode == 0:
    print("✓ All packages installed.")
else:
    print("Some packages may have failed — check output above.")

# ── Step 2: API keys ──────────────────────────────────────────────────────────

banner("Step 2 of 6 — API Keys")

existing = {}
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            existing[k.strip()] = v.strip()

print("Enter your API keys. Press Enter to keep existing value.\n")

keys = {
    "NOTION_TOKEN": {
        "label": "Notion Integration Token",
        "hint":  "Get from: notion.so/my-integrations → New integration",
        "secret": True,
    },
    "ANTHROPIC_API_KEY": {
        "label": "Anthropic (Claude) API Key",
        "hint":  "Get from: console.anthropic.com/settings/keys",
        "secret": True,
    },
    "XERO_CLIENT_ID": {
        "label": "Xero Client ID",
        "hint":  "Get from: developer.xero.com/app/manage → Your App",
        "secret": False,
    },
    "XERO_CLIENT_SECRET": {
        "label": "Xero Client Secret",
        "hint":  "Same location as Client ID",
        "secret": True,
    },
    "KIM_EMAIL": {
        "label": "Kim's email address (for portfolio reports)",
        "hint":  "The email address Kim sends weekly reports from",
        "secret": False,
    },
    "GMAIL_CREDENTIALS_PATH": {
        "label": "Gmail credentials JSON path",
        "hint":  "Default: credentials/gmail_credentials.json",
        "secret": False,
    },
}

env_vals = dict(existing)

for key, cfg in keys.items():
    current = existing.get(key, "")
    print(f"\n{cfg['label']}")
    print(f"  Hint: {cfg['hint']}")
    if current:
        masked = current[:6] + "..." if cfg["secret"] and len(current) > 6 else current
        print(f"  Current: {masked}")
        change = input("  Keep existing? [Y/n]: ").strip().lower()
        if change not in ("n", "no"):
            continue
    val = ask(f"  Enter value", secret=cfg["secret"])
    if val:
        env_vals[key] = val

# Set default for gmail path
if "GMAIL_CREDENTIALS_PATH" not in env_vals or not env_vals["GMAIL_CREDENTIALS_PATH"]:
    env_vals["GMAIL_CREDENTIALS_PATH"] = "credentials/gmail_credentials.json"

# Write .env
lines = [f"{k}={v}" for k, v in env_vals.items()]
ENV_FILE.write_text("\n".join(lines) + "\n")
print(f"\n✓ Credentials saved to .env")

# ── Step 3: Gmail OAuth ───────────────────────────────────────────────────────

banner("Step 3 of 6 — Gmail Authorization")

creds_path = ROOT / env_vals.get("GMAIL_CREDENTIALS_PATH", "credentials/gmail_credentials.json")
token_path = ROOT / "agents" / "gmail_token.json"

if token_path.exists():
    print(f"Gmail token already exists at {token_path}")
    redo = input("Re-authorize Gmail? [y/N]: ").strip().lower()
    if redo in ("y", "yes"):
        token_path.unlink()

if not token_path.exists():
    if not creds_path.exists():
        print(f"\nGmail credentials file not found at: {creds_path}")
        print("\nTo get Gmail credentials:")
        print("  1. Go to console.cloud.google.com")
        print("  2. Create/select a project")
        print("  3. Enable the Gmail API")
        print("  4. Create OAuth 2.0 credentials (Desktop app)")
        print(f"  5. Download JSON and save as: {creds_path}")
        print("\nOnce saved, re-run this wizard or run: python3 agents/gmail_auth.py")
        input("\nPress Enter to continue (skip Gmail for now)...")
    else:
        print("Opening browser for Gmail authorization...")
        result = subprocess.run([sys.executable, str(ROOT / "agents" / "gmail_auth.py")])
        if result.returncode == 0:
            print("✓ Gmail authorized.")
        else:
            print("Gmail authorization failed. You can retry with: python3 agents/gmail_auth.py")

# ── Step 4: Xero OAuth ────────────────────────────────────────────────────────

banner("Step 4 of 6 — Xero Authorization")

xero_token_path  = ROOT / "agents" / "xero_tokens.json"
xero_tenant_path = ROOT / "agents" / "xero_tenants.json"

if xero_token_path.exists() and xero_tenant_path.exists():
    tenants = json.loads(xero_tenant_path.read_text())
    print(f"Xero already authorized ({len(tenants)} org(s) connected):")
    for name in tenants:
        print(f"  ✓ {name}")
    redo = input("Re-authorize Xero? [y/N]: ").strip().lower()
    if redo not in ("y", "yes"):
        print("Keeping existing Xero authorization.")
        skip_xero = True
    else:
        skip_xero = False
else:
    skip_xero = False

if not skip_xero:
    if not env_vals.get("XERO_CLIENT_ID") or not env_vals.get("XERO_CLIENT_SECRET"):
        print("Xero Client ID/Secret not set. Skipping Xero setup.")
        print("Set them in .env and run: python3 agents/xero_auth.py")
    else:
        print("Opening browser for Xero authorization...")
        result = subprocess.run([sys.executable, str(ROOT / "agents" / "xero_auth.py")])
        if result.returncode == 0:
            print("✓ Xero authorized.")
        else:
            print("Xero authorization failed. Retry with: python3 agents/xero_auth.py")

# ── Step 5: Install launchd agents ───────────────────────────────────────────

banner("Step 5 of 6 — Install Scheduled Agents (launchd)")

print("This installs 5 background agents to run automatically:\n")
print("  7:45 AM daily     — HGI Night Audit parser")
print("  8:00 AM daily     — Xero Cash Position sync")
print("  8:30 AM Monday    — Leasing Follow-Up (AppFolio)")
print("  9:00 AM daily     — Gardant AL Reports")
print("  6:00 PM Friday    — Kim's Portfolio Report parser")
print("  8:00 AM Monday    — Kim's Portfolio Report (catch-up)\n")

install = input("Install launchd agents now? [Y/n]: ").strip().lower()
if install not in ("n", "no"):
    result = subprocess.run(["bash", str(ROOT / "launchd" / "install_launchd.sh")])
    if result.returncode == 0:
        print("✓ Agents installed and scheduled.")
    else:
        print("Installation failed. Try manually: bash launchd/install_launchd.sh")
else:
    print("Skipped. Install later with: bash launchd/install_launchd.sh")

# ── Step 6: Launch dashboard ──────────────────────────────────────────────────

banner("Step 6 of 6 — Launch Dashboard")
print("Setup complete! Launch the dashboard with:\n")
print("  python3 -m streamlit run app.py\n")

launch = input("Launch dashboard now? [Y/n]: ").strip().lower()
if launch not in ("n", "no"):
    print("\nStarting dashboard at http://localhost:8501 ...")
    os.execvp(sys.executable, [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py")])
else:
    banner("Setup Complete!")
    print("Run anytime:  python3 -m streamlit run ~/IDP_Command_Center/app.py")
    print("Sync:         git pull  (on any machine)")
    print("Agent logs:   ~/IDP_Command_Center/logs/")

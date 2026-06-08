NOTION_DB = {
    "cash_position":     "35d8a99fb94481b1afa9da84fece162b",
    "hgi_daily_metrics": "35d8a99fb944812eb207de4cab3494d0",
    "deal_pipeline":     "35d8a99fb94481da927be85a13dfaa3d",
    "action_items":      "35f8a99fb94481d3aa55eb0c5e8e16ce",
    "portfolio_reports": "35d8a99fb94481d48547ea9c6ebc7c9f",
}

# Notion field name -> display label for cash position panel
CASH_FIELDS = {
    "Xero IAM Corporate":    "Ironhold AM S-Corp",
    "Xero IAM LLC":          "Ironhold AM LLC",
    "Xero IDP":              "Innovative Dev Partners",
    "Xero Yost Enterprises": "Yost Enterprises",
    "Xero Yost Development": "Yost Development",
    "Xero Vending":          "The Vending Company",
    "Xero IAM":              "IAM (Main)",
    "Xero Hotel Operating":  "Hotel Operating",
    "AppFolio Trust":        "AppFolio Trust",
    "Xero Other":            "Other",
}

# Xero org short ID -> Notion cash field name
# IDs are populated during xero_auth.py setup and stored in agents/xero_tenants.json
XERO_ORG_MAP = {
    "Ironhold Asset Management S-Corp":       "Xero IAM Corporate",
    "Ironhold Asset Management LLC":          "Xero IAM LLC",
    "Innovative Development Partners":        "Xero IDP",
    "Yost Enterprises":                       "Xero Yost Enterprises",
    "Yost Development":                       "Xero Yost Development",
    "The Vending Company":                    "Xero Vending",
    "Ironhold Asset Management":              "Xero IAM",
    "Mattoon Hilton Garden Inn":              "Xero Hotel Operating",
}

STAGE_COLORS = {
    "Prospecting":    "#6b7280",
    "LOI":            "#f59e0b",
    "Due Diligence":  "#f97316",
    "Under Contract": "#3b82f6",
    "Closed":         "#22c55e",
    "Dead":           "#ef4444",
}

PRIORITY_COLORS = {
    "High":   "#ef4444",
    "Medium": "#f59e0b",
    "Low":    "#3b82f6",
}

ACTION_CATEGORIES = ["Finance", "Operations", "Legal", "Deals", "Hotel"]

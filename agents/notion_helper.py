"""
Shared Notion REST helper for all agents.
Uses requests directly — no SDK dependency.
"""
import os, requests
from dotenv import load_dotenv
import pathlib

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

NOTION_VERSION = "2022-06-28"


def _headers():
    return {
        "Authorization": f"Bearer {os.getenv('NOTION_TOKEN')}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def db_query(db_id: str, sorts=None, filters=None) -> list:
    url  = f"https://api.notion.com/v1/databases/{db_id}/query"
    body = {}
    if sorts:   body["sorts"]  = sorts
    if filters: body["filter"] = filters
    results, cursor = [], None
    while True:
        if cursor:
            body["start_cursor"] = cursor
        resp = requests.post(url, headers=_headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return results


def page_create(db_id: str, properties: dict) -> dict:
    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=_headers(),
        json={"parent": {"database_id": db_id}, "properties": properties},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def page_update(page_id: str, properties: dict) -> dict:
    resp = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=_headers(),
        json={"properties": properties},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def find_existing(db_id: str, title_field: str, title_value: str) -> str | None:
    """Return page_id if a record with the given title exists, else None."""
    results = db_query(db_id, filters={
        "property": title_field,
        "title": {"equals": title_value}
    })
    return results[0]["id"] if results else None

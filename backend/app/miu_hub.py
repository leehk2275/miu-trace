"""Read-only MIU Hub Supabase ledger synchronizer.

MIU Hub records operational events at scan time.  The local copy keeps MIU
Trace independent from that service at query time and supplies the audit
archive with stable source evidence.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
INDEX = Path(os.getenv("MIU_TRACE_MIU_HUB_INDEX", ROOT / "var" / "miu-hub-index.sqlite"))
SOURCE_URL = "https://315seconds.github.io/miu-hub/receiving/items.html"
FAMILY = "MIU_HUB_SUPABASE"
BARCODE = re.compile(r"^(?:[A-Z]{1,6}\d{1,14}|\d{8,14})$")
SEOUL = ZoneInfo("Asia/Seoul")


def normalize(value) -> str:
    return re.sub(r"[\u200b-\u200d\ufeff\s]", "", str(value or "")).upper()


def iso_time(value) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(SEOUL).isoformat(timespec="seconds")


def day(value) -> str | None:
    timestamp = iso_time(value)
    return timestamp[:10] if timestamp else None


def source_config() -> tuple[str, str]:
    url = os.getenv("MIU_HUB_SUPABASE_URL", "https://yqnocnzjrcsrwrvsvsyg.supabase.co").rstrip("/")
    key = os.getenv("MIU_HUB_SUPABASE_ANON_KEY")
    if not key:
        raise RuntimeError("MIU_HUB_SUPABASE_ANON_KEY is required for MIU Hub synchronization")
    return url, key


def fetch_all(url: str, key: str, table: str, select: str, order: str, extra: dict[str, str] | None = None) -> list[dict]:
    rows: list[dict] = []
    start = 0
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Range-Unit": "items"}
    while True:
        params = urllib.parse.urlencode({"select": select, "order": order, **(extra or {})})
        request = urllib.request.Request(f"{url}/rest/v1/{table}?{params}", headers={**headers, "Range": f"{start}-{start + 999}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            page = json.loads(response.read().decode("utf-8"))
        if not isinstance(page, list):
            raise RuntimeError(f"Unexpected {table} response")
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += len(page)


def build_payload(inventory: list[dict], moves: list[dict], prices: list[dict], sales: list[dict]) -> dict:
    events: list[dict] = []
    products: dict[str, dict] = {}
    moves_by_code: dict[str, list[dict]] = defaultdict(list)
    for row in moves:
        code = normalize(row.get("barcode"))
        session = row.get("move_sessions") or {}
        occurred = iso_time(row.get("scanned_at") or session.get("session_date") or row.get("created_at"))
        if not BARCODE.match(code) or not occurred or not session.get("to_location"):
            continue
        event = {
            "barcode": code, "type": "LOCATION_CHANGE", "label": "위치 이동", "from": occurred,
            "precision": "EXACT", "confidence": "CONFIRMED", "before": session.get("from_location") or None,
            "after": session.get("to_location") or None, "source_family": FAMILY, "source_id": "miu_hub",
            "source_file": "session_items", "worksheet": "move_sessions", "row": row.get("id"),
            "evidence": f"MIU Hub 물류 이동 · {session.get('session_date') or occurred[:10]} · {session.get('from_location') or '출발지 미확인'} → {session.get('to_location')}",
            "source_url": SOURCE_URL,
        }
        moves_by_code[code].append(event)
        events.append(event)
    for row in inventory:
        code = normalize(row.get("barcode"))
        occurred = iso_time(row.get("created_at"))
        if not BARCODE.match(code):
            continue
        products[code] = {
            "barcode": code, "received_at": day(occurred), "location": row.get("location") or None,
            "description": row.get("product_name") or None, "price": row.get("price"),
            "category": row.get("category") or None, "updated_at": occurred,
        }
        if occurred:
            first_move = next((event for event in sorted(moves_by_code.get(code, []), key=lambda item: item["from"]) if event["from"] >= occurred and event.get("before")), None)
            initial_location = first_move.get("before") if first_move else None
            evidence = "MIU Hub 입고 등록"
            if initial_location:
                evidence += f" · 최초 물류 이동 원장 기준 초기 위치 {initial_location}"
            events.append({
                "barcode": code, "type": "RECEIVED", "label": "정식 입고", "from": occurred,
                "precision": "EXACT", "confidence": "CONFIRMED" if not initial_location else "HIGH",
                "after": initial_location, "price": row.get("price"), "source_family": FAMILY,
                "source_id": "miu_hub", "source_file": "inventory_items", "worksheet": "inventory_items",
                "row": row.get("id"), "evidence": evidence, "source_url": SOURCE_URL,
            })
    for row in prices:
        code = normalize(row.get("barcode"))
        occurred = iso_time(row.get("changed_at") or row.get("created_at"))
        if BARCODE.match(code) and occurred:
            events.append({
                "barcode": code, "type": "PRICE_CHANGE", "label": "가격 수정", "from": occurred,
                "precision": "EXACT", "confidence": "CONFIRMED", "before": row.get("old_price"), "after": row.get("new_price"),
                "source_family": FAMILY, "source_id": "miu_hub", "source_file": "price_changes", "worksheet": "price_changes", "row": row.get("id"),
                "evidence": "MIU Hub 가격 수정", "source_url": SOURCE_URL,
            })
    for row in sales:
        code = normalize(row.get("barcode"))
        occurred = iso_time(row.get("sold_date") or row.get("created_at"))
        if BARCODE.match(code) and occurred:
            events.append({
                "barcode": code, "type": "SOLD", "label": "판매", "from": occurred,
                "precision": "EXACT", "confidence": "CONFIRMED", "location": row.get("store") or None, "price": row.get("price"),
                "source_family": FAMILY, "source_id": "miu_hub", "source_file": "sold_items", "worksheet": "sold_items", "row": row.get("id"),
                "evidence": "MIU Hub 판매 완료", "source_url": SOURCE_URL,
            })
    return {"generated_at": datetime.now(SEOUL).isoformat(timespec="seconds"), "mode": "MIU_HUB_SUPABASE", "products": products, "events": events}


def write_index(payload: dict, output: Path = INDEX) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript("CREATE TABLE products(barcode TEXT PRIMARY KEY,payload TEXT NOT NULL);CREATE TABLE events(barcode TEXT NOT NULL,occurred TEXT NOT NULL,payload TEXT NOT NULL);CREATE INDEX events_barcode_time ON events(barcode,occurred);CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);")
        connection.executemany("INSERT INTO products VALUES (?,?)", ((code, json.dumps(product, ensure_ascii=False, separators=(",", ":"))) for code, product in payload["products"].items()))
        connection.executemany("INSERT INTO events VALUES (?,?,?)", ((event["barcode"], event.get("from") or "", json.dumps(event, ensure_ascii=False, separators=(",", ":"))) for event in payload["events"]))
        connection.executemany("INSERT INTO meta VALUES (?,?)", ((key, str(payload.get(key) or "")) for key in ("generated_at", "mode")))
        connection.commit()
    finally:
        connection.close()
    temporary.replace(output)


def sync(output: Path = INDEX) -> dict:
    url, key = source_config()
    payload = build_payload(
        fetch_all(url, key, "inventory_items", "*", "created_at.asc"),
        fetch_all(url, key, "session_items", "*,move_sessions(to_location,session_date,from_location,created_by)", "scanned_at.asc", {"is_submitted": "eq.true"}),
        fetch_all(url, key, "price_changes", "*", "changed_at.asc"),
        fetch_all(url, key, "sold_items", "*", "sold_date.asc"),
    )
    write_index(payload, output)
    return payload

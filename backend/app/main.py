from __future__ import annotations

import json
import gzip
import os
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.app.dropbox_index import normalize_category
from backend.app.event_archive import archived_events_for_barcode, mark_observed_events
from backend.app.miu_hub import INDEX as MIU_HUB_INDEX

ROOT = Path(__file__).resolve().parents[2]
STATIC_DATA = Path(os.getenv("MIU_TRACE_DATA", ROOT / "frontend" / "data" / "beta-events.json"))
GOOGLE_STATIC_DATA = Path(os.getenv("MIU_TRACE_GOOGLE_DATA", ROOT / "frontend" / "data" / "google-events.json.gz"))
INDEX = Path(os.getenv("MIU_TRACE_INDEX", ROOT / "var" / "dropbox-index.sqlite"))
PAGES_ORIGIN = os.getenv("MIU_TRACE_PAGES_ORIGIN", "https://i7444636.github.io")
GOOGLE_CACHE_SECONDS = int(os.getenv("MIU_TRACE_GOOGLE_CACHE_SECONDS", "21600"))

app = FastAPI(title="MIU Trace Beta API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[PAGES_ORIGIN], allow_methods=["GET", "POST"], allow_headers=["*"])
google_cache = {}
google_lock = threading.Lock()
EVENT_ORDER = {"RECEIVED": 0, "LOCATION_CHANGE": 10, "DISCARDED": 11, "STATUS_CHANGE": 12, "INFO_CHANGE": 20, "PRICE_CHANGE": 30, "SOLD": 40, "REFUND": 50}


class BatchRequest(BaseModel):
    barcodes: list[str] = Field(min_length=1, max_length=500)


def normalize(value: str) -> str:
    return re.sub(r"[\u200b-\u200d\ufeff\s]", "", value).upper()


def static_payload():
    try:
        base = json.loads(STATIC_DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        base = {"events": [], "diagnostics": []}
    try:
        with gzip.open(GOOGLE_STATIC_DATA, "rt", encoding="utf-8") as handle:
            full = json.load(handle)
        return {"events": full.get("events", []), "diagnostics": full.get("diagnostics", []), "generated_at": full.get("generated_at")}
    except (OSError, json.JSONDecodeError):
        return base


def index_query(code):
    if not INDEX.exists():
        return None, [], {}
    connection = sqlite3.connect(f"file:{INDEX.as_posix()}?mode=ro", uri=True)
    row = connection.execute("SELECT payload FROM products WHERE barcode=?", (code,)).fetchone()
    product = json.loads(row[0]) if row else None
    if product:
        product["category"] = normalize_category(product.get("category"))
    events = [json.loads(item[0]) for item in connection.execute("SELECT payload FROM events WHERE barcode=? ORDER BY occurred", (code,))]
    meta = dict(connection.execute("SELECT key,value FROM meta WHERE key IN ('generated_at','sales_coverage_end','mode')"))
    connection.close()
    return product, events, meta


def miu_hub_query(code):
    if not MIU_HUB_INDEX.exists():
        return None, []
    connection = sqlite3.connect(f"file:{MIU_HUB_INDEX.as_posix()}?mode=ro", uri=True)
    row = connection.execute("SELECT payload FROM products WHERE barcode=?", (code,)).fetchone()
    product = json.loads(row[0]) if row else None
    events = [json.loads(item[0]) for item in connection.execute("SELECT payload FROM events WHERE barcode=? ORDER BY occurred", (code,))]
    connection.close()
    return product, events


def google_events(code):
    now = time.time()
    cached = google_cache.get(code)
    if cached and now - cached[0] < GOOGLE_CACHE_SECONDS:
        return cached[1], cached[2]
    with google_lock:
        cached = google_cache.get(code)
        if cached and now - cached[0] < GOOGLE_CACHE_SECONDS:
            return cached[1], cached[2]
        try:
            from scripts.sync_google_beta import collect_events
            events, diagnostics = collect_events({code})
        except Exception as exc:
            events, diagnostics = [], [{"source_id": "GOOGLE_SHEETS", "status": "ERROR", "error": str(exc)}]
        google_cache[code] = (now, events, diagnostics)
        return events, diagnostics


def dedupe(events):
    result, seen = [], set()
    priority = {"CONFIRMED": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
    for event in sorted(events, key=lambda item: (item.get("from") or "", EVENT_ORDER.get(item.get("type"), 99), -priority.get(item.get("confidence"), 0))):
        key = (event.get("type"), event.get("from"), event.get("to"), str(event.get("before")), str(event.get("after")), event.get("location"), event.get("quantity"))
        if key not in seen:
            seen.add(key); result.append(event)
    return result


def prefer_miu_hub(events):
    """Keep the operating ledger when two sources describe the same calendar event."""
    authoritative = [event for event in events if event.get("source_family") == "MIU_HUB_SUPABASE"]
    keys = {(event.get("type"), (event.get("from") or "")[:10]) for event in authoritative}
    return [event for event in events if event.get("source_family") == "MIU_HUB_SUPABASE" or (event.get("type"), (event.get("from") or "")[:10]) not in keys]


def is_dropbox_snapshot_movement(event):
    """Monthly Dropbox comparisons show a changed state, not the actual move."""
    return (
        event.get("source_family") == "DROPBOX_COMMON_SALES"
        and event.get("type") in {"LOCATION_CHANGE", "DISCARDED"}
        and event.get("evidence", "").startswith("Dropbox 월별 입고 스냅샷 비교")
    )


def enforce_lifecycle(events, product):
    """Keep direct ledger events in the timeline and discard snapshot-only moves."""
    received = (product or {}).get("received_at")
    result = []
    for original in events:
        event = dict(original)
        if is_dropbox_snapshot_movement(event):
            continue
        if not received:
            result.append(event)
            continue
        inferred_snapshot = event.get("precision") == "RANGE" and event.get("source_family") == "DROPBOX_COMMON_SALES"
        if inferred_snapshot and (event.get("from") or "") < received:
            if event.get("to") and event["to"] > received:
                event["from"] = received
                event["evidence"] = event.get("evidence", "") + " · 공식 입고일 이전 구간 제외"
            else:
                continue
        result.append(event)
    precise = [event for event in result if event.get("precision") != "RANGE"]
    reconciled = []
    for event in result:
        inferred_snapshot = event.get("precision") == "RANGE" and event.get("source_family") == "DROPBOX_COMMON_SALES"
        comparison_to = event.get("to") or ""
        if comparison_to:
            boundary = date.fromisoformat(comparison_to)
            next_month = date(boundary.year + (boundary.month == 12), 1 if boundary.month == 12 else boundary.month + 1, 1)
            comparison_to = (next_month - timedelta(days=1)).isoformat()
        superseded = inferred_snapshot and any(
            exact.get("type") == event.get("type")
            and (event.get("from") or "") <= (exact.get("from") or "") <= comparison_to
            for exact in precise
        )
        if not superseded:
            reconciled.append(event)
    return sorted(reconciled, key=lambda item: (item.get("from") or "", EVENT_ORDER.get(item.get("type"), 99), item.get("to") or ""))


def fill_event_state(events):
    """Connect exact change records to the last known value without inventing facts."""
    current_price = None
    enriched = []
    for original in events:
        event = dict(original)
        if event.get("type") == "RECEIVED" and event.get("price") is not None:
            current_price = event["price"]
        elif event.get("type") == "PRICE_CHANGE":
            if event.get("before") is None and current_price is not None:
                event["before"] = current_price
            if event.get("after") is not None:
                current_price = event["after"]
        enriched.append(event)
    return enriched


def summarize(code, product, events):
    counts = {kind: sum(event.get("type") == kind for event in events) for kind in ("RECEIVED", "SOLD", "REFUND", "LOCATION_CHANGE", "PRICE_CHANGE", "DISCARDED")}
    location = (product or {}).get("location") or "현재 위치 미확인"
    description = (product or {}).get("description") or "상품 설명 미확인"
    pieces = [f"{description} 상품은 {location} 상태입니다."]
    if counts["RECEIVED"]:
        pieces.append("정식 입고 기록이 확인됩니다.")
    if counts["SOLD"] or counts["REFUND"]:
        pieces.append(f"판매 {counts['SOLD']}건, 환불 {counts['REFUND']}건이 확인됩니다.")
    if counts["LOCATION_CHANGE"] or counts["DISCARDED"]:
        pieces.append(f"위치·상태 변화 {counts['LOCATION_CHANGE'] + counts['DISCARDED']}건이 있습니다.")
    if counts["PRICE_CHANGE"]:
        pieces.append(f"가격 변경 {counts['PRICE_CHANGE']}건이 있습니다.")
    return " ".join(pieces), counts


def resolve_current_state(product, events):
    state = {"location": (product or {}).get("location"), "status": (product or {}).get("status"), "price": (product or {}).get("price"), "updated_at": (product or {}).get("updated_at")}
    if state["location"] == "폐기":
        state["status"] = "폐기"
        return state
    moves = [event for event in events if event.get("type") in {"LOCATION_CHANGE", "DISCARDED"} and event.get("after")]
    if moves:
        latest_move = max(moves, key=lambda event: event.get("from") or "")
        state["location"] = latest_move["after"]
        state["updated_at"] = latest_move.get("from") or state["updated_at"]
    transactions = [event for event in events if event.get("type") in {"SOLD", "REFUND"}]
    if transactions:
        latest = max(transactions, key=lambda event: (event.get("from") or "", event.get("source_file") or "", event.get("row") or 0, event.get("archive_first_seen_at") or ""))
        state["status"] = "판매됨" if latest.get("type") == "SOLD" else "보유"
    return state


def build_timeline(code, include_live_google=True):
    product, dropbox, meta = index_query(code)
    hub_product, hub_events = miu_hub_query(code)
    if hub_product:
        product = {**hub_product, **{key: value for key, value in (product or {}).items() if value is not None}}
    static = [event for event in static_payload().get("events", []) if event.get("barcode") == code]
    live_google, google_diagnostics = ([], []) if static or not include_live_google else google_events(code)
    archived = archived_events_for_barcode(code)
    current_events = mark_observed_events(dropbox + static + live_google + hub_events, archived)
    events = fill_event_state(enforce_lifecycle(dedupe(prefer_miu_hub(current_events + archived)), product))
    summary, counts = summarize(code, product, events)
    return {"barcode": code, "found": bool(product or events), "product": product, "current_state": resolve_current_state(product, events), "summary": summary, "counts": counts, "events": events, "count": len(events), "generated_at": meta.get("generated_at") or static_payload().get("generated_at"), "sales_coverage_end": meta.get("sales_coverage_end"), "google_diagnostics": google_diagnostics}


@app.get("/api/health")
def health():
    product_count = event_count = 0
    meta = {}
    if INDEX.exists():
        connection = sqlite3.connect(f"file:{INDEX.as_posix()}?mode=ro", uri=True)
        product_count = connection.execute("SELECT count(*) FROM products").fetchone()[0]
        event_count = connection.execute("SELECT count(*) FROM events").fetchone()[0]
        meta = dict(connection.execute("SELECT key,value FROM meta WHERE key IN ('generated_at','sales_coverage_end')"))
        connection.close()
    return {"status": "ok", "version": app.version, "mode": "FULL_BETA", "products": product_count, "events": event_count, **meta, "checked_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/barcodes/{barcode}/timeline")
def timeline(barcode: str):
    code = normalize(barcode)
    if not code:
        raise HTTPException(400, "barcode required")
    return build_timeline(code)


@app.post("/api/barcodes/batch")
def batch_timeline(request: BatchRequest):
    codes = list(dict.fromkeys(normalize(value) for value in request.barcodes if normalize(value)))
    if not codes:
        raise HTTPException(400, "at least one barcode required")
    results = [build_timeline(code, include_live_google=False) for code in codes]
    return {"requested": len(codes), "found": sum(item["found"] for item in results), "results": results}


@app.get("/api/sources")
def sources():
    return {"dropbox_index": str(INDEX), "dropbox_ready": INDEX.exists(), "static_google": static_payload().get("diagnostics", [])}

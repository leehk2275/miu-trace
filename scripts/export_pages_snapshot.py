from __future__ import annotations

import gzip
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from backend.app.main import MIU_HUB_INDEX, dedupe, enforce_lifecycle, fill_event_state, prefer_miu_hub, static_payload, summarize
from backend.app.main import resolve_current_state
from backend.app.event_archive import ARCHIVE, mark_observed_events

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "var" / "dropbox-index.sqlite"
OUTPUT = ROOT / "frontend" / "data" / "index"

def shard_name(barcode: str) -> str:
    first = (barcode[:1] or "_").upper()
    return first if first.isascii() and first.isalnum() else "_"


SHARDS = [str(value) for value in range(10)] + [chr(value) for value in range(ord("A"), ord("Z") + 1)] + ["_"]


def rows_for_shard(connection, table, shard):
    pattern = f"{shard}*" if shard != "_" else "[^0-9A-Za-z]*"
    return connection.execute(f"SELECT barcode,payload FROM {table} WHERE barcode GLOB ?", (pattern,))

def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(f"file:{INDEX.as_posix()}?mode=ro", uri=True)
    hub = sqlite3.connect(f"file:{MIU_HUB_INDEX.as_posix()}?mode=ro", uri=True) if MIU_HUB_INDEX.exists() else None
    archive = sqlite3.connect(f"file:{ARCHIVE.as_posix()}?mode=ro", uri=True) if ARCHIVE.exists() else None
    meta = dict(connection.execute("SELECT key,value FROM meta"))
    google_events: dict[str, list[dict]] = defaultdict(list)
    for event in static_payload().get("events", []):
        google_events[shard_name(event["barcode"])].append(event)
    for old in OUTPUT.glob("*.json.gz"):
        old.unlink()
    total = written = 0
    for name in SHARDS:
        products = {barcode: json.loads(payload) for barcode, payload in rows_for_shard(connection, "products", name)}
        if hub:
            for barcode, payload in rows_for_shard(hub, "products", name):
                hub_product = json.loads(payload)
                products[barcode] = {**hub_product, **{key: value for key, value in products.get(barcode, {}).items() if value is not None}}
        events: dict[str, list[dict]] = defaultdict(list)
        archived_events: dict[str, list[dict]] = defaultdict(list)
        for barcode, payload in rows_for_shard(connection, "events", name):
            events[barcode].append(json.loads(payload))
        if hub:
            for barcode, payload in rows_for_shard(hub, "events", name):
                events[barcode].append(json.loads(payload))
        for event in google_events.pop(name, []):
            events[event["barcode"]].append(event)
        if archive:
            for barcode, payload in rows_for_shard(archive, "archived_events", name):
                archived_events[barcode].append(json.loads(payload))
        for barcode, current in list(events.items()):
            events[barcode] = mark_observed_events(current, archived_events.get(barcode, [])) + archived_events.get(barcode, [])
        for barcode, stored in archived_events.items():
            if barcode not in events:
                events[barcode] = stored
        payload = {}
        for barcode in sorted(set(products) | set(events)):
            product = products.get(barcode)
            timeline = fill_event_state(enforce_lifecycle(dedupe(prefer_miu_hub(events.get(barcode, []))), product))
            summary, counts = summarize(barcode, product, timeline)
            payload[barcode] = {"barcode":barcode,"found":True,"product":product,"current_state":resolve_current_state(product,timeline),"summary":summary,"counts":counts,"events":timeline,"count":len(timeline),"generated_at":meta.get("generated_at"),"sales_coverage_end":meta.get("sales_coverage_end"),"google_diagnostics":[]}
        if not payload:
            continue
        with gzip.open(OUTPUT / f"{name}.json.gz", "wt", encoding="utf-8", compresslevel=9) as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        total += len(payload)
        written += 1
    connection.close()
    if hub:
        hub.close()
    if archive:
        archive.close()
    print(json.dumps({"products":total,"shards":written,"bytes":sum(p.stat().st_size for p in OUTPUT.glob('*.gz'))}))

if __name__ == "__main__":
    main()

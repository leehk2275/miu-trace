from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.app.event_archive import archive_events
from backend.app.main import INDEX, MIU_HUB_INDEX, static_payload


def main() -> None:
    events = list(static_payload().get("events", []))
    if INDEX.exists():
        with sqlite3.connect(f"file:{INDEX.as_posix()}?mode=ro", uri=True) as database:
            events.extend(json.loads(row[0]) for row in database.execute("SELECT payload FROM events"))
    if MIU_HUB_INDEX.exists():
        with sqlite3.connect(f"file:{MIU_HUB_INDEX.as_posix()}?mode=ro", uri=True) as database:
            events.extend(json.loads(row[0]) for row in database.execute("SELECT payload FROM events"))
    result = archive_events(events)
    print(json.dumps({"archive": result, "total_candidates": len(events)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

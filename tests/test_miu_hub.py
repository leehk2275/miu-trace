from backend.app.main import prefer_miu_hub, resolve_current_state
from backend.app.miu_hub import build_payload


def test_miu_hub_preserves_exact_move_order_and_initial_location():
    payload = build_payload(
        [{"barcode": "CR03727", "created_at": "2026-07-07T03:00:00+00:00", "product_name": "모자", "price": 44000, "location": "성수"}],
        [
            {"id": "a", "barcode": "CR03727", "scanned_at": "2026-07-16T01:47:28+00:00", "move_sessions": {"session_date": "2026-07-16", "from_location": "온라인", "to_location": "상수"}},
            {"id": "b", "barcode": "CR03727", "scanned_at": "2026-08-10T03:39:28+00:00", "move_sessions": {"session_date": "2026-08-10", "from_location": "상수", "to_location": "온라인"}},
            {"id": "c", "barcode": "CR03727", "scanned_at": "2026-08-24T03:16:49+00:00", "move_sessions": {"session_date": "2026-08-24", "from_location": "온라인", "to_location": "성수"}},
        ], [], [],
    )
    events = sorted(payload["events"], key=lambda event: event["from"])
    assert events[0]["type"] == "RECEIVED"
    assert events[0]["after"] == "온라인"
    assert [(event["before"], event["after"]) for event in events[1:]] == [("온라인", "상수"), ("상수", "온라인"), ("온라인", "성수")]
    assert resolve_current_state({"location": "온라인", "status": "보유"}, events)["location"] == "성수"


def test_miu_hub_wins_only_when_sources_describe_same_event_day():
    hub = {"type": "LOCATION_CHANGE", "from": "2026-08-24T12:00:00+09:00", "before": "온라인", "after": "성수", "source_family": "MIU_HUB_SUPABASE"}
    conflicting = {"type": "LOCATION_CHANGE", "from": "2026-08-24", "before": "상수", "after": "성수", "source_family": "DROPBOX_COMMON_SALES"}
    other_day = {"type": "LOCATION_CHANGE", "from": "2026-08-10", "before": "상수", "after": "온라인", "source_family": "DROPBOX_COMMON_SALES"}
    assert prefer_miu_hub([conflicting, other_day, hub]) == [other_day, hub]

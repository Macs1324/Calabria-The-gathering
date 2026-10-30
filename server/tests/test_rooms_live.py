"""Executable spec for live rooms: seats, persistence, WebSocket sync.

Seat tokens make identity server-side (the client never names its actor);
the room store survives restarts by replaying a per-room JSON log.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from calabria.api.main import create_app
from calabria.game.store import RoomStore

# --- store ---------------------------------------------------------------------


def test_room_codes_are_short_and_readable():
    store = RoomStore()
    code = store.create().id
    assert len(code) == 4
    assert code.isalnum() and code == code.upper()
    assert not set(code) & set("01IO")  # no look-alikes to misread aloud


def test_lookup_is_case_insensitive():
    store = RoomStore()
    code = store.create().id
    assert store.get(code.lower()) is store.get(code)


def test_join_issues_token_and_seats_player():
    store = RoomStore()
    room = store.create()
    token = store.join(room.id, "al")
    assert token
    assert room.state["players"] == ["al"]
    assert store.seat_of(room.id, token) == "al"


def test_rejoin_with_token_reclaims_seat():
    store = RoomStore()
    room = store.create()
    token = store.join(room.id, "al")
    assert store.join(room.id, "al", token=token) == token
    assert room.state["players"] == ["al"]


def test_taken_name_without_token_rejected():
    store = RoomStore()
    room = store.create()
    store.join(room.id, "al")
    with pytest.raises(ValueError, match="taken"):
        store.join(room.id, "al")


def test_name_must_be_sensible():
    store = RoomStore()
    room = store.create()
    for bad in ("", "   ", "x" * 25):
        with pytest.raises(ValueError, match="name"):
            store.join(room.id, bad)
    assert store.join(room.id, "  bea  ") and room.state["players"] == ["bea"]


def test_rooms_survive_restart(tmp_path):
    store = RoomStore(tmp_path)
    room = store.create()
    token = store.join(room.id, "al")
    store.apply(room.id, token, "card_play", {"card_id": "bear"})
    store.apply(room.id, token, "life_change", {"delta": -2})
    store.undo(room.id, token)

    reloaded = RoomStore(tmp_path)
    again = reloaded.get(room.id)
    assert again.state == room.state
    assert again.state["battlefield"][0]["card_id"] == "bear"
    assert again.state["life"]["al"] == 20
    assert reloaded.seat_of(room.id, token) == "al"


def test_unknown_token_rejected():
    store = RoomStore()
    room = store.create()
    with pytest.raises(PermissionError):
        store.apply(room.id, "nope", "life_change", {"delta": 1})


# --- REST ----------------------------------------------------------------------


def seat(c: TestClient, room_id: str, name: str) -> dict[str, str]:
    res = c.post(f"/rooms/{room_id}/join", json={"name": name})
    assert res.status_code == 200, res.text
    return {"X-Seat-Token": res.json()["token"]}


def test_rest_events_act_as_token_holder():
    c = TestClient(create_app())
    room_id = c.post("/rooms").json()["room_id"]
    al = seat(c, room_id, "al")
    res = c.post(f"/rooms/{room_id}/events", headers=al, json={"type": "life_change", "payload": {"delta": -4}})
    assert res.status_code == 200
    assert res.json()["life"]["al"] == 16


def test_rest_events_without_token_forbidden():
    c = TestClient(create_app())
    room_id = c.post("/rooms").json()["room_id"]
    res = c.post(f"/rooms/{room_id}/events", json={"type": "life_change", "payload": {"delta": 1}})
    assert res.status_code == 403


def test_rest_join_conflict_409():
    c = TestClient(create_app())
    room_id = c.post("/rooms").json()["room_id"]
    seat(c, room_id, "al")
    assert c.post(f"/rooms/{room_id}/join", json={"name": "al"}).status_code == 409


def test_rest_undo():
    c = TestClient(create_app())
    room_id = c.post("/rooms").json()["room_id"]
    al = seat(c, room_id, "al")
    c.post(f"/rooms/{room_id}/events", headers=al, json={"type": "life_change", "payload": {"delta": -4}})
    res = c.post(f"/rooms/{room_id}/undo", headers=al)
    assert res.status_code == 200
    assert res.json()["life"]["al"] == 20


# --- WebSocket -----------------------------------------------------------------


def test_ws_sends_view_on_connect_and_broadcasts_changes():
    with TestClient(create_app()) as c:
        room_id = c.post("/rooms").json()["room_id"]
        al = seat(c, room_id, "al")["X-Seat-Token"]
        bea = seat(c, room_id, "bea")["X-Seat-Token"]
        with c.websocket_connect(f"/rooms/{room_id}/ws?token={al}") as ws_al:
            first = ws_al.receive_json()
            assert first["kind"] == "view"
            assert first["you"] == "al"
            assert first["state"]["players"] == ["al", "bea"]
            assert first["online"] == ["al"]
            with c.websocket_connect(f"/rooms/{room_id}/ws?token={bea}") as ws_bea:
                assert ws_bea.receive_json()["online"] == ["al", "bea"]
                assert ws_al.receive_json()["online"] == ["al", "bea"]  # presence broadcast

                ws_bea.send_json({"op": "event", "type": "card_play", "payload": {"card_id": "bear"}})
                for ws in (ws_al, ws_bea):
                    view = ws.receive_json()
                    assert view["state"]["battlefield"][0]["controller"] == "bea"
                    assert view["log"][-1]["type"] == "card_play"
                    assert view["log"][-1]["actor"] == "bea"


def test_ws_error_goes_to_sender_only():
    with TestClient(create_app()) as c:
        room_id = c.post("/rooms").json()["room_id"]
        al = seat(c, room_id, "al")["X-Seat-Token"]
        with c.websocket_connect(f"/rooms/{room_id}/ws?token={al}") as ws:
            ws.receive_json()
            ws.send_json({"op": "event", "type": "card_tap", "payload": {"entry": 99, "tapped": True}})
            msg = ws.receive_json()
            assert msg["kind"] == "error"
            assert "99" in msg["detail"]


def test_ws_undo_op():
    with TestClient(create_app()) as c:
        room_id = c.post("/rooms").json()["room_id"]
        al = seat(c, room_id, "al")["X-Seat-Token"]
        with c.websocket_connect(f"/rooms/{room_id}/ws?token={al}") as ws:
            ws.receive_json()
            ws.send_json({"op": "event", "type": "life_change", "payload": {"delta": -5}})
            assert ws.receive_json()["state"]["life"]["al"] == 15
            ws.send_json({"op": "undo"})
            assert ws.receive_json()["state"]["life"]["al"] == 20


def test_ws_spectator_is_read_only():
    with TestClient(create_app()) as c:
        room_id = c.post("/rooms").json()["room_id"]
        seat(c, room_id, "al")
        with c.websocket_connect(f"/rooms/{room_id}/ws") as ws:
            assert ws.receive_json()["you"] is None
            ws.send_json({"op": "event", "type": "life_change", "payload": {"delta": 1}})
            assert ws.receive_json()["kind"] == "error"


def test_ws_unknown_room_closes():
    with TestClient(create_app()) as c, pytest.raises(WebSocketDisconnect):
        c.websocket_connect("/rooms/ZZZZ/ws").__enter__()


def test_corrupt_room_file_is_skipped(tmp_path):
    (tmp_path / "BAD1.json").write_text("{not json")
    store = RoomStore(tmp_path)
    assert store.get("BAD1") is None

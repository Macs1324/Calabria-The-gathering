"""Tier-0 game state: executable spec for the room event log.

The room is event-sourced: plays are accepted events, state is a fold over
the log. No rule enforcement beyond sanity (tier 0); strictness comes later.
"""

import pytest

from calabria.game.room import Event, Room, apply_event, fold, new_room


def test_new_room_starts_empty():
    state = new_room()
    assert state["players"] == []
    assert state["battlefield"] == []
    assert state["life"] == {}
    assert state["turn"] == {"number": 1, "player": None}
    assert state["phase"] == "main"


def test_join_adds_player_with_starting_life():
    state = apply_event(new_room(), Event("player_join", "al", {}, seq=0))
    assert state["players"] == ["al"]
    assert state["life"] == {"al": 20}
    assert state["turn"]["player"] == "al"


def test_join_duplicate_rejected():
    state = apply_event(new_room(), Event("player_join", "al", {}, seq=0))
    with pytest.raises(ValueError, match="already seated"):
        apply_event(state, Event("player_join", "al", {}, seq=1))


def test_play_without_seat_rejected():
    with pytest.raises(ValueError, match="not seated"):
        apply_event(new_room(), Event("card_play", "ghost", {"card_id": "x"}, seq=0))


def test_card_play_places_on_battlefield():
    state = new_room()
    state = apply_event(state, Event("player_join", "al", {}, seq=0))
    state = apply_event(state, Event("card_play", "al", {"card_id": "mulldrifter"}, seq=1))
    assert len(state["battlefield"]) == 1
    entry = state["battlefield"][0]
    assert entry["card_id"] == "mulldrifter"
    assert entry["controller"] == "al"
    assert entry["entry_seq"] == 1
    assert entry["tapped"] is False


def test_card_play_requires_card_id():
    state = apply_event(new_room(), Event("player_join", "al", {}, seq=0))
    with pytest.raises(ValueError, match="card_id"):
        apply_event(state, Event("card_play", "al", {}, seq=1))


def test_tap_targets_battlefield_entry():
    state = new_room()
    state = apply_event(state, Event("player_join", "al", {}, seq=0))
    state = apply_event(state, Event("card_play", "al", {"card_id": "forest"}, seq=1))
    state = apply_event(state, Event("card_tap", "al", {"entry": 1, "tapped": True}, seq=2))
    assert state["battlefield"][0]["tapped"] is True
    state = apply_event(state, Event("card_tap", "al", {"entry": 1, "tapped": False}, seq=3))
    assert state["battlefield"][0]["tapped"] is False


def test_tap_unknown_entry_rejected():
    state = apply_event(new_room(), Event("player_join", "al", {}, seq=0))
    with pytest.raises(ValueError, match="battlefield"):
        apply_event(state, Event("card_tap", "al", {"entry": 99, "tapped": True}, seq=1))


def test_tap_requires_tapped_flag():
    state = apply_event(new_room(), Event("player_join", "al", {}, seq=0))
    with pytest.raises(ValueError, match="tapped"):
        apply_event(state, Event("card_tap", "al", {"entry": 0}, seq=1))


def test_life_change_updates_own_life():
    state = apply_event(new_room(), Event("player_join", "al", {}, seq=0))
    state = apply_event(state, Event("life_change", "al", {"delta": -3}, seq=1))
    assert state["life"]["al"] == 17


def test_turn_end_passes_and_increments():
    state = new_room()
    state = apply_event(state, Event("player_join", "al", {}, seq=0))
    state = apply_event(state, Event("player_join", "bea", {}, seq=1))
    state = apply_event(state, Event("turn_end", "bea", {}, seq=2))
    assert state["turn"] == {"number": 2, "player": "al"}


def test_player_leave_removes_seat_and_cards():
    state = new_room()
    state = apply_event(state, Event("player_join", "al", {}, seq=0))
    state = apply_event(state, Event("player_join", "bea", {}, seq=1))
    state = apply_event(state, Event("card_play", "al", {"card_id": "isle"}, seq=2))
    state = apply_event(state, Event("player_leave", "al", {}, seq=3))
    assert state["players"] == ["bea"]
    assert state["battlefield"] == []
    assert "al" not in state["life"]


def test_unknown_event_type_rejected():
    with pytest.raises(ValueError, match="unknown event"):
        apply_event(new_room(), Event("monkey_business", "al", {}, seq=0))


def test_fold_rebuilds_identical_state():
    room = Room("test-room")
    room.apply("player_join", "al", {})
    room.apply("player_join", "bea", {})
    room.apply("card_play", "al", {"card_id": "mulldrifter"})
    room.apply("card_tap", "al", {"entry": 2, "tapped": True})
    room.apply("life_change", "bea", {"delta": -2})

    replayed = fold(room.events)
    assert replayed == room.state


def test_room_snapshot_is_room_state():
    room = Room("test-room")
    room.apply("player_join", "al", {})
    assert room.snapshot() == room.state

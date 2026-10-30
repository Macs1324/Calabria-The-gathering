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
    assert state["turn"] == {"number": 2, "player": "bea"}


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


# --- zones, tokens, counters (MVP game model) ---------------------------------


def seated(*players: str) -> list[Event]:
    return [Event("player_join", p, {}, seq=i) for i, p in enumerate(players)]


def build(events: list[Event]) -> dict:
    """Fold events, numbering seqs by position so tests read top to bottom."""
    return fold([Event(e.type, e.actor, e.payload, seq=i) for i, e in enumerate(events)])


def test_new_room_has_public_zones():
    state = new_room()
    for zone in ("battlefield", "graveyard", "exile", "command"):
        assert state[zone] == []


def test_card_play_records_owner_name_and_empty_counters():
    state = build([*seated("al"), Event("card_play", "al", {"card_id": "bolt", "name": "Lightning Bolt"})])
    (entry,) = state["battlefield"]
    assert entry["owner"] == "al"
    assert entry["name"] == "Lightning Bolt"
    assert entry["counters"] == {}
    assert entry["token"] is False


def test_card_play_into_other_zone():
    state = build([*seated("al"), Event("card_play", "al", {"card_id": "bolt", "zone": "graveyard"})])
    assert state["battlefield"] == []
    assert state["graveyard"][0]["card_id"] == "bolt"


def test_card_play_unknown_zone_rejected():
    with pytest.raises(ValueError, match="zone"):
        build([*seated("al"), Event("card_play", "al", {"card_id": "bolt", "zone": "moon"})])


def test_card_move_between_public_zones_resets_tap_and_counters():
    state = build(
        [
            *seated("al"),
            Event("card_play", "al", {"card_id": "bear"}),
            Event("card_tap", "al", {"entry": 1, "tapped": True}),
            Event("card_counter", "al", {"entry": 1, "kind": "+1/+1", "delta": 2}),
            Event("card_move", "al", {"entry": 1, "zone": "graveyard"}),
        ]
    )
    assert state["battlefield"] == []
    (entry,) = state["graveyard"]
    assert entry["entry_seq"] == 1
    assert entry["tapped"] is False
    assert entry["counters"] == {}


def test_card_move_to_hidden_zone_removes_card():
    for hidden in ("hand", "library"):
        state = build(
            [*seated("al"), Event("card_play", "al", {"card_id": "bear"}), Event("card_move", "al", {"entry": 1, "zone": hidden})]
        )
        assert all(state[z] == [] for z in ("battlefield", "graveyard", "exile", "command"))


def test_token_leaving_battlefield_ceases_to_exist():
    state = build(
        [
            *seated("al"),
            Event("card_play", "al", {"card_id": "goblin-token", "token": True}),
            Event("card_move", "al", {"entry": 1, "zone": "graveyard"}),
        ]
    )
    assert state["graveyard"] == []


def test_any_seated_player_may_move_opponents_card():
    state = build(
        [
            *seated("al", "bea"),
            Event("card_play", "al", {"card_id": "bear"}),
            Event("card_move", "bea", {"entry": 2, "zone": "exile"}),
        ]
    )
    assert state["exile"][0]["owner"] == "al"


def test_card_move_unknown_entry_rejected():
    with pytest.raises(ValueError, match="no card"):
        build([*seated("al"), Event("card_move", "al", {"entry": 42, "zone": "exile"})])


def test_counters_add_and_vanish_at_zero():
    events = [*seated("al"), Event("card_play", "al", {"card_id": "bear"})]
    state = build([*events, Event("card_counter", "al", {"entry": 1, "kind": "+1/+1", "delta": 3})])
    assert state["battlefield"][0]["counters"] == {"+1/+1": 3}
    state = build(
        [
            *events,
            Event("card_counter", "al", {"entry": 1, "kind": "+1/+1", "delta": 1}),
            Event("card_counter", "al", {"entry": 1, "kind": "+1/+1", "delta": -1}),
        ]
    )
    assert state["battlefield"][0]["counters"] == {}


def test_counter_requires_kind_and_integer_delta():
    events = [*seated("al"), Event("card_play", "al", {"card_id": "bear"})]
    with pytest.raises(ValueError, match="kind"):
        build([*events, Event("card_counter", "al", {"entry": 1, "delta": 1})])
    with pytest.raises(ValueError, match="delta"):
        build([*events, Event("card_counter", "al", {"entry": 1, "kind": "loyalty", "delta": 1.5})])


def test_card_control_hands_card_to_other_player():
    state = build(
        [
            *seated("al", "bea"),
            Event("card_play", "al", {"card_id": "bear"}),
            Event("card_control", "bea", {"entry": 2, "player": "bea"}),
        ]
    )
    entry = state["battlefield"][0]
    assert entry["controller"] == "bea"
    assert entry["owner"] == "al"


def test_card_control_requires_seated_target():
    with pytest.raises(ValueError, match="not seated"):
        build([*seated("al"), Event("card_play", "al", {"card_id": "bear"}), Event("card_control", "al", {"entry": 1, "player": "zed"})])


def test_untap_all_only_touches_actors_battlefield():
    state = build(
        [
            *seated("al", "bea"),
            Event("card_play", "al", {"card_id": "forest"}),
            Event("card_play", "bea", {"card_id": "island"}),
            Event("card_tap", "al", {"entry": 2, "tapped": True}),
            Event("card_tap", "bea", {"entry": 3, "tapped": True}),
            Event("untap_all", "al", {}),
        ]
    )
    tapped = {e["card_id"]: e["tapped"] for e in state["battlefield"]}
    assert tapped == {"forest": False, "island": True}


def test_turn_end_untaps_next_players_permanents_and_resets_phase():
    state = build(
        [
            *seated("al", "bea"),
            Event("card_play", "bea", {"card_id": "island"}),
            Event("card_tap", "bea", {"entry": 2, "tapped": True}),
            Event("phase_set", "al", {"phase": "combat"}),
            Event("turn_end", "al", {}),
        ]
    )
    assert state["turn"]["player"] == "bea"
    assert state["battlefield"][0]["tapped"] is False
    assert state["phase"] == "main"


def test_life_change_can_target_another_player():
    state = build([*seated("al", "bea"), Event("life_change", "al", {"delta": -3, "player": "bea"})])
    assert state["life"] == {"al": 20, "bea": 17}


def test_life_change_rejects_non_integer_delta():
    for bad in (1.5, True, "3"):
        with pytest.raises(ValueError, match="delta"):
            build([*seated("al"), Event("life_change", "al", {"delta": bad})])


def test_dice_roll_records_last_roll():
    state = build([*seated("al"), Event("dice_roll", "al", {"sides": 20, "result": 13})])
    assert state["last_roll"] == {"player": "al", "sides": 20, "result": 13}


def test_dice_roll_result_must_fit_die():
    with pytest.raises(ValueError, match="result"):
        build([*seated("al"), Event("dice_roll", "al", {"sides": 6, "result": 7})])


def test_game_reset_clears_board_and_restores_life():
    state = build(
        [
            *seated("al", "bea"),
            Event("card_play", "al", {"card_id": "bear"}),
            Event("life_change", "bea", {"delta": -7}),
            Event("turn_end", "al", {}),
            Event("game_reset", "bea", {"starting_life": 40, "first": "bea"}),
        ]
    )
    assert state["battlefield"] == []
    assert state["life"] == {"al": 40, "bea": 40}
    assert state["turn"] == {"number": 1, "player": "bea"}
    assert state["players"] == ["al", "bea"]


# --- Room: undo and dice --------------------------------------------------------


def test_room_undo_pops_own_last_event():
    room = Room("r")
    room.apply("player_join", "al", {})
    room.apply("card_play", "al", {"card_id": "bear"})
    room.undo("al")
    assert room.state["battlefield"] == []
    assert len(room.events) == 1
    assert room.state == fold(room.events)


def test_room_undo_refuses_someone_elses_action():
    room = Room("r")
    room.apply("player_join", "al", {})
    room.apply("player_join", "bea", {})
    room.apply("life_change", "bea", {"delta": -1})
    with pytest.raises(ValueError, match="bea"):
        room.undo("al")


def test_room_undo_never_unseats():
    room = Room("r")
    room.apply("player_join", "al", {})
    with pytest.raises(ValueError, match="nothing to undo"):
        room.undo("al")


def test_room_rolls_dice_when_result_missing():
    room = Room("r")
    room.apply("player_join", "al", {})
    room.apply("dice_roll", "al", {"sides": 6})
    assert 1 <= room.state["last_roll"]["result"] <= 6
    # the rolled value is in the log, so replays are deterministic
    assert room.events[-1].payload["result"] == room.state["last_roll"]["result"]


def test_player_leave_passes_turn_to_next_seat():
    state = build([*seated("al", "bea", "cy"), Event("turn_end", "al", {}), Event("player_leave", "bea", {})])
    assert state["turn"]["player"] == "cy"

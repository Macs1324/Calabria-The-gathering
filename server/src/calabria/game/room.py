"""Tier-0 game state: an event-sourced "digital playmat".

Plays are *events* the server accepts and folds into state; the log doubles as
replay and audit trail. No rule enforcement beyond sanity — strictness is a
later tier (see docs/architecture.md). A card exists for the server only once
it is scanned into play, so hand privacy is natural.

Battlefield entries are identified by the `seq` of the event that created them
(`entry_seq`), so taps can target duplicates of the same card.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

STARTING_LIFE = 20

# Event types accepted by apply_event. Tier 0 is deliberately loose.
# TODO(tier-1): structured phases, mana payment, combat declarations.


@dataclass(frozen=True)
class Event:
    type: str
    actor: str
    payload: dict[str, Any] = field(default_factory=dict)
    seq: int = 0


def new_room() -> dict[str, Any]:
    return {
        "players": [],
        "battlefield": [],
        "life": {},
        "turn": {"number": 1, "player": None},
        "phase": "main",
    }


def apply_event(state: dict[str, Any], event: Event) -> dict[str, Any]:
    """Return the state produced by applying `event` to `state` (pure)."""
    s = copy.deepcopy(state)  # rooms are tiny; correctness over cleverness
    t, actor, payload = event.type, event.actor, event.payload

    if t == "player_join":
        if actor in s["players"]:
            raise ValueError(f"{actor} already seated")
        s["players"].append(actor)
        s["life"][actor] = STARTING_LIFE
        if s["turn"]["player"] is None:
            s["turn"]["player"] = actor

    elif t == "player_leave":
        _require_seated(s, actor)
        s["players"].remove(actor)
        s["battlefield"] = [c for c in s["battlefield"] if c["controller"] != actor]
        s["life"].pop(actor, None)
        if s["turn"]["player"] == actor:
            s["turn"]["player"] = s["players"][0] if s["players"] else None

    elif t == "card_play":
        _require_seated(s, actor)
        card_id = payload.get("card_id")
        if not card_id:
            raise ValueError("card_play requires card_id")
        s["battlefield"].append(
            {
                "card_id": str(card_id),
                "controller": actor,
                "entry_seq": event.seq,
                "tapped": False,
            }
        )

    elif t == "card_tap":
        _require_seated(s, actor)
        if "tapped" not in payload:
            raise ValueError("card_tap requires tapped flag")
        entry = _battlefield_entry(s, payload.get("entry"))
        entry["tapped"] = bool(payload["tapped"])

    elif t == "life_change":
        _require_seated(s, actor)
        delta = payload.get("delta")
        if not isinstance(delta, (int, float)):
            raise ValueError("life_change requires numeric delta")
        s["life"][actor] = s["life"].get(actor, STARTING_LIFE) + delta

    elif t == "phase_set":
        _require_seated(s, actor)
        phase = payload.get("phase")
        if not phase or not isinstance(phase, str):
            raise ValueError("phase_set requires phase string")
        s["phase"] = phase

    elif t == "turn_end":
        _require_seated(s, actor)
        nxt = _next_player(s, s["turn"]["player"])
        s["turn"] = {"number": s["turn"]["number"] + 1, "player": nxt}

    else:
        raise ValueError(f"unknown event type: {t}")

    return s


def fold(events: list[Event]) -> dict[str, Any]:
    """Rebuild state from scratch by replaying the log in order."""
    state = new_room()
    for event in events:
        state = apply_event(state, event)
    return state


def _require_seated(state: dict[str, Any], actor: str) -> None:
    if actor not in state["players"]:
        raise ValueError(f"{actor} not seated")


def _battlefield_entry(state: dict[str, Any], entry_seq: Any) -> dict[str, Any]:
    for entry in state["battlefield"]:
        if entry["entry_seq"] == entry_seq:
            return entry
    raise ValueError(f"no battlefield entry {entry_seq!r}")


def _next_player(state: dict[str, Any], current: str | None) -> str | None:
    players = state["players"]
    if not players:
        return None
    if current not in players:
        return players[0]
    return players[(players.index(current) + 1) % len(players)]


class Room:
    """A mutable holder around the pure event fold (for the API layer)."""

    def __init__(self, room_id: str):
        self.id = room_id
        self.events: list[Event] = []
        self.state = new_room()

    def apply(self, event_type: str, actor: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = Event(type=event_type, actor=actor, payload=dict(payload or {}), seq=len(self.events))
        self.state = apply_event(self.state, event)
        self.events.append(event)
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.state)

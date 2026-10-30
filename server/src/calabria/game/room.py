"""Tier-0 game state: an event-sourced "digital playmat".

Plays are *events* the server accepts and folds into state; the log doubles as
replay and audit trail. No rule enforcement beyond sanity — strictness is a
later tier (see docs/architecture.md). A card exists for the server only once
it is scanned into a public zone, so hand privacy is natural: moving a card to
hand or library removes it from the state.

Cards are identified by the `seq` of the event that created them
(`entry_seq`), so actions can target duplicates of the same card. The id
survives zone changes.

Tier 0 trusts the table: any seated player may act on any card (removal,
steal effects); the log records who did what and `Room.undo` fixes misclicks.
"""

from __future__ import annotations

import copy
import random
import threading
from dataclasses import dataclass, field
from typing import Any

STARTING_LIFE = 20

PUBLIC_ZONES = ("battlefield", "graveyard", "exile", "command")
HIDDEN_ZONES = ("hand", "library")

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
        **{zone: [] for zone in PUBLIC_ZONES},
        "life": {},
        "turn": {"number": 1, "player": None},
        "phase": "main",
        "last_roll": None,
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
        return s

    if t not in _HANDLERS:
        raise ValueError(f"unknown event type: {t}")
    _require_seated(s, actor)
    _HANDLERS[t](s, actor, payload, event.seq)
    return s


def _player_leave(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    s["players"].remove(actor)
    for zone in PUBLIC_ZONES:
        s[zone] = [c for c in s[zone] if c["owner"] != actor]
    for entry in s["battlefield"]:  # stolen permanents go home with nobody: return control
        if entry["controller"] == actor:
            entry["controller"] = entry["owner"]
    s["life"].pop(actor, None)
    if s["turn"]["player"] == actor:
        s["turn"]["player"] = s["players"][0] if s["players"] else None


def _card_play(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    card_id = payload.get("card_id")
    if not card_id:
        raise ValueError("card_play requires card_id")
    zone = payload.get("zone", "battlefield")
    if zone not in PUBLIC_ZONES:
        raise ValueError(f"cannot play into zone {zone!r}")
    s[zone].append(
        {
            "card_id": str(card_id),
            "name": payload.get("name"),
            "owner": actor,
            "controller": actor,
            "entry_seq": seq,
            "tapped": bool(payload.get("tapped", False)),
            "counters": {},
            "token": bool(payload.get("token", False)),
        }
    )


def _card_tap(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    if "tapped" not in payload:
        raise ValueError("card_tap requires tapped flag")
    entry = _battlefield_entry(s, payload.get("entry"))
    entry["tapped"] = bool(payload["tapped"])


def _card_move(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    dest = payload.get("zone")
    if dest not in PUBLIC_ZONES + HIDDEN_ZONES:
        raise ValueError(f"cannot move to zone {dest!r}")
    zone, entry = _find_entry(s, payload.get("entry"))
    s[zone].remove(entry)
    if dest in HIDDEN_ZONES or (entry["token"] and dest != "battlefield"):
        return  # out of public view (or a token that ceased to exist)
    # A card changing zones is a new object: it forgets taps, counters, steals.
    entry.update(tapped=False, counters={}, controller=entry["owner"])
    s[dest].append(entry)


def _card_counter(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    kind, delta = payload.get("kind"), payload.get("delta")
    if not kind or not isinstance(kind, str):
        raise ValueError("card_counter requires counter kind")
    if not _is_int(delta):
        raise ValueError("card_counter requires integer delta")
    _, entry = _find_entry(s, payload.get("entry"))
    count = entry["counters"].get(kind, 0) + delta
    if count > 0:
        entry["counters"][kind] = count
    else:
        entry["counters"].pop(kind, None)


def _card_control(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    player = payload.get("player")
    _require_seated(s, player)
    entry = _battlefield_entry(s, payload.get("entry"))
    entry["controller"] = player


def _untap_all(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    _untap(s, actor)


def _life_change(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    delta = payload.get("delta")
    if not _is_int(delta):
        raise ValueError("life_change requires integer delta")
    player = payload.get("player", actor)
    _require_seated(s, player)
    s["life"][player] = s["life"].get(player, STARTING_LIFE) + delta


def _phase_set(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    phase = payload.get("phase")
    if not phase or not isinstance(phase, str):
        raise ValueError("phase_set requires phase string")
    s["phase"] = phase


def _turn_end(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    nxt = _next_player(s, s["turn"]["player"])
    s["turn"] = {"number": s["turn"]["number"] + 1, "player": nxt}
    s["phase"] = "main"
    if nxt is not None:
        _untap(s, nxt)  # the untap step, done for you


def _dice_roll(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    sides, result = payload.get("sides"), payload.get("result")
    if not _is_int(sides) or sides < 2:
        raise ValueError("dice_roll requires integer sides >= 2")
    if not _is_int(result) or not 1 <= result <= sides:
        raise ValueError(f"dice_roll result must be within 1..{sides}")
    s["last_roll"] = {"player": actor, "sides": sides, "result": result}


def _game_reset(s: dict[str, Any], actor: str, payload: dict[str, Any], seq: int) -> None:
    life = payload.get("starting_life", STARTING_LIFE)
    if not _is_int(life) or life < 1:
        raise ValueError("game_reset starting_life must be a positive integer")
    first = payload.get("first", s["players"][0])
    _require_seated(s, first)
    for zone in PUBLIC_ZONES:
        s[zone] = []
    s["life"] = {p: life for p in s["players"]}
    s["turn"] = {"number": 1, "player": first}
    s["phase"] = "main"
    s["last_roll"] = None


_HANDLERS = {
    "player_leave": _player_leave,
    "card_play": _card_play,
    "card_tap": _card_tap,
    "card_move": _card_move,
    "card_counter": _card_counter,
    "card_control": _card_control,
    "untap_all": _untap_all,
    "life_change": _life_change,
    "phase_set": _phase_set,
    "turn_end": _turn_end,
    "dice_roll": _dice_roll,
    "game_reset": _game_reset,
}


def fold(events: list[Event]) -> dict[str, Any]:
    """Rebuild state from scratch by replaying the log in order."""
    state = new_room()
    for event in events:
        state = apply_event(state, event)
    return state


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_seated(state: dict[str, Any], actor: Any) -> None:
    if actor not in state["players"]:
        raise ValueError(f"{actor} not seated")


def _untap(state: dict[str, Any], player: str) -> None:
    for entry in state["battlefield"]:
        if entry["controller"] == player:
            entry["tapped"] = False


def _find_entry(state: dict[str, Any], entry_seq: Any) -> tuple[str, dict[str, Any]]:
    for zone in PUBLIC_ZONES:
        for entry in state[zone]:
            if entry["entry_seq"] == entry_seq:
                return zone, entry
    raise ValueError(f"no card {entry_seq!r} in a public zone")


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
    """A mutable holder around the pure event fold (for the API layer).

    Impure bits live here, not in the fold: dice get their result before the
    event is logged (so replays are deterministic), and undo rewrites the log.
    A lock keeps the log and state consistent across API worker threads.
    """

    def __init__(self, room_id: str, events: list[Event] | None = None):
        self.id = room_id
        self.events: list[Event] = list(events or [])
        self.state = fold(self.events)
        self._lock = threading.RLock()

    def apply(self, event_type: str, actor: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        if event_type == "dice_roll" and "result" not in payload and _is_int(payload.get("sides")):
            payload["result"] = random.randint(1, max(payload["sides"], 1))
        with self._lock:
            event = Event(type=event_type, actor=actor, payload=payload, seq=len(self.events))
            self.state = apply_event(self.state, event)
            self.events.append(event)
            return self.snapshot()

    def undo(self, actor: str) -> Event:
        """Drop the latest event if `actor` made it; seats are never undone."""
        with self._lock:
            if not self.events or self.events[-1].type == "player_join":
                raise ValueError("nothing to undo")
            last = self.events[-1]
            if last.actor != actor:
                raise ValueError(f"last action was {last.actor}'s, not yours")
            self.events.pop()
            self.state = fold(self.events)
            return last

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self.state)

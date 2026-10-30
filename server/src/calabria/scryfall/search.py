"""Card name search over the local metadata store.

Manual entry is a first-class input: typing "light bo" must find Lightning
Bolt. The ~35k distinct names fit comfortably in memory, so search is a
ranked scan over normalized names (accents, punctuation and case folded) —
no extra dependency, ~30 ms per query over the full snapshot.

Ranking, best first: exact name, name prefix, a name word starting with the
query, every query word prefixing some name word (any order), substring.
Ties go to the shorter name (closer to what was typed).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", stripped.casefold()).strip()


class CardSearch:
    def __init__(self, cards: Iterable[tuple[str, str, str]]):
        """`cards` yields (card_id, name, set_code); the first id per name wins."""
        self._entries: list[tuple[str, list[str], dict[str, str]]] = []
        seen: set[str] = set()
        for card_id, name, set_code in cards:
            if name in seen:
                continue
            seen.add(name)
            norm = normalize(name)
            self._entries.append((norm, norm.split(), {"card_id": card_id, "name": name, "set_code": set_code}))

    def __len__(self) -> int:
        return len(self._entries)

    def query(self, text: str, *, limit: int = 8) -> list[dict[str, str]]:
        q = normalize(text)
        if not q:
            return []
        q_words = q.split()
        ranked: list[tuple[int, int, str, dict[str, str]]] = []
        for norm, words, card in self._entries:
            rank = _rank(q, q_words, norm, words)
            if rank is not None:
                ranked.append((rank, len(norm), card["name"], card))
        ranked.sort(key=lambda item: item[:3])
        return [dict(card) for *_, card in ranked[:limit]]


def _rank(q: str, q_words: list[str], norm: str, words: list[str]) -> int | None:
    if norm == q:
        return 0
    if norm.startswith(q):
        return 1
    if f" {q}" in f" {norm}":
        return 2
    if all(any(w.startswith(qw) for w in words) for qw in q_words):
        return 3
    if q in norm:
        return 4
    return None

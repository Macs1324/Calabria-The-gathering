"""Executable spec for card name search and card images.

Manual entry is a first-class input (the camera only pre-fills it), so search
has to forgive partial words, word order, accents and punctuation.
"""

from fastapi.testclient import TestClient

from calabria.api.main import create_app
from calabria.scryfall.cards import CardMetaStore
from calabria.scryfall.search import CardSearch, image_url

CDN = "https://cards.scryfall.io/art_crop/front/{a}/{b}/{id}.jpg?1"


def row(card_id: str, name: str, set_code: str = "lea") -> dict:
    return {"card_id": card_id, "name": name, "set_code": set_code, "art_crop_uri": CDN.format(a=card_id[0], b=card_id[1], id=card_id)}


ROWS = [
    row("b01", "Lightning Bolt"),
    row("b02", "Lightning Bolt", "m10"),  # second art, same card
    row("b03", "Lightning Helix"),
    row("b04", "Bolt Bend"),
    row("b05", "Lim-Dûl the Necromancer"),
    row("b06", "Boltwave"),
    row("b07", "Ball Lightning"),
    row("b08", "Bolt"),
]


def search() -> CardSearch:
    return CardSearch([(r["card_id"], r["name"], r["set_code"]) for r in ROWS])


def names(results: list[dict]) -> list[str]:
    return [r["name"] for r in results]


def test_results_are_deduped_by_name():
    assert names(search().query("lightning bolt")).count("Lightning Bolt") == 1


def test_exact_then_prefix_then_word_prefix_then_substring():
    # ties go to the shorter (closer) name
    assert names(search().query("bolt")) == ["Bolt", "Boltwave", "Bolt Bend", "Lightning Bolt"]


def test_shorter_name_wins_ties():
    s = CardSearch([("x1", "Emeritus of Conflict // Lightning Bolt", "sos"), ("x2", "Lightning Bolt", "lea")])
    assert names(s.query("light bo"))[0] == "Lightning Bolt"


def test_partial_words_in_any_order():
    assert names(search().query("light bo"))[0] == "Lightning Bolt"
    assert names(search().query("bolt light"))[0] == "Lightning Bolt"


def test_accents_and_punctuation_are_ignored():
    assert names(search().query("lim dul")) == ["Lim-Dûl the Necromancer"]


def test_empty_query_returns_nothing():
    assert search().query("   ") == []


def test_limit_caps_results():
    assert len(search().query("l", limit=2)) == 2


def test_image_url_swaps_cdn_version():
    art = CDN.format(a="b", b="0", id="b01")
    assert image_url(art, "normal") == "https://cards.scryfall.io/normal/front/b/0/b01.jpg?1"
    assert image_url(art, "small") == "https://cards.scryfall.io/small/front/b/0/b01.jpg?1"


# --- API -----------------------------------------------------------------------


def app_with_cards(tmp_path):
    store = CardMetaStore(tmp_path / "cards.db")
    store.upsert_many(ROWS)
    return create_app(meta_store=store)


def test_search_endpoint(tmp_path):
    c = TestClient(app_with_cards(tmp_path))
    res = c.get("/cards/search", params={"q": "helix"}).json()
    assert res["results"] == [{"card_id": "b03", "name": "Lightning Helix", "set_code": "lea"}]


def test_card_image_redirects_to_cdn(tmp_path):
    c = TestClient(app_with_cards(tmp_path))
    res = c.get("/cards/b01/image", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"].startswith("https://cards.scryfall.io/normal/")
    small = c.get("/cards/b01/image", params={"version": "small"}, follow_redirects=False)
    assert "/small/" in small.headers["location"]


def test_card_image_unknown_404(tmp_path):
    c = TestClient(app_with_cards(tmp_path))
    assert c.get("/cards/nope/image", follow_redirects=False).status_code == 404


def test_card_play_gets_name_from_metadata(tmp_path):
    c = TestClient(app_with_cards(tmp_path))
    room_id = c.post("/rooms").json()["room_id"]
    token = c.post(f"/rooms/{room_id}/join", json={"name": "al"}).json()["token"]
    snap = c.post(
        f"/rooms/{room_id}/events",
        headers={"X-Seat-Token": token},
        json={"type": "card_play", "payload": {"card_id": "b03"}},
    ).json()
    assert snap["battlefield"][0]["name"] == "Lightning Helix"

"""Spec for the card metadata store (SQLite) and bulk-row parsing."""

from calabria.scryfall.cards import CardMetaStore, parse_card_row

ART_ENTRY = {
    "id": "b2de32fd-7a63-411c-95b5-88b4cb0e47b1",
    "name": "Isle of Vigilance",
    "set": "neo",
    "collector_number": "277",
    "image_uris": {"art_crop": "https://cards.scryfall.io/art_crop/img/a noop.jpg"},
}


def test_parse_card_row_extracts_fields():
    row = parse_card_row(ART_ENTRY)
    assert row["card_id"] == "b2de32fd-7a63-411c-95b5-88b4cb0e47b1"
    assert row["name"] == "Isle of Vigilance"
    assert row["set_code"] == "neo"
    assert "art_crop" in row["art_crop_uri"]


def test_parse_card_row_skips_rows_without_art():
    assert parse_card_row({"id": "x", "name": "Hidden form", "set": "znr"}) is None


def test_parse_card_row_uses_front_face_art():
    entry = {
        "id": "dup-id",
        "name": "Bilskirnir // Hidden Home",
        "set": "kpw",
        "card_faces": [
            {
                "name": "Bilskirnir",
                "image_uris": {"art_crop": "https://cards.scryfall.io/front.jpg"},
            },
            {"name": "Hidden Home", "image_uris": {"art_crop": "https://cards.scryfall.io/back.jpg"}},
        ],
    }
    row = parse_card_row(entry)
    assert row is not None
    assert row["name"] == "Bilskirnir"
    assert row["art_crop_uri"].endswith("front.jpg")


def test_store_upsert_and_get(tmp_path):
    store = CardMetaStore(tmp_path / "cards.db")
    store.upsert_many(
        [
            {"card_id": "a", "name": "Mana Castle", "set_code": "big", "art_crop_uri": "u1"},
            {"card_id": "b", "name": "Pure area", "set_code": "big", "art_crop_uri": "u2"},
        ]
    )
    assert store.count() == 2
    row = store.get("a")
    assert row is not None
    assert row["name"] == "Mana Castle"
    assert store.get("missing") is None


def test_store_upsert_replaces_same_id(tmp_path):
    store = CardMetaStore(tmp_path / "cards.db")
    store.upsert_many([{"card_id": "a", "name": "old", "set_code": "s", "art_crop_uri": "u"}])
    store.upsert_many([{"card_id": "a", "name": "new", "set_code": "s", "art_crop_uri": "u2"}])
    assert store.count() == 1
    assert store.get("a")["art_crop_uri"] == "u2"


def test_store_all_iterates_rows(tmp_path):
    store = CardMetaStore(tmp_path / "cards.db")
    store.upsert_many(
        [
            {"card_id": f"c{i}", "name": f"card {i}", "set_code": "z", "art_crop_uri": f"u{i}"}
            for i in range(5)
        ]
    )
    rows = list(store.all())
    assert len(rows) == 5
    assert rows[0]["card_id"] in {f"c{i}" for i in range(5)}

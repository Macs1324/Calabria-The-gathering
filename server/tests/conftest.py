"""Shared fixtures.

Tests must never see a locally built card index: create_app() defaults to
CALABRIA_DATA_DIR (or ./data), so point it at an empty temp dir per test.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CALABRIA_DATA_DIR", str(data_dir))
    return data_dir

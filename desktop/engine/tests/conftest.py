"""Masaüstü test ortak ayarları: her test kendi geçici veri dizininde çalışır."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _data_dir(tmp_path_factory, monkeypatch):
    from bulutbelge_engine import settings

    veri = tmp_path_factory.mktemp("veri")
    monkeypatch.setenv("BULUTBELGE_DATA_DIR", str(veri))
    settings.VAULT.lock()
    yield
    settings.VAULT.lock()

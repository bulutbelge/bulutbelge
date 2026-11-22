from bulutbelge_core import amac
from bulutbelge_core.profiles import all_builtin


def test_every_purpose_suggests_an_existing_profile():
    ids = {p["id"] for p in all_builtin()}
    assert amac.purposes()
    for p in amac.purposes():
        assert p["profile"] in ids


def test_suggest_profile():
    assert amac.suggest_profile("yapay_zeka") == "musteri"
    assert amac.suggest_profile("denetim") == "denetci"
    assert amac.suggest_profile("bilinmeyen") is None


def test_resolve_zorunlu_ve_listeden():
    import pytest

    assert amac.resolve("denetim") == ("denetim", "Denetçiye / düzenleyiciye paylaşım")
    for bos in (None, "", "   "):
        with pytest.raises(ValueError, match="zorunlu"):
            amac.resolve(bos)
    with pytest.raises(ValueError, match="Bilinmeyen amaç"):
        amac.resolve("Avukat incelemesi")  # eski serbest metin
    with pytest.raises(ValueError, match="yalnızca 'diger'"):
        amac.resolve("denetim", "ek açıklama metni")
    with pytest.raises(ValueError, match="en az 10"):
        amac.resolve("diger", "kısa")
    pid, metin = amac.resolve("diger", "  Mahkeme   yazısına yanıt  ")
    assert pid == "diger" and metin == "Diğer — Mahkeme yazısına yanıt"

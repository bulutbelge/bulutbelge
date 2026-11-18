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

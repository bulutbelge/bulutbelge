"""Sektör kural takımları. Yalnızca sahte değerler."""

from datetime import date

from bulutbelge_core.detect import detect
from bulutbelge_core.extra_types import age_range, year_capped
from bulutbelge_core.profiles import all_builtin
from bulutbelge_core.rules import Rules


def takim(pid):
    return next(p for p in all_builtin() if p["id"] == pid)


def kurallar(pid):
    return Rules.from_dict(takim(pid))


def bulgular(text, pid):
    r = kurallar(pid)
    return {(f.type, f.value): r.replacement_for(f, ascii_only=False) for f in detect(text, r)}


def test_sektor_takimlari_listede_ve_gecerli():
    ids = [p["id"] for p in all_builtin()]
    assert ids[-4:] == ["saglik", "ik", "hukuk", "finans"]
    for pid in ids:
        kurallar(pid)  # kalıplar ve yöntemler geçerli


def test_yas_90_ve_ustu_ayri_anilmaz():
    bugun = date(2026, 11, 4)
    assert year_capped("01.01.1930", bugun) == "90+ yaş"
    assert year_capped("14.03.1987", bugun) == "1987"
    assert age_range("01.01.1930", bugun) == "90+ yaş"
    assert age_range("14.03.1987", bugun) == "30-39 yaş"


def test_saglik_yil_ve_bolge():
    r = kurallar("saglik")
    assert r.method_for("dogum_tarihi") == "yil" and r.method_for("adres") == "bolge"
    assert r.column_actions == {"yas": "yas"}
    b = bulgular("Doğum tarihi: 14.03.1987\nAdres: Caferağa Mah. Moda Cad. No:12 Kadıköy/İstanbul\n", "saglik")
    assert b[("dogum_tarihi", "14.03.1987")] == "1987"
    assert any(v == "Marmara Bölgesi" for k, v in b.items() if k[0] == "adres")


def test_hukuk_esas_karar_dosya_no():
    text = "Mahkememizin 2023/145 Esas sayılı, 2024/67 K. sayılı karar; Dosya No: 2022/9981 görülmüştür."
    degerler = {v for (t, v) in bulgular(text, "hukuk") if t == "ozel_kalip"}
    assert any("2023/145" in v for v in degerler)
    assert any("2024/67" in v for v in degerler)
    assert any("2022/9981" in v for v in degerler)


def test_finans_iban_son4():
    b = bulgular("IBAN: TR33 0006 1005 1978 6457 8413 26", "finans")
    assert list(b.values()) == ["**** 1326"]


def test_ik_maas_araligi_ve_sicil():
    r = kurallar("ik")
    assert r.types["tutar"].enabled and r.types["sicil_no"].enabled

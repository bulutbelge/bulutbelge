"""Kaçağa rağmen kaydetme. Belgeler ve numaralar sahtedir."""

import inspect
import json
import zipfile

import docx
import pytest

from bulutbelge_engine import ajan, journal, settings
from bulutbelge_engine.protocol import EngineError, handle_line


def _sahte_tc(ilk9: str) -> str:
    d = [int(c) for c in ilk9]
    d10 = ((sum(d[0:9:2]) * 7) - sum(d[1:8:2])) % 10
    d11 = (sum(d) + d10) % 10
    return f"{ilk9}{d10}{d11}"


TC = _sahte_tc("123456789")


def call(method, **params):
    resp = handle_line(json.dumps({"id": 1, "method": method, "params": params}))
    if "error" in resp:
        raise EngineError(resp["error"]["code"], resp["error"]["message"])
    return resp["result"]


def raw_log() -> str:
    p = settings.data_dir() / journal.LOG_FILE
    return p.read_text(encoding="utf-8") if p.exists() else ""


def kacakli_docx(path):
    """Görünen metinde TC var (maskelenir); taranmayan gizli bir parçada aynı TC kalır (kaçak)."""
    d = docx.Document()
    d.add_paragraph(f"TC Kimlik No: {TC}")
    d.save(path)
    with zipfile.ZipFile(path) as z:
        items = {n: z.read(n) for n in z.namelist()}
    items["customXml/item1.xml"] = f"<kayit><no>{TC}</no></kayit>".encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in items.items():
            z.writestr(n, data)
    return path


def test_izinsiz_kacakta_dosya_yazilmaz(tmp_path):
    src = kacakli_docx(tmp_path / "kacak.docx")
    hedef = tmp_path / "kacak_maskeli.docx"
    with pytest.raises(EngineError, match="Kaçak tespiti"):
        call("doc.mask", source=str(src), target=str(hedef))
    assert not hedef.exists()


def test_izinle_yazilir_turler_doner_gunluge_kacakla_girer(tmp_path):
    src = kacakli_docx(tmp_path / "kacak.docx")
    hedef = tmp_path / "kacak_maskeli.docx"
    r = call("doc.mask", source=str(src), target=str(hedef), accept_leak=True)
    assert hedef.exists()
    assert r["leaked"] == ["tc_kimlik"]
    assert any("Kaçağa rağmen kaydedildi" in w for w in r["warnings"])
    son = json.loads(raw_log().strip().splitlines()[-1])
    assert son["op"] == "maskeleme" and son["result"] == "kacakla" and son["error"] == "kacak:tc_kimlik"
    assert TC not in raw_log()  # değer günlüğe girmez


def test_izin_sonraki_cagriya_sizmaz(tmp_path):
    src = kacakli_docx(tmp_path / "kacak.docx")
    call("doc.mask", source=str(src), target=str(tmp_path / "bir.docx"), accept_leak=True)
    with pytest.raises(EngineError, match="Kaçak tespiti"):
        call("doc.mask", source=str(src), target=str(tmp_path / "iki.docx"))
    assert not (tmp_path / "iki.docx").exists()


def test_kacak_yoksa_sonuc_basarili(tmp_path):
    src = tmp_path / "temiz.docx"
    d = docx.Document()
    d.add_paragraph(f"TC Kimlik No: {TC}")
    d.save(src)
    r = call("doc.mask", source=str(src), target=str(tmp_path / "temiz_maskeli.docx"), accept_leak=True)
    assert "leaked" not in r
    assert json.loads(raw_log().strip().splitlines()[-1])["result"] == "basarili"


def test_accept_leak_dogru_yanlis_olmali(tmp_path):
    src = kacakli_docx(tmp_path / "kacak.docx")
    with pytest.raises(EngineError) as e:
        call("doc.mask", source=str(src), target=str(tmp_path / "x.docx"), accept_leak="evet")
    assert e.value.code == "invalid_params"


def test_ajan_yolu_kacak_iznini_gecirmez():
    """Ajan komutu ve MCP maskelemeyi kendi kurduğu parametrelerle çağırır; izin alanı yok."""
    kaynak = inspect.getsource(ajan)
    assert "accept_leak" not in kaynak and "kacak_izni" not in kaynak


def test_son_yapilanlar_kacak_turlerini_saklar_deger_saklamaz():
    """Geçmiş kaydı kaçağa rağmen kayıtta yalnızca tür kodlarını tutar; tür kodu dışı girdi atılır."""
    entry = {"path": "C:/x/a.docx", "target": "C:/x/a_maskeli.docx", "count": 1, "at": 1,
             "leaked": ["tc_kimlik", TC, "Adres; DROP", "tc_kimlik"]}
    out = settings.history_add({"entry": entry})
    item = next(r for r in out if r["target"].endswith("a_maskeli.docx"))
    assert item["leaked"] == ["tc_kimlik"]
    db = (settings.data_dir() / settings.HISTORY_DB_FILE).read_bytes()
    assert TC.encode() not in db


def test_son_yapilanlar_kacaksiz_kayitta_alan_yok():
    out = settings.history_add({"entry": {"path": "C:/x/b.docx", "target": "C:/x/b_maskeli.docx", "count": 2, "at": 2}})
    item = next(r for r in out if r["target"].endswith("b_maskeli.docx"))
    assert "leaked" not in item

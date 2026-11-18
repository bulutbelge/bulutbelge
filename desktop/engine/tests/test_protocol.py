import io
import json

from bulutbelge_engine import __version__
from bulutbelge_engine.protocol import handle_line, serve

def test_ping():
    assert handle_line('{"id": 1, "method": "ping"}') == {"id": 1, "result": "pong"}

def test_version():
    resp = handle_line('{"id": 2, "method": "version", "params": {}}')
    assert resp["result"]["engine"] == __version__

def test_unknown_method():
    resp = handle_line('{"id": 3, "method": "yok"}')
    assert resp["error"]["code"] == "unknown_method"

def test_invalid_json():
    assert handle_line("{bozuk")["error"]["code"] == "parse_error"

def test_serve_skips_blank_lines_and_answers_each_request():
    stdin = io.StringIO('{"id": 1, "method": "ping"}\n\n{"id": 2, "method": "ping"}\n')
    stdout = io.StringIO()
    serve(stdin, stdout)
    lines = [json.loads(l) for l in stdout.getvalue().splitlines()]
    assert [l["id"] for l in lines] == [1, 2]

def test_serve_accepts_utf8_bom_on_first_line():
    stdin = io.StringIO('\ufeff{"id": 1, "method": "ping"}\n')
    stdout = io.StringIO()
    serve(stdin, stdout)
    assert json.loads(stdout.getvalue())["result"] == "pong"

def test_rules_types_lists_builtin_types():
    resp = handle_line('{"id": 4, "method": "rules.types"}')
    keys = [t["key"] for t in resp["result"]]
    assert "tc_kimlik" in keys and "iban" in keys

def test_pdf_scan_reports_user_error_for_missing_file(tmp_path):
    req = json.dumps({"id": 5, "method": "doc.scan", "params": {"path": str(tmp_path / "yok.pdf")}})
    resp = handle_line(req)
    assert resp["error"] == {"code": "document", "message": "Dosya bulunamadı"}

def test_pdf_scan_rejects_bad_rules(tmp_path):
    req = json.dumps(
        {"id": 6, "method": "doc.scan", "params": {"path": "x.pdf", "rules": {"patterns": [{"name": "b", "pattern": "("}]}}}
    )
    assert handle_line(req)["error"]["code"] == "invalid_rules"

def test_pdf_page_and_rects(tmp_path):
    import pymupdf

    path = tmp_path / "a.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "E-posta: ali@ornek.com")
    doc.save(path)
    doc.close()

    scan = handle_line(json.dumps({"id": 1, "method": "doc.scan", "params": {"path": str(path)}}))["result"]
    x0, y0, x1, y1 = scan["findings"][0]["rects"][0]
    assert 72 < x0 < x1 and y0 < 72 < y1 + 2

    page = handle_line(json.dumps({"id": 2, "method": "doc.page", "params": {"path": str(path), "page": 1, "width": 400}}))
    res = page["result"]
    assert res["image"].startswith("data:image/png;base64,") and res["pages"] == 1
    assert (res["width"], res["height"]) == (595, 842)

def test_batch_plan_and_mask_with_manual_area(tmp_path):
    import pymupdf

    src = tmp_path / "klasor"
    src.mkdir()
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Gizli proje: Mavi Kartal")
    doc.save(src / "a.pdf")
    doc.close()

    plan = handle_line(json.dumps({"id": 1, "method": "batch.plan", "params": {"source_dir": str(src)}}))["result"]
    assert plan["target_dir"].endswith("klasor_maskeli") and len(plan["files"]) == 1
    f = plan["files"][0]

    req = {"source": f["source"], "target": f["target"], "make_dirs": True,
           "manual_areas": [{"page": 1, "rect": [60, 58, 400, 78]}]}
    res = handle_line(json.dumps({"id": 2, "method": "doc.mask", "params": req}))["result"]
    out = pymupdf.open(res["target"])
    assert "Mavi" not in out[0].get_text()
    out.close()

def test_batch_plan_rejects_target_inside_source(tmp_path):
    req = {"source_dir": str(tmp_path), "target_dir": str(tmp_path / "x")}
    assert handle_line(json.dumps({"id": 1, "method": "batch.plan", "params": req}))["error"]["code"] == "document"

def test_doc_formats_and_xml_scan(tmp_path):
    formats = handle_line(json.dumps({"id": 1, "method": "doc.formats"}))["result"]
    assert "xml" in formats["all"] and "jpg" in formats["gorsel"]
    path = tmp_path / "a.xml"
    path.write_text("<a><b>ayse@ornek.com.tr</b></a>", encoding="utf-8")
    scan = handle_line(json.dumps({"id": 2, "method": "doc.scan", "params": {"path": str(path)}}))["result"]
    assert scan["format"] == "metin"
    f = scan["findings"][0]
    assert scan["text"][f["span"][0]:f["span"][1]] == "ayse@ornek.com.tr"

def test_unsupported_extension_is_user_error(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"x")
    res = handle_line(json.dumps({"id": 1, "method": "doc.scan", "params": {"path": str(path)}}))
    assert res["error"]["code"] == "document"

def test_doc_text_returns_content_for_preview(tmp_path):
    path = tmp_path / "a.csv"
    path.write_bytes("ad;şehir\r\nAyşe;İzmir\r\n".encode("cp1254"))
    res = handle_line(json.dumps({"id": 1, "method": "doc.text", "params": {"path": str(path)}}))["result"]
    assert res["text"] == "ad;şehir\r\nAyşe;İzmir\r\n"

def test_word_scan_and_bytes(tmp_path):
    import docx

    d = docx.Document()
    d.add_paragraph("E-posta: ayse@example.com")
    path = tmp_path / "a.docx"
    d.save(path)
    scan = handle_line(json.dumps({"id": 1, "method": "doc.scan", "params": {"path": str(path)}}))["result"]
    assert scan["format"] == "word" and scan["findings"][0]["value"] == "ayse@example.com"
    data = handle_line(json.dumps({"id": 2, "method": "doc.bytes", "params": {"path": str(path)}}))["result"]["data"]
    assert data.startswith("UEsDB")  # ZIP imzası (PK..) base64'te

def test_mask_reports_when_saved_path_differs(tmp_path):
    # Mac bildirimi (TAKIP 1.36): seçilen yer ile yazılan yer farklıysa kullanıcıya söylenir.
    src = tmp_path / "a.txt"
    src.write_text("E-posta: ayse@ornek.com.tr", encoding="utf-8")

    def mask(target):
        req = {"source": str(src), "target": str(target)}
        return handle_line(json.dumps({"id": 1, "method": "doc.mask", "params": req}))["result"]

    first = mask(tmp_path / "kopya.txt")
    assert first["changed"] is None and first["target"] == str((tmp_path / "kopya.txt").resolve())
    # Kaydetme penceresinde var olan dosya seçildi: üzerine yazılmaz, yeni ad bildirilir.
    second = mask(tmp_path / "kopya.txt")
    assert second["target"].endswith("kopya_2.txt") and "üzerine yazılmadı" in second["changed"]
    assert (tmp_path / "kopya_2.txt").is_file()
    third = mask(tmp_path / "baska.pdf")
    assert third["target"].endswith("baska.txt") and ".txt uzantısıyla" in third["changed"]

def test_mask_permission_error_is_user_error(tmp_path, monkeypatch):
    from bulutbelge_engine import commands

    def denied(_params):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(commands, "_doc_mask", denied)
    req = {"source": str(tmp_path / "a.txt"), "target": str(tmp_path / "b.txt")}
    err = handle_line(json.dumps({"id": 1, "method": "doc.mask", "params": req}))["error"]
    assert err["code"] == "permission" and "Dosyalar ve Klasörler" in err["message"]

def test_sunucu_komutlari_yok_ve_maskeleme_yerelde_yapilir(tmp_path):
    """Karar (17 Kasım): masaüstü sunucuya bağlanmaz; `server.*` komutları yoktur, belge hesapsız ve yerelde işlenir."""
    for yontem in ("server.status", "server.connect", "server.disconnect", "server.sync", "server.login"):
        assert handle_line(json.dumps({"id": 1, "method": yontem}))["error"]["code"] == "unknown_method"
    belge = tmp_path / "a.txt"
    belge.write_text("TC: 10000000146", encoding="utf-8")
    sonuc = handle_line(json.dumps({"id": 2, "method": "doc.mask", "params": {"source": str(belge), "target": str(tmp_path / "b.txt")}}))
    assert "result" in sonuc and "10000000146" not in (tmp_path / "b.txt").read_text(encoding="utf-8")

def test_eml_scan_and_mask(tmp_path):
    from email.message import EmailMessage
    from pathlib import Path

    m = EmailMessage()
    m["From"] = "ayse@ornek.com.tr"
    m["Subject"] = "Selam"
    m.set_content("Merhaba")
    path = tmp_path / "a.eml"
    path.write_bytes(m.as_bytes())
    formats = handle_line(json.dumps({"id": 1, "method": "doc.formats"}))["result"]
    assert "eml" in formats["all"] and formats["eposta"] == ["eml"]
    scan = handle_line(json.dumps({"id": 2, "method": "doc.scan", "params": {"path": str(path)}}))["result"]
    assert scan["format"] == "metin"
    f = next(x for x in scan["findings"] if x["type"] == "eposta")
    assert scan["text"][f["span"][0]:f["span"][1]] == "ayse@ornek.com.tr"
    out = handle_line(json.dumps({"id": 3, "method": "doc.mask", "params": {"source": str(path), "target": str(tmp_path / "o.eml")}}))["result"]
    assert b"ayse@" not in Path(out["target"]).read_bytes()
    text = handle_line(json.dumps({"id": 4, "method": "doc.text", "params": {"path": str(path)}}))["result"]["text"]
    assert "Merhaba" in text

def test_metin_taramasi_ozel_nitelikli_uyari_verir():
    import json

    from bulutbelge_engine.protocol import handle_line

    yanit = handle_line(json.dumps({"id": 1, "method": "text.scan", "params": {"text": "Hastalığı kanser; sendika üyesi."}}))
    uyarilar = yanit["result"]["warnings"]
    assert uyarilar and all("KVKK m.6" in u for u in uyarilar)
    assert "kanser" not in json.dumps(uyarilar)

def test_udf_scan_and_mask(tmp_path):
    import zipfile
    from pathlib import Path

    metin = "Sahte dilekçe\nE-posta: ayse@ornek.com.tr\n"
    path = tmp_path / "a.udf"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("content.xml", f'<?xml version="1.0" encoding="UTF-8"?><template><content><![CDATA[{metin}]]></content></template>')
    formats = handle_line(json.dumps({"id": 1, "method": "doc.formats"}))["result"]
    assert "udf" in formats["all"] and formats["udf"] == ["udf"]
    scan = handle_line(json.dumps({"id": 2, "method": "doc.scan", "params": {"path": str(path)}}))["result"]
    assert scan["format"] == "metin"
    f = next(x for x in scan["findings"] if x["type"] == "eposta")
    assert scan["text"][f["span"][0]:f["span"][1]] == "ayse@ornek.com.tr"
    out = handle_line(json.dumps({"id": 3, "method": "doc.mask", "params": {"source": str(path), "target": str(tmp_path / "o.udf")}}))["result"]
    with zipfile.ZipFile(out["target"]) as z:
        assert b"ayse@" not in z.read("content.xml")

def test_batch_linkability_warns_without_values(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("Kişi-3 İzmir'de 12.03.2020 tarihinde görevliydi.", encoding="utf-8")
    b.write_text("Kişi-3 İzmir'e döndü.", encoding="utf-8")
    req = {"id": 1, "method": "batch.linkability", "params": {"paths": [str(a), str(b)]}}
    res = handle_line(json.dumps(req))["result"]
    assert res["duzey"] == "Yüksek" and res["uyari"]
    assert "İzmir" not in json.dumps(res, ensure_ascii=False) and "Kişi-3" not in json.dumps(res, ensure_ascii=False)
    one = handle_line(json.dumps({"id": 2, "method": "batch.linkability", "params": {"paths": [str(a)]}}))["result"]
    assert one == {"duzey": "Yok", "uyari": []}
    bad = handle_line(json.dumps({"id": 3, "method": "batch.linkability", "params": {"paths": "x"}}))
    assert bad["error"]["code"] == "invalid_params"

def test_flatten_param_is_forwarded_to_scan_and_mask(tmp_path, monkeypatch):
    import pymupdf

    from bulutbelge_engine import commands

    path = tmp_path / "duz.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "E-posta: ali@ornek.com")
    doc.save(path)
    doc.close()

    seen = {}
    real_scan, real_mask = commands.scan_pdf, commands.mask_pdf

    def spy_scan(*a, **k):
        seen["scan"] = k.get("flatten")
        return real_scan(*a, **k)

    def spy_mask(*a, **k):
        seen["mask"] = k.get("flatten")
        return real_mask(*a, **k)

    monkeypatch.setattr(commands, "scan_pdf", spy_scan)
    monkeypatch.setattr(commands, "mask_pdf", spy_mask)
    handle_line(json.dumps({"id": 1, "method": "doc.scan", "params": {"path": str(path)}}))
    assert seen["scan"] is False
    handle_line(json.dumps({"id": 2, "method": "doc.scan", "params": {"path": str(path), "flatten": True}}))
    assert seen["scan"] is True
    handle_line(json.dumps({"id": 3, "method": "doc.mask", "params": {
        "source": str(path), "target": str(tmp_path / "o.pdf"), "flatten": True}}))
    assert seen["mask"] is True

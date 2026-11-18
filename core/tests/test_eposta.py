from email import message_from_bytes
from email.message import EmailMessage
from pathlib import Path

import pytest

from bulutbelge_core.documents import is_supported, kind_of
from bulutbelge_core.eposta import mask_eml, preview_text, scan_eml
from bulutbelge_core.pdf import PdfError
from bulutbelge_core.rules import Rules

from fake_data import fake_iban, fake_tc

TC = fake_tc()
TC2 = fake_tc("987654321")
IBAN = fake_iban()


def _eml(tmp_path: Path, attach: bool = True, nested: bool = False) -> Path:
    m = EmailMessage()
    m["From"] = "Ayşe Örnek <ayse@ornek.com.tr>"
    m["To"] = "ali@ornek.com.tr"
    m["Subject"] = "Başvuru"
    m.set_content(f"Merhaba,\nTC kimlik no: {TC}\nIBAN: {IBAN}\n")
    m.add_alternative(f"<p>TC: {TC}</p>", subtype="html")
    if attach:
        m.add_attachment(f"Ek not\nTC: {TC2}\n".encode("utf-8"), maintype="text", subtype="plain", filename="ayse_ornek_notu.txt")
        m.add_attachment(b"\x00\x01binary", maintype="application", subtype="octet-stream", filename="gizli.bin")
    if nested:
        inner = EmailMessage()
        inner["From"] = "veli@ornek.com.tr"
        inner.set_content(f"TC: {TC2}")
        m.add_attachment(inner.as_bytes(), maintype="application", subtype="octet-stream", filename="iletilen.eml")
    p = tmp_path / "posta.eml"
    p.write_bytes(m.as_bytes())
    return p


def _all_text(data: bytes) -> str:
    msg = message_from_bytes(data)
    out = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        payload = part.get_payload(decode=True) or b""
        out.append(payload.decode("utf-8", "replace"))
        out.append(" ".join(str(v) for v in part.values()))
    return "\n".join(out)


def test_eml_is_supported():
    assert is_supported("a.eml") and kind_of("A.EML") == "eposta"
    assert not is_supported("a.msg")


def test_scan_finds_headers_body_and_attachment(tmp_path):
    scan = scan_eml(_eml(tmp_path), Rules.from_dict(None))
    types = {f.finding.type for f in scan.findings}
    assert {"eposta", "tc_kimlik", "iban"} <= types
    for f in scan.findings:
        if f.span:
            assert scan.text[f.span[0]:f.span[1]] == f.finding.value
    assert any(f.span is None and f.finding.value == TC2 for f in scan.findings)  # ek bulgusu
    assert any("taranamadı" in w for w in scan.warnings)  # bilinmeyen tür ek


def test_mask_removes_values_everywhere(tmp_path):
    src = _eml(tmp_path)
    counts: dict[str, int] = {}
    target, masked, warnings = mask_eml(src, tmp_path / "out.eml", Rules.from_dict(None), counts=counts)
    data = Path(target).read_bytes()
    text = _all_text(data)
    assert masked > 0 and counts.get("tc_kimlik", 0) >= 3
    for secret in (TC, TC2, "ayse@ornek", "ali@ornek", "ayse_ornek", "gizli.bin", "binary"):
        assert secret not in text and secret not in data.decode("utf-8", "replace")
    assert "ek_1.txt" in data.decode() and "ek_2.bin" in data.decode()
    assert any("silindi" in w for w in warnings)
    assert "Başvuru" in preview_text(target)  # yapı ve masumca metin korunur
    assert src.read_bytes().count(TC.encode()) >= 1  # orijinale dokunulmaz


def test_mask_nested_eml_attachment(tmp_path):
    target, _, _ = mask_eml(_eml(tmp_path, attach=False, nested=True), tmp_path / "o.eml", Rules.from_dict(None))
    data = Path(target).read_bytes()
    inner = next(p for p in message_from_bytes(data).walk() if (p.get_filename() or "").endswith(".eml"))
    assert TC2 not in inner.get_payload(decode=True).decode() and b"veli@" not in inner.get_payload(decode=True)


def test_excluded_finding_stays(tmp_path):
    src = _eml(tmp_path, attach=False)
    rules = Rules.from_dict(None)
    keep = next(f for f in scan_eml(src, rules).findings if f.finding.type == "eposta" and "ali@" in f.finding.value)
    target, _, _ = mask_eml(src, tmp_path / "o.eml", rules, excluded_ids={keep.id})
    assert "ali@ornek.com.tr" in message_from_bytes(Path(target).read_bytes())["To"]
    assert TC not in _all_text(Path(target).read_bytes())


def test_invalid_and_same_target(tmp_path):
    bad = tmp_path / "x.eml"
    bad.write_bytes(b"")
    with pytest.raises(PdfError):
        scan_eml(bad, Rules.from_dict(None))
    src = _eml(tmp_path, attach=False)
    with pytest.raises(PdfError):
        mask_eml(src, src, Rules.from_dict(None))


def test_docx_attachment_is_masked(tmp_path):
    import docx

    d = tmp_path / "ek.docx"
    doc = docx.Document()
    doc.add_paragraph(f"TC: {TC2}")
    doc.save(d)
    m = EmailMessage()
    m["Subject"] = "Ek"
    m.set_content("Merhaba")
    m.add_attachment(d.read_bytes(), maintype="application",
                     subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename="ek.docx")
    p = tmp_path / "d.eml"
    p.write_bytes(m.as_bytes())
    target, masked, _ = mask_eml(p, tmp_path / "o.eml", Rules.from_dict(None))
    att = next(x for x in message_from_bytes(Path(target).read_bytes()).walk() if x.get_filename())
    out = tmp_path / "cikti.docx"
    out.write_bytes(att.get_payload(decode=True))
    assert masked >= 1 and TC2 not in "\n".join(pp.text for pp in docx.Document(out).paragraphs)

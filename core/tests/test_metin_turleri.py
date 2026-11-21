"""Düz metin türleri (.log .md .json .tsv .ini .yaml .yml): taranır, maskelenir; JSON geçerli kalır."""

import json

import pytest

from bulutbelge_core.rules import Rules
from bulutbelge_core.textdoc import TEXT_EXTS, mask_text_doc, scan_text_doc

ORNEK = {
    ".log": "2026-11-18 INFO tc=10000000146\n",
    ".md": "# Not\nMüşteri TC 10000000146\n",
    ".json": '{"tc": "10000000146", "ad": "Ayşe Yılmaz"}\n',
    ".tsv": "ad\ttc\nAyşe Yılmaz\t10000000146\n",
    ".ini": "[kisi]\ntc = 10000000146\n",
    ".yaml": "tc: 10000000146\n",
    ".yml": "tc: 10000000146\n",
}


def test_yeni_uzantilar_tanimli():
    assert set(ORNEK) <= TEXT_EXTS


@pytest.mark.parametrize("uzanti", sorted(ORNEK))
def test_tara_ve_maskele(tmp_path, uzanti):
    kaynak = tmp_path / f"ornek{uzanti}"
    kaynak.write_text(ORNEK[uzanti], encoding="utf-8")
    tarama = scan_text_doc(kaynak, Rules.from_dict(None))
    assert any(b.finding.type == "tc_kimlik" for b in tarama.findings), uzanti
    hedef = tmp_path / f"ornek_maskeli{uzanti}"
    mask_text_doc(kaynak, hedef, Rules.from_dict(None))
    cikti = hedef.read_text(encoding="utf-8")
    assert "10000000146" not in cikti
    if uzanti == ".json":
        json.loads(cikti)

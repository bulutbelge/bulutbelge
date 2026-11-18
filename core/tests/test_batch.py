from pathlib import Path

import pytest

from bulutbelge_core.batch import default_target_dir, plan_folder
from bulutbelge_core.pdf import PdfError


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "belgeler"
    (root / "alt").mkdir(parents=True)
    for p in ("a.pdf", "notlar.odt", "alt/b.PDF", "alt/foto.jpg"):
        (root / p).write_bytes(b"%PDF-1.7 sahte")
    return root


def test_plan_keeps_structure_and_skips_unsupported(folder):
    target = default_target_dir(str(folder))
    assert target.endswith("belgeler_maskeli")
    plan = plan_folder(str(folder), target)
    assert [p.relative for p in plan] == ["a.pdf", str(Path("alt/b.PDF")), str(Path("alt/foto.jpg"))]
    assert plan[1].target == str(Path(target) / "alt" / "b_maskeli.PDF")


def test_not_recursive(folder):
    assert [p.relative for p in plan_folder(str(folder), default_target_dir(str(folder)), recursive=False)] == ["a.pdf"]


def test_target_inside_source_is_rejected(folder):
    with pytest.raises(PdfError):
        plan_folder(str(folder), str(folder / "cikti"))
    with pytest.raises(PdfError):
        plan_folder(str(folder), str(folder))


def test_missing_source(tmp_path):
    with pytest.raises(PdfError):
        plan_folder(str(tmp_path / "yok"), str(tmp_path / "x"))


def test_default_target_dir_increments_when_target_already_exists(folder):
    target1 = default_target_dir(str(folder))
    assert target1.endswith("belgeler_maskeli")
    Path(target1).mkdir()
    target2 = default_target_dir(str(folder))
    assert target2.endswith("belgeler_maskeli_2")
    Path(target2).mkdir()
    target3 = default_target_dir(str(folder))
    assert target3.endswith("belgeler_maskeli_3")


def test_default_target_dir_when_source_itself_is_masked(folder):
    masked_src = folder.parent / "belgeler_maskeli"
    masked_src.mkdir()
    target = default_target_dir(str(masked_src))
    assert target.endswith("belgeler_maskeli_2")


def test_plan_cleans_already_masked_file_stems_and_skips_masked_subfolders(folder):
    (folder / "duyuru_maskeli.pdf").write_bytes(b"%PDF-1.7 sahte")
    (folder / "duyuru_maskeli_2.pdf").write_bytes(b"%PDF-1.7 sahte")
    (folder / "alt_maskeli").mkdir(parents=True)
    (folder / "alt_maskeli" / "eski.pdf").write_bytes(b"%PDF-1.7 sahte")

    target = default_target_dir(str(folder))
    plan = plan_folder(str(folder), target)

    targets = [p.target for p in plan]
    # alt_maskeli altındaki dosyalar atlanmalı
    assert not any("alt_maskeli" in t for t in targets)
    # _maskeli_maskeli gibi mükerrer ekler olmamalı
    assert not any("_maskeli_maskeli" in t for t in targets)
    assert not any("_maskeli_2_maskeli" in t for t in targets)

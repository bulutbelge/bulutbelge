"""Klasörle toplu işlem: hangi dosya nereye yazılacak.

Kurallar (tasarım: "Masaüstü uygulaması > Ana ekran > Hedef"):
- Klasör yapısı hedefte korunur.
- Hedef, kaynağın kendisi ya da kaynağın içindeki bir klasör olamaz (aksi hâlde
  ikinci çalıştırmada maskeli kopyalar yeniden işlenirdi).
- Orijinallere dokunulmaz; hedefte aynı adda dosya varsa üzerine yazılmaz
  (bkz. pdf.unique_path, maskeleme sırasında uygulanır).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .documents import is_supported
from .pdf import PdfError

MAX_FILES = 2000


@dataclass
class PlannedFile:
    source: str
    target: str
    relative: str
    size: int


def default_target_dir(source_dir: str) -> str:
    """Varsayılan maskeli hedef klasörü belirler.

    Klasör daha önce maskelenmiş ve hedef dizin zaten mevcutsa (örn. klasor_maskeli),
    üzerine yazmak veya dosyaları içine yığmak yerine ardışık numarayla yeni klasör oluşturur:
    örn. klasor_maskeli_2, klasor_maskeli_3...
    """
    src = Path(source_dir).resolve()
    base_name = re.sub(r"(_maskeli(?:_\d+)?)+$", "", src.name)
    if not base_name:
        base_name = src.name
    base = src.with_name(f"{base_name}_maskeli")
    if not base.exists():
        return str(base)
    idx = 2
    while True:
        candidate = src.with_name(f"{base_name}_maskeli_{idx}")
        if not candidate.exists():
            return str(candidate)
        idx += 1


def plan_folder(source_dir: str, target_dir: str, recursive: bool = True) -> list[PlannedFile]:
    src = Path(source_dir).resolve()
    dst = Path(target_dir).resolve()
    if not src.is_dir():
        raise PdfError("Kaynak klasör bulunamadı")
    if dst == src or src in dst.parents:
        raise PdfError("Hedef klasör, kaynak klasörün kendisi ya da içinde olamaz")

    pattern = "**/*" if recursive else "*"
    all_files = sorted(p for p in src.glob(pattern) if p.is_file() and is_supported(p))
    if len(all_files) > MAX_FILES:
        raise PdfError(f"Klasörde {len(all_files)} belge var; tek seferde en fazla {MAX_FILES} işlenebilir")

    plan = []
    for f in all_files:
        rel = f.relative_to(src)
        # Kaynak klasörün altındaki daha önceki maskeleme çıktı alt klasörlerini (örn. alt_maskeli/) atla
        if any(re.search(r"(_maskeli(?:_\d+)?)+$", part) for part in rel.parts[:-1]):
            continue
        clean_stem = re.sub(r"(_maskeli(?:_\d+)?)+$", "", f.stem)
        target = dst / rel.parent / f"{clean_stem}_maskeli{f.suffix}"
        plan.append(PlannedFile(str(f), str(target), str(rel), f.stat().st_size))
    return plan

"""Ajan komut satırı kılavuzu (docs/AJAN-KOMUT-SATIRI.md'nin paketteki kopyası: kilavuz.md).

Kılavuz motorun içinde gelir; böylece kurulu uygulamada internet ya da repo olmadan
`bulutbelge kilavuz` ile okunur. Kaynak `docs/AJAN-KOMUT-SATIRI.md`; kopyalar
`desktop/scripts/kilavuz-esitle.py` ile eşitlenir (testler farkı yakalar).

Claude Code becerisi `skill/SKILL.md` de paketle gelir: `bulutbelge kilavuz --skill`.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

GUIDE_FILE = Path(__file__).with_name("kilavuz.md")
SKILL_FILE = Path(__file__).with_name("skill") / "SKILL.md"
PROMPT_START = "<!-- yonerge-basla -->"
PROMPT_END = "<!-- yonerge-bitis -->"


def guide_text() -> str:
    return GUIDE_FILE.read_text(encoding="utf-8")


def command_here() -> str:
    """Bu kurulumda ajan komutunun gerçek çağrılışı.

    PATH'te `bulutbelge` varsa kısa ad; paketli uygulamada motor exe'sinin tam yolu; geliştirmede
    `python -m bulutbelge_engine.cli`. Boşluklu yollar tırnaklanır.
    """
    if shutil.which("bulutbelge"):
        return "bulutbelge"
    exe = sys.executable
    quoted = f'"{exe}"' if " " in exe else exe
    if getattr(sys, "frozen", False):
        return quoted
    return f"{quoted} -m bulutbelge_engine.cli"


def _with_command(text: str, command: str | None) -> str:
    """Metindeki `bulutbelge <komut>` çağrıları, bu kurulumda çalışan gerçek komutla değiştirilir."""
    if not command or command == "bulutbelge":
        return text
    return re.sub(r"\bbulutbelge (?=(?:folders|scan|read|mask|kilavuz|mcp)\b)", lambda _m: command + " ", text)


def skill_text(command: str | None = None) -> str:
    """Claude Code beceri dosyası (SKILL.md); komut adı bu kuruluma göre yazılır."""
    return _with_command(SKILL_FILE.read_text(encoding="utf-8"), command)


def guide_prompt(command: str | None = None) -> str:
    """Kılavuzdaki "ajana verilecek hazır yönerge" bloğu (işaretçiler arası, kod çiti dahil değil)."""
    text = guide_text()
    start, end = text.find(PROMPT_START), text.find(PROMPT_END)
    if start < 0 or end < start:
        return ""
    block = text[start + len(PROMPT_START):end].strip()
    lines = block.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return _with_command("\n".join(lines).strip() + "\n", command)

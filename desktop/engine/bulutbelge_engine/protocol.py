"""Kabuk ile motor arasındaki satır bazlı JSON protokolü.

İstek:  {"id": 1, "method": "ping", "params": {}}
Yanıt:  {"id": 1, "result": ...}  ya da  {"id": 1, "error": {"code": "...", "message": "..."}}

stdout yalnızca protokol içindir. Günlükler stderr'e yazılır ve belge içeriği,
bulgu ya da orijinal değer içermez.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, TextIO

from . import __version__

Handler = Callable[[dict[str, Any]], Any]


class EngineError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _ping(_params: dict[str, Any]) -> str:
    return "pong"


def _version(_params: dict[str, Any]) -> dict[str, str]:
    from bulutbelge_core import __version__ as core_version

    return {"engine": __version__, "core": core_version, "python": sys.version.split()[0]}


def _lazy(name: str) -> Handler:
    # Belge kütüphaneleri ilk kullanımda yüklensin; motor hızlı açılsın.
    def call(params: dict[str, Any]) -> Any:
        from . import commands

        return getattr(commands, name)(params)

    return call


HANDLERS: dict[str, Handler] = {
    "ping": _ping,
    "version": _version,
    "rules.types": _lazy("rules_types"),
    "purposes.list": _lazy("purposes_list"),
    "doc.formats": _lazy("doc_formats"),
    "doc.scan": _lazy("doc_scan"),
    "doc.mask": _lazy("doc_mask"),
    "doc.page": _lazy("doc_page"),
    "doc.text": _lazy("doc_text"),
    "doc.bytes": _lazy("doc_bytes"),
    "doc.slides": _lazy("doc_slides"),
    "doc.sheets": _lazy("doc_sheets"),
    "batch.plan": _lazy("batch_plan"),
    "batch.linkability": _lazy("batch_linkability"),
    "rules.test": _lazy("rules_test"),
    "settings.get": _lazy("settings_get"),
    "settings.save": _lazy("settings_save"),
    "profiles.export": _lazy("profiles_export"),
    "profiles.import": _lazy("profiles_import"),
    "vault.create": _lazy("vault_create"),
    "vault.unlock": _lazy("vault_unlock"),
    "vault.save": _lazy("vault_save"),
    "vault.change_password": _lazy("vault_change_password"),
    "vault.lock": _lazy("vault_lock"),
    "vault.delete": _lazy("vault_delete"),
    "vault.pseudonyms": _lazy("vault_pseudonyms"),
    "vault.pseudonym_lookup": _lazy("vault_pseudonym_lookup"),
    "vault.pseudonym_restore_text": _lazy("vault_pseudonym_restore_text"),
    "vault.pseudonym_clear": _lazy("vault_pseudonym_clear"),
    "text.scan": _lazy("text_scan"),
    "allow.add": _lazy("allow_add"),
    "allow.list": _lazy("allow_list"),
    "allow.remove": _lazy("allow_remove"),
    "history.list": _lazy("history_list"),
    "history.add": _lazy("history_add"),
    "history.delete": _lazy("history_delete"),
    "history.clear": _lazy("history_clear"),
    "log.list": _lazy("log_list"),
    "log.verify": _lazy("log_verify"),
    "log.export": _lazy("log_export"),
    "agent.get": _lazy("agent_get"),
    "agent.save": _lazy("agent_save"),
    "agent.guide": _lazy("agent_guide"),
}


def handle_line(line: str) -> dict[str, Any]:
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        return {"id": None, "error": {"code": "parse_error", "message": "Geçersiz JSON"}}

    if not isinstance(request, dict):
        return {"id": None, "error": {"code": "invalid_request", "message": "İstek nesne olmalı"}}

    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    handler = HANDLERS.get(method) if isinstance(method, str) else None
    if handler is None:
        return {"id": req_id, "error": {"code": "unknown_method", "message": f"Bilinmeyen komut: {method}"}}
    if not isinstance(params, dict):
        return {"id": req_id, "error": {"code": "invalid_params", "message": "params nesne olmalı"}}


    try:
        return {"id": req_id, "result": handler(params)}
    except EngineError as exc:
        return {"id": req_id, "error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # noqa: BLE001 - motor çökmemeli, hata kabuğa dönmeli
        # Mesaj belge içeriği taşıyabilir; yalnızca hata türünü raporla.
        return {"id": req_id, "error": {"code": "internal", "message": type(exc).__name__}}


def serve(stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        line = line.lstrip("\ufeff").strip()
        if not line:
            continue
        stdout.write(json.dumps(handle_line(line), ensure_ascii=False) + "\n")
        stdout.flush()

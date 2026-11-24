"""Yerel MCP sunucusu (`bulutbelge mcp`): yalnızca standart giriş/çıkış (stdio).

Karar: docs/kararlar/2026-11-21-ajan-mcp-stdio.md. Ağ portu açmaz, hiçbir sunucuya bağlanmaz; ajan
aracı (Claude Code, Cursor vb.) bu komutu alt süreç olarak başlatır ve satır başına bir JSON-RPC 2.0
iletisi alışverişi yapar (MCP protokol sürümü 2025-06-18). Yeni bağımlılık yoktur; gereken iletiler
(initialize, notifications/initialized, ping, tools/list, tools/call) burada uygulanır.

Araçlar komut satırıyla AYNI iç işlevleri çağırır (ajan.py): aynı izin denetimi, aynı kural takımı
üst sınırı (K1), aynı işlem günlüğü. Ajana orijinal değer dönmez: scan yalnızca sayılar, read maskeli
metin, mask yalnızca özet. Ajan adı `BULUTBELGE_AJAN` ortam değişkeninden (istemci yapılandırması) ya
da istemcinin `clientInfo.name` değerinden alınır, `--ajan` ile aynı kuralla temizlenir.

stdout yalnızca MCP iletilerini taşır: kütüphanelerin olası çıktısı stderr'e yönlendirilir.
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
from typing import Any, Callable, TextIO

from . import __version__, ajan, journal
from .protocol import EngineError

PROTOCOL_VERSION = "2025-06-18"
AGENT_ENV = "BULUTBELGE_AJAN"

INSTRUCTIONS = (
    "BulutBelge kullanıcının bilgisayarındaki belgelerde kişisel veriyi gerçekten silerek maskeler. "
    "Kişisel veri içerebilecek bir belgede (sözleşme, dilekçe, bordro, fatura, kimlik, CV vb.) önce "
    "bulutbelge_scan ile değer görmeden bak, kullanıcıya maskeli okumayı (bulutbelge_read) öner; dosyayı "
    "başka yoldan doğrudan okuma. bulutbelge_mask yalnızca kullanıcı isteyince. İzin hatasında dur ve "
    "mesajı kullanıcıya ilet; maskeli yer tutucuları ([AD SOYAD], █████) doldurmaya çalışma."
)

_PATH = {"type": "string", "description": "Belgenin tam yolu (izinli klasörde olmalı)"}
_PROFILE = {
    "type": "string",
    "description": "Kural takımı kimliği; yalnızca ajan için atanan takım ya da ondan sıkısı. Genelde verme.",
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "bulutbelge_folders",
        "title": "İzinli klasörler",
        "description": "Ajanın çalışabileceği klasörleri ve maskeli kopya yazma iznini gösterir (kullanıcı uygulamada ayarlar).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "bulutbelge_scan",
        "title": "Belgeye bak (yalnızca sayılar)",
        "description": (
            "Belgeyi değiştirmeden tarar; DEĞER GÖSTERMEZ: veri türüne göre bulgu sayıları, sayfa sayısı ve "
            "uyarılar. Kişisel veri içerebilecek bir belgede ilk adım budur."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"path": _PATH, "profile": _PROFILE},
            "required": ["path"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "bulutbelge_read",
        "title": "Maskeli oku",
        "description": (
            "Belgenin MASKELİ metnini ve özetini döndürür; orijinal değerler dönmez. Belge geçici bir kopyada "
            "gerçekten maskelenir, metin o kopyadan çıkarılır."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"path": _PATH, "profile": _PROFILE},
            "required": ["path"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "bulutbelge_mask",
        "title": "Maskeli kopya yaz",
        "description": (
            "Maskeli kopyayı YENİ bir dosyaya yazar (kullanıcının yazma izni gerekir; kaynak belgeye ve var olan "
            "dosyaya dokunulmaz). Yalnızca özet döner. Kullanıcı istemeden çağırma."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": _PATH,
                "target": {"type": "string", "description": "Maskeli kopyanın yolu (varsayılan: kaynağın yanında _maskeli)"},
                "profile": _PROFILE,
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    },
]

# Hata kodu → komut satırındaki çıkış kodu (ajan aynı tabloyu kullanabilsin).
def _exit_code(code: str) -> int:
    from .cli import EXIT_ERROR, EXIT_LOG, EXIT_REFUSED, EXIT_USAGE

    if code == "log_unwritable":
        return EXIT_LOG
    if code in journal.REFUSALS or code == ajan.APP_NOT_INSTALLED:
        return EXIT_REFUSED
    return EXIT_USAGE if code in ("invalid_params", "no_data_dir") else EXIT_ERROR


class Server:
    def __init__(self) -> None:
        self.agent = ajan.clean_agent_name(os.environ.get(AGENT_ENV), default="") or "mcp"
        self.from_env = bool(os.environ.get(AGENT_ENV)) and self.agent != "mcp"

    # ---------- JSON-RPC ----------

    def handle(self, line: str) -> dict[str, Any] | None:
        """Bir satırı işler; yanıt ya da (bildirimse) None döndürür."""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return _error(None, -32700, "Geçersiz JSON")
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            if isinstance(msg, dict) and "method" not in msg and ("result" in msg or "error" in msg):
                return None  # istemcinin yanıtı: sunucu istek göndermediği için yok sayılır
            return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Geçersiz istek")
        method, mid, params = msg["method"], msg.get("id"), msg.get("params") or {}
        if "id" not in msg:
            return None  # bildirim (notifications/initialized, notifications/cancelled …): yanıt yok
        if not isinstance(params, dict):
            return _error(mid, -32602, "params nesne olmalı")
        handler: Callable[[dict[str, Any]], dict[str, Any]] | None = {
            "initialize": self._initialize,
            "ping": lambda _p: {},
            "tools/list": lambda _p: {"tools": TOOLS},
            "tools/call": self._call,
        }.get(method)
        if handler is None:
            return _error(mid, -32601, f"Bilinmeyen yöntem: {method}")
        try:
            return {"jsonrpc": "2.0", "id": mid, "result": handler(params)}
        except _ParamError as exc:
            return _error(mid, -32602, str(exc))

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        info = params.get("clientInfo")
        if not self.from_env and isinstance(info, dict) and info.get("name"):
            self.agent = ajan.clean_agent_name(info.get("name"), default="mcp")
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "bulutbelge", "title": "BulutBelge", "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    # ---------- araçlar ----------

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in {t["name"] for t in TOOLS}:
            raise _ParamError(f"Bilinmeyen araç: {name}")
        if not isinstance(args, dict):
            raise _ParamError("arguments nesne olmalı")
        # Her çağrı ayrı bağlamda: çağıran = ajan (adıyla), komut satırındaki gibi.
        return contextvars.copy_context().run(self._run_tool, name, args)

    def _run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        journal.CALLER.set(("ajan", self.agent))
        try:
            path, profile = _opt_str(args, "path"), _opt_str(args, "profile")
            if name == "bulutbelge_folders":
                data = ajan.folders()
                return _ok(json.dumps(data, ensure_ascii=False), data)
            if path is None:
                raise EngineError("invalid_params", "'path' gerekli")
            if name == "bulutbelge_scan":
                s = ajan.scan(path, profile)
                return _ok(ajan.format_scan(s), {"ok": True, "summary": s})
            if name == "bulutbelge_read":
                r = ajan.read(path, profile)
                return _ok(r["text"].rstrip("\n") + "\n\n" + ajan.format_summary(r["summary"]), {"ok": True, **r})
            r = ajan.mask(path, _opt_str(args, "target"), profile, self.agent)
            return _ok(ajan.format_summary(r["summary"]), {"ok": True, **r})
        except EngineError as exc:
            return _fail(exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - mesaj içerik taşıyabilir; yalnızca tür
            return _fail("internal", type(exc).__name__)


class _ParamError(Exception):
    pass


def _opt_str(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise EngineError("invalid_params", f"'{key}' metin olmalı")
    return value


def _ok(text: str, structured: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "structuredContent": structured, "isError": False}


def _fail(code: str, message: str) -> dict[str, Any]:
    exit_code = _exit_code(code)
    hint = " İzni aşmaya çalışma; mesajı kullanıcıya aynen ilet." if exit_code in (3, 4) else ""
    return {
        "content": [{"type": "text", "text": f"Hata ({code}): {message}{hint}"}],
        "structuredContent": {"ok": False, "code": code, "message": message, "exit_code": exit_code},
        "isError": True,
    }


def _error(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve(inp: TextIO, out: TextIO) -> None:
    server = Server()
    for line in inp:
        if not line.strip():
            continue
        resp = server.handle(line)
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out.flush()


def serve_stdio() -> None:
    """Süreç stdio'su üzerinde çalışır. fd 1 stderr'e çevrilir; MCP iletileri kopyalanmış tanıtıcıya yazılır.

    Böylece bir kütüphanenin (MuPDF, Tesseract) stdout'a yazdığı satır protokolü bozamaz.
    """
    sys.stdout.flush()
    out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", newline="\n")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdin.reconfigure(encoding="utf-8-sig")
    try:
        serve(sys.stdin, out)
    finally:
        out.close()

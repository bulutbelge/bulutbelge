"""PowerPoint önizlemesi: slaytları arayüzde çizmek için sade bir tarif.

Tarayıcıda PowerPoint çizen hazır ve güvenilir bir kütüphane yok; PyMuPDF de
sunumu slayt slayt değil, metin olarak döker. Bu yüzden her slayt için şunlar
çıkarılır ve arayüz bunları slaytın üzerine yerleştirir:

- kutuların konumu ve boyutu (slayt genişliğine/yüksekliğine oranla, %),
- metin: paragraflar, hizalama, yazı boyutu (pt), kalın/italik, renk,
- görseller (data URL), tablolar (hücre metinleriyle), arka plan rengi,
- konuşmacı notları.

Konumu slaytta yazmayan başlık/gövde kutuları (yer tutucu) konumunu slayt
düzeninden (layout) ya da asıl slayttan (master) alır. Tema renkleri, gölge,
animasyon, grafik ve SmartArt çizilmez; amaç birebir kopya değil, hangi
bilginin nerede olduğunu görmektir. Her paragrafın "birim" anahtarı, bulgularla
eşleşir (bkz. office.py).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from lxml import etree

from .office import A, P, POWERPOINT, R, _rels, open_zip, parse, slide_order, units

EMU_PER_PT = 12700
_MAX_IMAGE = 3 * 1024 * 1024
_DEFAULT_SIZE = {"title": 36.0, "ctrTitle": 40.0, "subTitle": 22.0, "body": 20.0}
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".bmp": "image/bmp"}


def _ph(sp: etree._Element) -> tuple[str | None, str | None]:
    ph = sp.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
    if ph is None:
        ph = sp.find(f"{P}nvPicPr/{P}nvPr/{P}ph")
    if ph is None:
        return None, None
    return ph.get("type", "body"), ph.get("idx")


def _xfrm(el: etree._Element) -> tuple[int, int, int, int] | None:
    x = el.find(f"{P}spPr/{A}xfrm")
    if x is None:
        x = el.find(f"{P}xfrm")
    if x is None:
        x = el.find(f"{P}grpSpPr/{A}xfrm")
    if x is None:
        return None
    off, ext = x.find(A + "off"), x.find(A + "ext")
    if off is None or ext is None:
        return None
    return int(off.get("x", 0)), int(off.get("y", 0)), int(ext.get("cx", 0)), int(ext.get("cy", 0))


def _placeholders(root: etree._Element) -> dict[tuple[str, str | None], tuple[int, int, int, int]]:
    out = {}
    for sp in root.iter(P + "sp"):
        t, idx = _ph(sp)
        box = _xfrm(sp)
        if t and box:
            out.setdefault((t, idx), box)
            out.setdefault((t, None), box)
    return out


def _color(el: etree._Element | None) -> str | None:
    if el is None:
        return None
    c = el.find(f"{A}solidFill/{A}srgbClr")
    return f"#{c.get('val')}" if c is not None and c.get("val") else None


def _paragraphs(owner: etree._Element, unit_of: dict[etree._Element, int], part: str, default_size: float) -> list[dict]:
    out = []
    for p in owner.iter(A + "p"):
        ppr = p.find(A + "pPr")
        runs = []
        for node in p:
            if node.tag in (A + "r", A + "fld"):
                rpr = node.find(A + "rPr")
                t = node.find(A + "t")
                size = rpr.get("sz") if rpr is not None else None
                runs.append(
                    {
                        "text": (t.text or "") if t is not None else "",
                        "size": int(size) / 100 if size else default_size,
                        "bold": rpr is not None and rpr.get("b") == "1",
                        "italic": rpr is not None and rpr.get("i") == "1",
                        "color": _color(rpr),
                    }
                )
            elif node.tag == A + "br":
                runs.append({"text": "\n", "size": default_size, "bold": False, "italic": False, "color": None})
        ui = unit_of.get(p)
        out.append(
            {
                "unit": f"{part}:{ui}" if ui is not None else None,
                "align": (ppr.get("algn") if ppr is not None else None) or "l",
                "level": int(ppr.get("lvl", 0)) if ppr is not None else 0,
                "runs": runs,
            }
        )
    return out


def _bg(*roots: etree._Element | None) -> str | None:
    for root in roots:
        if root is None:
            continue
        bg = root.find(f"{P}cSld/{P}bg/{P}bgPr")
        c = _color(bg)
        if c:
            return c
    return None


def slide_preview(path: str | os.PathLike) -> dict:
    with open_zip(Path(path), POWERPOINT) as z:
        names = set(z.namelist())
        pres = parse(z.read("ppt/presentation.xml"))
        size = pres.find(P + "sldSz")
        width = int(size.get("cx", 9144000)) if size is not None else 9144000
        height = int(size.get("cy", 6858000)) if size is not None else 6858000

        slides = []
        for part in slide_order(z):
            if part not in names:
                continue
            root = parse(z.read(part))
            # Liste canlı kalmalı: lxml öğe nesneleri ancak bir başvuru varken aynı kalır.
            slide_units = units(POWERPOINT, root)
            unit_of = {el: ui for ui, (el, _s) in enumerate(slide_units)}
            rels = _rels(z, part)
            layout = master = None
            layout_part = next((t for t in rels.values() if "slideLayouts/" in t), None)
            if layout_part and layout_part in names:
                layout = parse(z.read(layout_part))
                master_part = next((t for t in _rels(z, layout_part).values() if "slideMasters/" in t), None)
                if master_part and master_part in names:
                    master = parse(z.read(master_part))
            inherited = {}
            for r in (master, layout):  # düzen, asıl slaytı ezer
                if r is not None:
                    inherited.update(_placeholders(r))

            items = []
            tree = root.find(f"{P}cSld/{P}spTree")
            for el in tree.iter(P + "sp", P + "pic", P + "graphicFrame") if tree is not None else []:
                ph_type, idx = _ph(el)
                box = _xfrm(el)
                if box is None and ph_type:
                    box = inherited.get((ph_type, idx)) or inherited.get((ph_type, None))
                if not box:
                    continue
                x, y, cx, cy = box
                geo = {
                    "x": x / width * 100,
                    "y": y / height * 100,
                    "w": cx / width * 100,
                    "h": cy / height * 100,
                }
                if el.tag == P + "sp":
                    body = el.find(P + "txBody")
                    if body is None:
                        continue
                    default = _DEFAULT_SIZE.get(ph_type or "", 18.0)
                    anchor = body.find(A + "bodyPr")
                    items.append(
                        {
                            "kind": "text",
                            **geo,
                            "fill": _color(el.find(P + "spPr")),
                            "anchor": (anchor.get("anchor") if anchor is not None else None)
                            or ("ctr" if ph_type in ("title", "ctrTitle") else "t"),
                            "paragraphs": _paragraphs(body, unit_of, part, default),
                        }
                    )
                elif el.tag == P + "pic":
                    blip = el.find(f"{P}blipFill/{A}blip")
                    target = rels.get(blip.get(R + "embed")) if blip is not None else None
                    if target and target in names and z.getinfo(target).file_size <= _MAX_IMAGE:
                        mime = _MIME.get(Path(target).suffix.lower())
                        if mime:
                            data = base64.b64encode(z.read(target)).decode()
                            items.append({"kind": "image", **geo, "src": f"data:{mime};base64,{data}"})
                else:
                    tbl = el.find(f"{A}graphic/{A}graphicData/{A}tbl")
                    if tbl is None:
                        continue
                    rows = []
                    for tr in tbl.iter(A + "tr"):
                        rows.append([_paragraphs(tc, unit_of, part, 14.0) for tc in tr.iter(A + "tc")])
                    items.append({"kind": "table", **geo, "rows": rows})

            notes = []
            notes_part = next((t for t in rels.values() if "notesSlides/" in t), None)
            if notes_part and notes_part in names:
                nroot = parse(z.read(notes_part))
                note_units = units(POWERPOINT, nroot)
                n_unit = {el: ui for ui, (el, _s) in enumerate(note_units)}
                for sp in nroot.iter(P + "sp"):
                    if _ph(sp)[0] == "body" and sp.find(P + "txBody") is not None:
                        notes.extend(_paragraphs(sp.find(P + "txBody"), n_unit, notes_part, 12.0))
            slides.append({"part": part, "bg": _bg(root, layout, master) or "#ffffff", "items": items, "notes": notes})

    return {"width_pt": width / EMU_PER_PT, "height_pt": height / EMU_PER_PT, "slides": slides}


def slide_of_part(path: str | os.PathLike) -> dict[str, int]:
    """Parça → slayt numarası (notlar, slaytıyla aynı numarayı alır)."""
    with open_zip(Path(path), POWERPOINT) as z:
        out = {}
        for i, part in enumerate(slide_order(z), start=1):
            out[part] = i
            notes = next((t for t in _rels(z, part).values() if "notesSlides/" in t), None)
            if notes:
                out[notes] = i
    return out

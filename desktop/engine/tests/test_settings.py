import json

import pytest

from bulutbelge_engine import settings
from bulutbelge_engine.protocol import EngineError, handle_line


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BULUTBELGE_DATA_DIR", str(tmp_path))
    settings.VAULT.lock()
    yield tmp_path
    settings.VAULT.lock()


def call(method, **params):
    resp = handle_line(json.dumps({"id": 1, "method": method, "params": params}))
    if "error" in resp:
        raise EngineError(resp["error"]["code"], resp["error"]["message"])
    return resp["result"]


def test_default_settings_have_default_profile():
    s = call("settings.get")
    assert s["active"] == "musteri"  # ilk açılışta "Müşteriye" seçili
    assert [p["id"] for p in s["profiles"]] == ["varsayilan", "musteri", "denetci", "kurum_ici", "efatura", "saglik", "ik", "hukuk", "finans"]
    assert s["profiles"][0]["types"]["imza"]["enabled"] is True
    assert s["vault"] == {"exists": False, "unlocked": False}


def test_save_and_reload_profiles(data_dir):
    s = call("settings.get")
    custom = {**s["profiles"][0], "id": "musteri", "name": "Müşteriye gönderim", "whitelist": ["info@kurum.com.tr"]}
    call("settings.save", profiles=[s["profiles"][0], custom], active="musteri")
    again = call("settings.get")
    assert again["active"] == "musteri"
    assert again["profiles"][1]["whitelist"] == ["info@kurum.com.tr"]


def test_default_profile_cannot_be_removed():
    s = call("settings.get")
    other = {**s["profiles"][0], "id": "x", "name": "X"}
    with pytest.raises(EngineError):
        call("settings.save", profiles=[other], active="x")


def test_invalid_pattern_rejected_on_save():
    p = {**call("settings.get")["profiles"][0], "patterns": [{"name": "bozuk", "pattern": "("}]}
    with pytest.raises(EngineError) as e:
        call("settings.save", profiles=[p], active="varsayilan")
    assert e.value.code == "invalid_rules"


def test_vault_roundtrip_and_terms_not_plain_on_disk(data_dir):
    call("vault.create", password="cok-gizli-parola")
    call("vault.save", terms={"varsayilan": ["Ayşe Yılmaz", "Mavi Kartal", "Ayşe Yılmaz"]})
    raw = (data_dir / "terms.bbvault").read_bytes()
    assert b"Mavi" not in raw and "Ayşe".encode() not in raw

    call("vault.lock")
    assert call("settings.get")["vault"] == {"exists": True, "unlocked": False}
    with pytest.raises(EngineError) as e:
        call("vault.save", terms={})
    assert e.value.code == "vault_locked"

    terms = call("vault.unlock", password="cok-gizli-parola")["terms"]
    assert terms == {"varsayilan": ["Ayşe Yılmaz", "Mavi Kartal"]}


def test_wrong_password_and_weak_password():
    with pytest.raises(EngineError) as e:
        call("vault.create", password="kisa")
    assert e.value.code == "weak_password"
    call("vault.create", password="cok-gizli-parola")
    call("vault.lock")
    with pytest.raises(EngineError) as e:
        call("vault.unlock", password="yanlis-parola")
    assert e.value.code == "wrong_password"


def test_change_password_and_delete(data_dir):
    call("vault.create", password="ilk-parola-1")
    call("vault.save", terms={"varsayilan": ["Mavi Kartal"]})
    call("vault.change_password", password="yeni-parola-2")
    call("vault.lock")
    with pytest.raises(EngineError):
        call("vault.unlock", password="ilk-parola-1")
    assert call("vault.unlock", password="yeni-parola-2")["terms"]["varsayilan"] == ["Mavi Kartal"]
    call("vault.delete")
    assert not (data_dir / "terms.bbvault").exists()


def test_rules_test_highlights_custom_pattern():
    spans = call(
        "rules.test",
        text="Kod: PRJ-0042, ayse@ornek.com",
        rules={"patterns": [{"name": "Proje", "pattern": r"PRJ-\d{4}"}]},
    )
    assert [(s["type"], s["start"]) for s in spans] == [("ozel_kalip", 5), ("eposta", 15)]


def test_pseudonyms_live_in_vault_and_are_consistent(data_dir):
    doc = data_dir / "a.txt"
    doc.write_text("Ad Soyad: Ayşe Yılmaz\nToplantı: Mehmet Demir ve Ayşe Yılmaz\n", encoding="utf-8")
    rules = {"types": {"kisi_adi": {"enabled": True, "method": "takma_ad"}}}

    # Kasa kilitliyken takma ad kullanılamaz.
    with pytest.raises(EngineError) as e:
        call("doc.scan", path=str(doc), rules=rules)
    assert e.value.code == "vault_locked"

    call("vault.create", password="cok-gizli-parola")
    scan = call("doc.scan", path=str(doc), rules=rules)
    assert [f["replacement"] for f in scan["findings"]] == ["Kişi-1", "Kişi-2", "Kişi-1"]
    # Tarama kasaya yazmaz; maskeleme yazar.
    assert call("vault.pseudonyms")["counts"] == {}
    out = call("doc.mask", source=str(doc), target=str(data_dir / "b.txt"), rules=rules)
    assert (data_dir / "b.txt").read_text(encoding="utf-8") == "Ad Soyad: Kişi-1\nToplantı: Kişi-2 ve Kişi-1\n"
    assert out["masked"] == 3
    assert call("vault.pseudonyms")["counts"] == {"kisi_adi": 2}

    # Kilitleyip açınca tablo kalır; başka belgede aynı kişi aynı takma adı alır.
    call("vault.lock")
    call("vault.unlock", password="cok-gizli-parola")
    doc2 = data_dir / "c.txt"
    doc2.write_text("Sayın Mehmet Demir\n", encoding="utf-8")
    assert call("doc.scan", path=str(doc2), rules=rules)["findings"][0]["replacement"] == "Kişi-2"

    # Geri çevirme yalnızca kasa açıkken ve tek tek.
    assert call("vault.pseudonym_lookup", label="Kişi-1") == {"type": "kisi_adi", "value": "Ayşe Yılmaz"}
    with pytest.raises(EngineError):
        call("vault.pseudonym_lookup", label="Kişi-9")
    call("vault.lock")
    with pytest.raises(EngineError):
        call("vault.pseudonym_lookup", label="Kişi-1")
    # Kasa dosyasında değerler açık yazılmaz.
    assert "Ayşe" not in (data_dir / "terms.bbvault").read_text(encoding="utf-8")


def test_builtin_purpose_profiles_are_added_once(data_dir):
    s = call("settings.get")
    assert [p["name"] for p in s["profiles"]] == ["Varsayılan", "Müşteriye", "Denetçiye", "Kurum içine", "e-Fatura", "Sağlık", "İnsan kaynakları", "Hukuk / UYAP", "Finans"]
    denetci = next(p for p in s["profiles"] if p["id"] == "denetci")
    assert denetci["types"]["kisi_adi"] == {"enabled": True, "method": "bas_harf"}
    kurum = next(p for p in s["profiles"] if p["id"] == "kurum_ici")
    assert kurum["types"]["kisi_adi"]["enabled"] is False and kurum["types"]["tc_kimlik"]["enabled"] is True
    # Kullanıcı birini silip kaydederse geri gelmez.
    kept = [p for p in s["profiles"] if p["id"] != "denetci"]
    call("settings.save", profiles=kept, active="musteri")
    again = call("settings.get")
    assert "denetci" not in [p["id"] for p in again["profiles"]]
    assert again["active"] == "musteri"


def test_allow_list_stores_only_hash_and_filters_scan(data_dir):
    text = "Santral 0212 555 12 34, cep 0532 123 45 67"
    found = call("text.scan", text=text)["findings"]
    assert len(found) == 2
    items = call("allow.add", values=["0212 555 12 34"], type="telefon")
    assert [i["type_label"] for i in items] == ["Telefon"]
    raw = (data_dir / settings.ALLOW_FILE).read_text(encoding="utf-8")
    # Değer değil, yalnızca özeti (rastgele özette kısa rakam dizileri geçebilir; tam numara aranır).
    assert "2125551234" not in raw and "555 12 34" not in raw
    found = call("text.scan", text=text)["findings"]
    assert [f["value"] for f in found] == ["0532 123 45 67"]
    assert call("allow.remove", id=items[0]["id"]) == []
    assert len(call("text.scan", text=text)["findings"]) == 2


def test_history_sqlite_database_crud(data_dir):
    assert call("history.list") == []
    entry1 = {
        "path": "/tmp/a.pdf",
        "target": "/tmp/a_maskeli.pdf",
        "count": 4,
        "at": 1700000001000,
        "profileName": "Müşteriye",
        "byType": [{"type": "kisi_adi", "label": "Kişi adı", "count": 2, "methodLabel": "Etiket"}],
    }
    entry2 = {
        "path": "/tmp/b.docx",
        "target": "/tmp/b_maskeli.docx",
        "count": 7,
        "at": 1700000002000,
        "profileName": "Denetçiye",
    }
    res = call("history.add", entries=[entry1, entry2])
    assert (data_dir / settings.HISTORY_DB_FILE).exists()
    assert [r["target"] for r in res] == ["/tmp/b_maskeli.docx", "/tmp/a_maskeli.pdf"]
    assert res[1]["byType"] == [{"type": "kisi_adi", "label": "Kişi adı", "count": 2, "methodLabel": "Etiket"}]

    after_del = call("history.delete", target="/tmp/b_maskeli.docx")
    assert [r["target"] for r in after_del] == ["/tmp/a_maskeli.pdf"]

    assert call("history.clear") == []
    assert call("history.list") == []


def test_history_folder_grouping_and_multi_delete(data_dir):
    assert call("history.list") == []
    folder_entries = [
        {
            "path": "/data/test/file1.txt",
            "target": "/data/test_maskeli/file1.txt",
            "count": 3,
            "at": 1700000003000,
            "folderName": "test_maskeli",
            "folderRoot": "/data/test_maskeli",
        },
        {
            "path": "/data/test/file2.txt",
            "target": "/data/test_maskeli/file2.txt",
            "count": 5,
            "at": 1700000004000,
            "folderName": "test_maskeli",
            "folderRoot": "/data/test_maskeli",
        },
    ]
    res = call("history.add", entries=folder_entries)
    assert len(res) == 2
    assert res[0]["folderName"] == "test_maskeli"
    assert res[0]["folderRoot"] == "/data/test_maskeli"

    # Multi-target delete
    remaining = call("history.delete", targets=["/data/test_maskeli/file1.txt", "/data/test_maskeli/file2.txt"])
    assert remaining == []



def test_eski_surumden_kalan_yonetilen_alani_yok_sayilir_ve_yazilmaz(data_dir):
    s = call("settings.get")
    eski = {"version": 1, "active": "musteri", "profiles": [{**p, "removed_types": ["eposta"]} for p in s["profiles"]], "seeded": True, "yonetilen": True}
    (data_dir / settings.SETTINGS_FILE).write_text(json.dumps(eski), encoding="utf-8")
    okunan = call("settings.get")
    assert "yonetilen" not in okunan and all("removed_types" not in p for p in okunan["profiles"])
    call("settings.save", profiles=okunan["profiles"], active="musteri")
    kayit = json.loads((data_dir / settings.SETTINGS_FILE).read_text(encoding="utf-8"))
    assert "yonetilen" not in kayit
    # Eski sürümde panelin editlenemez yaptığı takımlar artık düzenlenip kaydedilebilir.
    call("settings.save", profiles=okunan["profiles"], active="denetci")
    assert call("settings.get")["active"] == "denetci"


def test_pseudonym_scope_per_document(data_dir):
    rules = {"types": {"kisi_adi": {"enabled": True, "method": "takma_ad"}}, "pseudonym_scope": "belge"}
    shared = {"types": rules["types"]}
    call("vault.create", password="cok-gizli-parola")
    a, b = data_dir / "a.txt", data_dir / "b.txt"
    a.write_text("Ad Soyad: Ayşe Yılmaz ve Ayşe Yılmaz\n", encoding="utf-8")
    b.write_text("Sayın Ayşe Yılmaz\n", encoding="utf-8")
    call("doc.mask", source=str(a), target=str(data_dir / "a2.txt"), rules=rules)
    call("doc.mask", source=str(b), target=str(data_dir / "b2.txt"), rules=rules)
    assert (data_dir / "a2.txt").read_text(encoding="utf-8") == "Ad Soyad: Kişi-1 ve Kişi-1\n"
    assert (data_dir / "b2.txt").read_text(encoding="utf-8") == "Sayın Kişi-2\n"
    assert call("vault.pseudonym_lookup", label="Kişi-2")["value"] == "Ayşe Yılmaz"
    # Kapsam verilmezse mevcut davranış: ilk numara yeniden kullanılır.
    assert call("doc.scan", path=str(b), rules=shared)["findings"][0]["replacement"] == "Kişi-1"


def test_profile_export_has_no_terms_or_whitelist():
    call("vault.create", password="cok-gizli-parola")
    call("vault.save", terms={"varsayilan": ["Mavi Kartal"]})
    s = call("settings.get")
    p = {**s["profiles"][0], "whitelist": ["sahte@ornek.test"], "patterns": [{"name": "Dosya", "pattern": r"DSY-\d{4}"}]}
    call("settings.save", profiles=[p, *s["profiles"][1:]], active="varsayilan")
    pack = call("profiles.export")
    text = json.dumps(pack, ensure_ascii=False)
    assert "Mavi" not in text and "sahte@ornek.test" not in text and "terms" not in text
    assert pack["kind"] == "bulutbelge-profiller" and len(pack["profiles"]) == 9
    assert pack["profiles"][0]["patterns"][0]["pattern"] == r"DSY-\d{4}"
    assert [x["id"] for x in call("profiles.export", ids=["musteri"])["profiles"]] == ["musteri"]


def test_profile_import_adds_without_overwriting():
    pack = call("profiles.export", ids=["musteri"])
    pack["profiles"][0]["terms"] = ["Gizli Ad"]
    pack["profiles"][0]["whitelist"] = ["x@ornek.test"]
    r = call("profiles.import", data=json.dumps(pack))
    assert r["imported"] == ["musteri_1"]
    added = r["profiles"][-1]
    assert added["name"].endswith("(içe aktarılan)") and added["whitelist"] == []
    assert "terms" not in added
    assert r["active"] == "musteri"
    assert len([p for p in call("settings.get")["profiles"] if p["id"] == "musteri"]) == 1


@pytest.mark.parametrize("bad", ["{", "[]", '{"kind": "baska"}', '{"kind": "bulutbelge-profiller", "version": 1, "profiles": []}'])
def test_profile_import_rejects_bad_pack(bad):
    with pytest.raises(EngineError) as e:
        call("profiles.import", data=bad)
    assert e.value.code == "invalid_pack"


def test_profile_import_rejects_invalid_pattern():
    pack = call("profiles.export", ids=["musteri"])
    pack["profiles"][0]["id"] = "yeni"
    pack["profiles"][0]["patterns"] = [{"name": "bozuk", "pattern": "("}]
    with pytest.raises(EngineError) as e:
        call("profiles.import", data=pack)
    assert e.value.code == "invalid_rules"
    assert all(p["id"] != "yeni" for p in call("settings.get")["profiles"])


def test_history_does_not_store_person_names_in_paths(data_dir):
    """TAKIP 1.60: dosya adı ve yoldaki kişi adı history.db'ye yazılmaz (yalnızca sahte adlar)."""
    entry = {
        "path": "/home/Ahmet Yılmaz/Ayşe Demir kira.pdf",
        "target": "/home/Ahmet Yılmaz/kisi_maskeli.pdf",
        "count": 1,
        "at": 1700000003000,
        "folderName": "Ahmet Yılmaz_maskeli",
    }
    res = call("history.add", entry=entry)
    assert res[0]["path"] == "/home/[kişi]/[kişi] kira.pdf"
    assert res[0]["target"] == "/home/[kişi]/kisi_maskeli.pdf"
    assert "Ahmet" not in str(res) and "Ayşe" not in str(res)
    import sqlite3

    raw = sqlite3.connect(str(data_dir / settings.HISTORY_DB_FILE)).execute("SELECT * FROM recent_history").fetchall()
    assert "Ahmet" not in str(raw) and "Ayşe" not in str(raw)
    assert call("history.delete", target="/home/Ahmet Yılmaz/kisi_maskeli.pdf") == []


def test_history_scrubs_existing_rows(data_dir):
    import sqlite3

    settings.history_list()  # tabloyu oluşturur
    conn = sqlite3.connect(str(data_dir / settings.HISTORY_DB_FILE))
    conn.execute(
        "INSERT INTO recent_history (target, path, count, at) VALUES (?, ?, 1, 1)",
        ("/x/Ahmet Yılmaz_maskeli.pdf", "/x/Ahmet Yılmaz.pdf"),
    )
    conn.commit()
    conn.close()
    items = settings.history_list()
    assert items[0]["path"] == "/x/[kişi].pdf" and items[0]["target"] == "/x/[kişi]_maskeli.pdf"


def test_doc_scan_suggests_nameless_target(tmp_path):
    src = tmp_path / "Ahmet Yılmaz notlar.txt"
    src.write_text("Merhaba", encoding="utf-8")
    res = call("doc.scan", path=str(src))
    assert res["suggested_target"] == str(tmp_path / "kisi notlar_maskeli.txt")
    plain = tmp_path / "notlar.txt"
    plain.write_text("Merhaba", encoding="utf-8")
    assert "suggested_target" not in call("doc.scan", path=str(plain))


def test_profile_institutions_saved_and_exported():
    s = call("settings.get")
    p = {**s["profiles"][0], "institutions": ["Sahte Anadolu Lisesi"]}
    call("settings.save", profiles=[p, *s["profiles"][1:]], active="varsayilan")
    assert call("settings.get")["profiles"][0]["institutions"] == ["Sahte Anadolu Lisesi"]
    pack = call("profiles.export", ids=["varsayilan"])
    assert pack["profiles"][0]["institutions"] == ["Sahte Anadolu Lisesi"]


def test_profile_column_rules_saved_and_empty_rows_dropped():
    s = call("settings.get")
    rules = [{"header": "TC", "type": "tc_kimlik"}, {"header": "", "type": ""}, {"header": "Boş", "type": ""}]
    p = {**s["profiles"][0], "column_rules": rules}
    call("settings.save", profiles=[p, *s["profiles"][1:]], active="varsayilan")
    assert call("settings.get")["profiles"][0]["column_rules"] == [{"header": "TC", "type": "tc_kimlik"}]


def test_profile_pseudonym_scope_saved(data_dir):
    s = call("settings.get")
    profiles = [{**p} for p in s["profiles"]]
    profiles[0]["pseudonym_scope"] = "belge"
    profiles[1]["pseudonym_scope"] = "ortak"
    call("settings.save", profiles=profiles, active=s["active"])
    got = {p["id"]: p for p in call("settings.get")["profiles"]}
    assert got[profiles[0]["id"]]["pseudonym_scope"] == "belge"
    assert "pseudonym_scope" not in got[profiles[1]["id"]]


def test_profile_export_import_via_file(tmp_path):
    tmp_path = tmp_path / "disari"
    tmp_path.mkdir()
    out = call("profiles.export", ids=["musteri"], target=str(tmp_path / "paket"))
    assert out["count"] == 1 and out["target"].endswith("paket.json")
    assert json.loads((tmp_path / "paket.json").read_text(encoding="utf-8"))["kind"] == "bulutbelge-profiller"
    r = call("profiles.import", source=out["target"])
    assert r["imported"] == ["musteri_1"]
    with pytest.raises(EngineError) as e:
        call("profiles.import", source=str(tmp_path / "yok.json"))
    assert e.value.code == "document"
    (tmp_path / "bozuk.json").write_text("{", encoding="utf-8")
    with pytest.raises(EngineError) as e:
        call("profiles.import", source=str(tmp_path / "bozuk.json"))
    assert e.value.code == "invalid_pack"
    with pytest.raises(EngineError):
        call("profiles.export", target=str(tmp_path / "yok-klasor" / "a.json"))

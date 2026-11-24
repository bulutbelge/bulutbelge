"""e-Arşiv fatura başlığındaki iletişim ve şirket alanları (sahte değerler).

Gerçek bir faturada telefon iki biçimde kaçıyordu: 0850 ile başlayan özel numara ve "+" olmadan
"90" ile yazılmış numara. Web sitesi için tür yoktu.
"""

from bulutbelge_core.detect import detect
from bulutbelge_core.extra_types import find_websites
from bulutbelge_core.profiles import builtin_profiles
from bulutbelge_core.rules import Rules

FATURA = (
    "ORNEK TICARET A.S.\n"
    "Tel: 0850 000 00 00 \n"
    "Web Sitesi: https://ornek-ticaret.com.tr\n"
    "e-Posta: bilgi@ornek-ticaret.com.tr\n"
    "MERSİS No: 0000000000000001\n"
    "Ticaret Sicil No: 00001\n"
    "SAYIN DENEME KISI\n"
    "Tel: 905000000000 \n"
)


def _bulunan(text, rules):
    return {(f.type, f.value) for f in detect(text, rules)}


def test_0850_ve_artisiz_90_telefonlari_bulunur():
    found = _bulunan(FATURA, Rules.default())
    assert ("telefon", "0850 000 00 00") in found
    assert ("telefon", "905000000000") in found


def test_etiketsiz_artisiz_90_yalnizca_cep_numarasinda():
    rules = Rules.default()
    assert ("telefon", "905321234567") in _bulunan("arayin 905321234567 lutfen", rules)
    # Etiketsiz 12 haneli, 90 ile başlayan sabit hat biçimli sayı telefon sayılmaz (sipariş no vb.).
    assert not [t for t, _ in _bulunan("siparis 902121234567 kaydi", rules) if t == "telefon"]
    assert ("telefon", "902121234567") in _bulunan("Telefon: 902121234567", rules)


def test_web_sitesi_bulunur_e_posta_alan_adi_bulunmaz():
    spans = [FATURA[s:e] for s, e in find_websites(FATURA)]
    assert spans == ["https://ornek-ticaret.com.tr"]
    text = "Web: ornek.com.tr. Ayrica www.deneme.net/sayfa?a=1, (bkz. http://x.example.org)."
    assert [text[s:e] for s, e in find_websites(text)] == ["http://x.example.org", "www.deneme.net/sayfa?a=1", "ornek.com.tr"]


def test_web_sitesi_varsayilanda_kapali_e_faturada_acik():
    assert not [t for t, _ in _bulunan(FATURA, Rules.default()) if t == "web_sitesi"]
    efatura = next(p for p in builtin_profiles() if p["id"] == "efatura")
    found = _bulunan(FATURA, Rules.from_dict(efatura))
    assert ("web_sitesi", "https://ornek-ticaret.com.tr") in found
    assert ("mersis", "0000000000000001") in found
    assert ("ticaret_sicil", "00001") in found
    # Alan adı e-posta bulgusunun içinde kalır, ayrıca web bulgusu çıkmaz.
    assert ("eposta", "bilgi@ornek-ticaret.com.tr") in found

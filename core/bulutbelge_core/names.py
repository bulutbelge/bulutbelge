"""Türkçe kişi adı tespiti (ad + soyad).

İki yol vardır:

1. **Etiketli** (yüksek güven): "Ad Soyad:", "Adı Soyadı:", "Sayın", "Kiracı:",
   "Hasta:" gibi bir etiketin ardından büyük harfle başlayan 2-4 sözcük.
2. **Sözlükten** (orta güven): yaygın Türkçe adlardan biri (+ isteğe bağlı ikinci
   ad) ve ardından büyük harfle başlayan bir soyad. Tek başına ad ("Deniz",
   "Umut") yakalanmaz; gündelik sözcüklerle karışır.

Şirket ve kurum adları ("Deniz Bank", "Örnek Bilişim A.Ş.") soyad sanılmasın
diye kurum sözcükleri ve adres sözcükleri elenir. Ad listesi yalnızca yaygın
adlardır, kişisel veri değildir. Kaçan adlar için "Özel ifade" kullanılabilir.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import lru_cache

_FIRST_NAMES = """
Abdullah Abdulkadir Abdurrahman Adem Adil Adnan Ahmet Akif Alparslan Ali Alper Alperen Altan Arda Arif Arslan
Aslan Atakan Atilla Ayhan Aykut Aziz Bahadır Baran Barış Batuhan Battal Bayram Bekir Berat Berk Berkay Bilal
Bora Burak Burhan Bülent Cahit Can Canberk Celal Cem Cemal Cemil Cengiz Cenk Cevdet Cihan Coşkun Cumali Çağatay
Çağlar Çetin Davut Doğan Doğukan Durmuş Efe Ekrem Emin Emir Emirhan Emre Ender Engin Enes Ercan Erdal Erdem
Erdoğan Eren Erhan Erkan Ersin Ertuğrul Esat Eyüp Fahri Faruk Fatih Ferhat Fethi Fevzi Fikret Furkan Gökhan
Gökay Güven Hakan Halil Haluk Hamza Harun Hasan Haydar Hayri Hikmet Hilmi Hüseyin İbrahim İhsan İlhan İlker
İlyas İrfan İsa İshak İsmail İsmet İzzet Kaan Kadir Kamil Kemal Kenan Kerem Kerim Koray Korkmaz Kubilay Kudret
Levent Lütfi Mahmut Mehmet Melih Mert Mesut Metin Mithat Muhammed Muhammet Murat Mustafa Muzaffer Necati Necdet
Necip Nedim Nevzat Nihat Nuri Nurettin Oğuz Oğuzhan Okan Oktay Onur Orhan Osman Ozan Ömer Önder Özcan Özgür
Polat Rahmi Ramazan Rasim Recep Refik Remzi Reşat Rıza Rüstem Sabri Sadık Salih Sami Savaş Selahattin Selim
Selçuk Semih Serdar Serkan Sermet Sezer Sinan Suat Süleyman Şahin Şakir Şener Şenol Şevket Şükrü Taha Tahir
Talha Tamer Taner Tarık Tayfun Taylan Tekin Turan Turgay Turgut Tuncay Tuncer Uğur Utku Ümit Vahit Vedat Veli
Volkan Yakup Yalçın Yasin Yavuz Yılmaz Yiğit Yunus Yusuf Yücel Zafer Zeki
Ayşe Fatma Emine Hatice Zeynep Elif Meryem Şerife Sultan Zehra Hanife Merve Havva Zeliha Esra Fadime Özlem
Hacer Yasemin Hülya Leyla Songül Sevim Melek Rabia Dilek Gülsüm Kübra Büşra Tuğba Ebru Derya Aysel Sibel Filiz
Hande Hilal Huriye İlknur İrem Kader Kevser Kezban Kiraz Lale Melike Meltem Mine Müge Nalan Nazan Nazlı Necla
Nermin Nesrin Neslihan Nihal Nilay Nilgün Nur Nuray Nurcan Nuran Nurhan Nursel Oya Öznur Pelin Pınar Reyhan Rukiye
Saadet Sabahat Saliha Seda Sedef Selda Selin Selma Sema Semra Senem Serap Sevda Sevgi Sevil Sevinç Seyhan Sinem
Suna Sümeyye Şebnem Şeyma Şule Tuba Tuğçe Tülay Türkan Ümran Yağmur Yeliz Yeşim Yıldız Zerrin Zübeyde Ayla
Aylin Aynur Ayten Aysun Aslı Asiye Arzu Bahar Banu Belgin Berna Betül Beyza Burcu Canan Cansu Ceren Cemile Damla
Defne Demet Didem Dilara Duygu Ecem Eda Ela Elçin Emel Esin Eylül Feride Feyza Figen Funda Gamze Gizem Gonca
Gökçe Gönül Gül Gülay Gülcan Gülşen Gülten Güler Günay Gülizar Hacer Hale Halime Handan Hatice Hayriye Hediye
İclal İkbal İnci Işıl Jale Kamile Keziban Meral Mihriban Mukaddes Münevver Naciye Nazife Nebahat Nefise Nezahat
Nilüfer Pakize Perihan Ruken Safiye Saniye Sare Semiha Serpil Sevgül Şengül Şükran Tijen Ülkü Zuhal Zülfiye
Deniz Umut Özge Ezgi Duru Asya Ada Azra Eflin Ela Nehir Mira Lina Alya Elisa Zümra Hiranur Ecrin Beren Erva
""".split()


# Ek yaygın adlar (TÜİK'in kamuya açık ad dağılımı ve yaygın yazılışlar; kişisel veri değildir).
_MORE_FIRST_NAMES = """
Abbas Abdulhamit Abdulkerim Abdullatif Abdulmuttalip Abdussamet Adil Ahmed Ahsen Akın Aksel Alaaddin Alaattin
Alican Alihan Alp Alpay Alpaslan Alptekin Altuğ Anıl Aras Arman Armağan Asım Aydın Aydoğan Ayetullah Aytaç
Azmi Bahattin Bahri Bedri Bedirhan Behçet Behzat Bekir Bener Beytullah Bircan Birol Bozkurt Bünyamin Burak
Cafer Cavit Cebrail Cesur Cüneyt Çınar Çağrı Demir Derviş Deniz Dinç Doruk Dursun Ediz Ekin Emrah Enver
Eray Ercüment Erdi Erel Eren Ergin Ergün Erkut Ersan Ertan Ertaç Eser Evren Eyüphan Fahrettin Farouk Fatih
Fehmi Ferit Fırat Fuat Galip Gazi Giray Gürkan Gürsel Habib Hafız Hakkı Halis Hamdi Hamit Hanefi Harun Hayati
Hazım Hidayet Hurşit Hüsamettin Hüsnü Ihsan Irmak Işık Izzet Kadri Kazım Kenan Kemalettin Kıvanç Kürşat
Lokman Mahir Mazlum Mecit Mehmed Melih Memduh Menderes Mevlüt Mikail Mirza Muammer Muharrem Muhsin Muhittin
Mümin Münir Mürsel Mustafa Nabi Nadir Namık Nazım Nebi Nejat Nezih Niyazi Numan Nusret Okay Olcay Orkun Oral
Ordal Osmancan Ozgür Ömercan Özkan Özer Özden Rafet Rauf Recai Reşit Rıdvan Ruhi Sacit Sadi Sadettin Safa
Sait Salim Sarp Seçkin Sedat Semi Seyit Seyfettin Sezgin Sıtkı Soner Sungur Süha Tacettin Tahsin Talat Tanju
Tarkan Tevfik Timur Tolga Tolgahan Toprak Tuğrul Tunç Tuncay Turhan Ufuk Ulaş Ulvi Umutcan Vecihi Yaşar Yekta
Yener Yusuf Yağız Yahya Yaman Yamaç Yiğithan Yurdakul Zahit Zekeriya Zeynel Ziya Zihni Zülkif Rasul Resul
Resül Raşit Rasim Ramiz Rehber Rüzgar Rüştü Ferdi Feyyaz Ferman Fevzullah Gıyasettin Gündüz Gürbüz Güney
Abdulaziz Abdulgani Abdulvahap Ahmet Alaeddin Alim Alpgiray Apo Arif Arhan Aşkın Atıf Ayaz Aybars Aydıncan
Ayberk Bayezid Behram Bilge Bilgehan Bülent Cabbar Cahide Caner Cüneyd Dağhan Dorukhan Edis Emirali Emircan
Erbil Ercan Erdinç Ergi Erim Ertunç Eymen Ferhan Gökmen Gökşin Gürhan Hasbi Haşim Hıdır Hüdai Ilgaz Işıkhan
Kağan Kaplan Karahan Kutay Kutlu Mazhar Mümtaz Nasuh Necmi Nizamettin Oğuzcan Orçun Oytun Özay Özgün Rüzgâr
Sabahattin Samet Sezai Sükrü Tankut Tuna Tuncel Uluç Yasar Yusufcan Zafer Zeynelabidin
Afra Ahsen Akgül Alev Almila Amine Arife Aybüke Aycan Ayça Aygül Aygün Aylin Aysel Ayşegül Ayşenur Azize Bahar
Bediha Belkıs Beyhan Bilge Bircan Birgül Bürge Cahide Cavidan Ceyda Ceylan Cennet Cihan Çağla Çiğdem Çisem
Dicle Dilan Dilber Dilruba Doğa Dudu Duriye Ebrar Edanur Elanur Elmas Emine Emriye Erva Esma Ezel Fadıl Fahriye
Fazilet Fehime Fethiye Fidan Firdevs Fulya Gaye Gizem Gökçen Gülbahar Gülçin Gülfem Gülhan Gülnur Gülistan
Gülsen Gülşah Gülümser Günseli Hafize Halide Hamide Hasibe Hatun Havin Hazal Hilal Hümeyra Işın İlayda İpek
İrfan İz Kader Kamer Kardelen Kıymet Kıvılcım Kudret Lamia Latife Leman Lemis Leyla Lütfiye Mahinur Mahperi
Makbule Mediha Mehtap Melahat Melis Menekşe Mensure Merve Mervenur Meryem Mihrimah Miray Müberra Müjde
Müyesser Nagehan Naz Nazlıcan Nazmiye Necmiye Nehir Nesibe Nevin Neşe Nigar Nihan Nimet Nisa Nisanur Nurşen
Nurten Öykü Özden Özgül Özge Özlem Perim Rana Rahime Rengin Ruhsar Rümeysa Sakine Selcen Selen Selvi Semanur
Sena Serra Sevcan Sevtap Sevim Şadiye Şahika Şaziye Şeyda Şirin Tansu Tuğçe Tülin Turgut Umay Vildan Yaren
Yasemin Yelda Yonca Zarife Zehra Zekiye Zeynep Zilan Zübeyde Ayşenur Fatmanur Hülya Kübranur Nuriye Sümeyra
Rabia Ravza Reyyan Rojin Rüya Sıla Sidre Suzan Sümbül Şeref Tuana Ülfet Yağmur Yıldız Zahide Zelal
"""

# 17 Kasım 2026 (TAKIP 1.47): ad listesinde olmayan adların etiketsiz bağlamda kaçmasını azaltmak için eklendi.
# Yalnızca yaygın adlar; gündelik sözcükle karışanlar (Kuzey, Poyraz, Rüzgar, Fırat, Çınar vb.) bilerek eklenmedi.
_EXTRA_FIRST_NAMES = """
Abdulhamit Abdulkerim Abdullah Adnan Ahsen Akın Alaaddin Alihan Alpay Anıl Arman Atahan Aydın Aytaç Azmi Barkın
Batu Bedri Behçet Berkcan Bircan Cafer Cihat Cüneyt Dursun Ediz Egemen Emrah Erman Ersan Evren Gürkan Güray
Hüsnü İlter İsmail Kağan Kazım Kürşat Mazlum Mazhar Mehmetcan Metehan Miraç Muhittin Mücahit Namık Nazım Nejat
Nihat Oğuzcan Orkun Oral Osmancan Özkan Rauf Recai Rıdvan Sabahattin Sadi Said Salim Samet Sedat Selami Sertaç
Servet Sevket Sezgin Sıtkı Tacettin Tevfik Timur Tolga Tolgahan Toprak Ufuk Uluç Vecihi Yaşar Yiğithan Yusufcan
Zekeriya Ziya Zihni Alaz Aras Aslan Ayberk Aykan Bahattin Barışcan Batın Bertan Bozkurt Bünyamin Cavit Cebrail
Çağan Çağrı Demircan Doruk Ensar Erkut Ferdi Gazi Gürcan Haktan Halis Hazar İlkay İlhami İlkin Kerem Kıvanç
Koray Mirza Muammer Mümin Nebi Nizami Oğuzkan Orhun Ozcan Remzi Reha Sefa Sırrı Sungur Şafak Şahap Taylan
Tunç Turhan Tuna Ulaş Ulvi Vural Yekta Yusufhan Zahid
Afife Ahsen Akgül Alev Almila Arife Aslıhan Ayça Ayşegül Azize Bahriye Başak Behiye Bengü Bilge Binnaz Birgül
Birsen Buse Çiğdem Çisem Dilan Dilek Dilruba Ebrar Edanur Ecrin Elanur Elmas Eslem Evrim Fahriye Fidan Fulya
Gaye Gülbahar Gülnur Gülsen Gülşah Güneş Hafize Halide Hazal Hilmiye Hümeyra Iclal Ilgın İdil İpek İrem İsra
Kadriye Kardelen Kıymet Lamia Latife Mahinur Makbule Mediha Mehtap Melahat Melis Menekşe Mevlüde Muazzez Müjde
Naile Nergis Neşe Nevin Nida Nigar Nimet Nuriye Oylum Özlem Rabiye Reyhan Rezzan Sanem Selenay Selvihan Semahat
Serenay Seval Sevinç Sezen Sıdıka Simge Sonay Şahnur Şermin Şevval Tahire Tanem Tolga Tuğba Türkan Ümmühan
Ümmü Vecihe Yadigar Yasemin Yeter Zahide Zehranur Zeynel Zilha Züleyha
""".split()

FIRST_NAMES = frozenset(_FIRST_NAMES + _MORE_FIRST_NAMES.split() + _EXTRA_FIRST_NAMES)

# Türkçe harfsiz yazımlar da ad sayılır ("Ayse Yilmaz", dosya adları ve klavyesiz yazışmalar).
_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def _ascii_key(word: str) -> str:
    return word.replace("I", "ı").replace("İ", "i").lower().translate(_ASCII)


FIRST_NAMES_ASCII = frozenset(_ascii_key(n) for n in _FIRST_NAMES + _EXTRA_FIRST_NAMES)

# Ad sözcüğü gibi görünen ama ardından gelen kurum/yer sözcüğü yüzünden kişi olmayanlar.
_NOT_SURNAME = {
    w.casefold()
    for w in """
    A.Ş. AŞ A.S. Ltd Ltd. Şti Şti. Holding Bank Bankası Grup Group Sigorta Yatırım Vakfı Vakıf Derneği Belediyesi
    Belediye Başkanlığı Bakanlığı Müdürlüğü Üniversitesi Hastanesi Okulu Lisesi Camii Mahallesi Mah Mah. Cad Cad.
    Caddesi Sokak Sokağı Sk. Bulvarı Apartmanı Sitesi Plaza Tower İnşaat Gıda Ticaret Sanayi Market Otel Tekstil
    Lojistik Teknoloji Bilişim Yazılım Danışmanlık Hukuk Bürosu Eczanesi Kliniği Cumhuriyeti Türkiye Bey Hanım
    Ve İle Da De Ki School University College Institute Academy Hospital Foundation Company Corporation Inc
    Limited Bank Hotel Street Avenue Road Park
    """.split()
}

# Formlarda adın ardından gelen bir sonraki alanın adı; ada katılmaz ("Ad Soyad: Ayşe Yılmaz Telefon: ...").
_FIELD_WORDS = {
    w.casefold()
    for w in """
    Telefon Tel Gsm Cep Adres Adresi TC T.C. Kimlik E-posta Eposta Mail Doğum Tarih Tarihi İmza Kaşe No Numara
    Numarası Unvan Unvanı Görev Görevi Departman Birim Şube İl İlçe Uyruk Cinsiyet Meslek Baba Anne Medeni Kan
    Sicil Pasaport Ehliyet Plaka Iban Hesap Tutar Tarafından İçin Olarak Ile
    Firma Şirket Kurum Kuruluş Çalıştığı Çalıştığınız Pozisyon Pozisyonu Referans Referansı Ünvan Işyeri İşyeri
    Company Position Phone Email Address Title Department Employer
    CV Özgeçmiş Resume Dilekçe Sözleşme Fatura
    """.split()
}
# Kişi adı taşıyan yer adları ("Fatih Sultan Mehmet Bulvarı", "Atatürk Lisesi").
_PLACE_WORDS = {
    w.casefold()
    for w in """
    Bulvarı Bulvar Caddesi Cadde Cad Sokak Sokağı Sk Mahallesi Mah Köprüsü Parkı Meydanı Lisesi Okulu
    İlkokulu Ortaokulu Üniversitesi Hastanesi Camii Havalimanı Stadyumu Kültür Merkezi Vakfı Ödülü Salonu
    School Schools University College Institute Academy High Primary Secondary Middle Hospital Foundation
    Street Avenue Road Park Airport Stadium Center Centre Company Corporation Inc Ltd Limited Bank Hotel
    """.split()
}

# En yaygın Türkçe soyadları (kamuya açık dağılım; kişisel veri değildir). Ad + bu soyad, harf büyüklüğünden
# bağımsız ("Taner şahin") kişi adı sayılır.
_COMMON_SURNAMES = frozenset(
    fold_w
    for fold_w in """
    yilmaz kaya demir sahin celik yildiz yildirim ozturk aydin ozdemir arslan dogan cetin 
    ozkan simsek polat korkmaz ozcan erdogan yavuz aksoy turan 
    bozkurt karaca ekinci coskun cinar aktas
    sezer ucar bayrak bayram bozkurt duran kahraman karakaya korkut ozgur tuncer uysal
    yalcin yuksel ergin ersoy gungor karadeniz kurtulus taskin bayar inonu esedoglu
    """.split()
)

_WORD = r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]+|[A-ZÇĞİÖŞÜ]{2,}"
# Güçlü etiketler: ardından gelen her ad-soyad kişidir. Zayıf etiketlerden ("Müşteri", "Kiracı")
# sonra ise en az bir sözcük bilinen bir ad olmalı ("Müşteri Başvuru Formu" kişi değildir).
_STRONG = re.compile(
    r"(?i)(?:ad[ıi]?\s*(?:ve\s*)?soyad[ıi]?|ad\s*-\s*soyad|isim(?:\s*soyisim)?|sayın|sn\.|name|full\s+name)"
)
_LABEL = re.compile(
    r"(?i)(?<!\w)(ad[ıi]?\s*(?:ve\s*)?soyad[ıi]?|ad\s*-\s*soyad|isim(?:\s*soyisim)?|sayın|sn\.|"
    r"kiracı|kiraya\s+veren|işçi|çalışan|personel|müşteri|hasta|öğrenci|veli|vekil|katılımcı|başvuran|"
    r"hazırlayan|düzenleyen|teslim\s+alan|teslim\s+eden|yetkili|alıcı|gönderen|sigortalı|borçlu|kefil|"
    r"tanık|davacı|davalı|name|full\s+name)\s*[:\-]?[ \t]*"
    r"(?-i:((?:" + _WORD + r")(?:[ \t]+(?:" + _WORD + r")){1,3}))"
)
_TOKEN = re.compile(r"[^\W\d_]+")
_CAP = re.compile(_WORD)


def _adjacent(text: str, a: re.Match[str], b: re.Match[str]) -> bool:
    """İki sözcük yalnızca boşluk ya da sekmeyle ayrılmış mı (satır sonu, noktalama değil)."""
    return bool(re.fullmatch(r"[ \t]+", text[a.end():b.start()]))


def _key(word: str) -> str:
    """Adı sözlükteki biçimine getirir ("AYŞE" → "Ayşe")."""
    w = word.replace("I", "ı").replace("İ", "i").lower()
    return w[:1].replace("i", "İ").replace("ı", "I").upper() + w[1:] if w else w


_TR_FOLD = str.maketrans("çÇğĞıIİiöÖşŞüÜâÂîÎûÛ", "ccggiiiioossuuaaiiuu")


@lru_cache(maxsize=65536)
def fold(word: str) -> str:
    """Türkçe karakterleri ASCII'ye indirir ("Resül" → "resul"); ASCII yazılmış belgelerde de eşleşsin."""
    return word.translate(_TR_FOLD).lower()


_FIRST_FOLDED = frozenset(fold(n) for n in FIRST_NAMES)


def _is_first(word: str) -> bool:
    return _key(word) in FIRST_NAMES or fold(word) in _FIRST_FOLDED


def _ok_surname(word: str) -> bool:
    return word.casefold() not in _NOT_SURNAME and len(word) >= 2


def _trim(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Etiketli eşleşmenin sonundaki kurum sözcüklerini atar; kişi adı kalmazsa None."""
    words = list(re.finditer(r"\S+", text[start:end]))
    kept = []
    for w in words:
        word = w.group().rstrip(".,;")
        if not _ok_surname(word) or word.casefold() in _FIELD_WORDS:
            break
        kept.append(w)
    if len(kept) < 2:
        return None
    return start + kept[0].start(), start + kept[-1].end()


def find_person_names(text: str) -> Iterator[tuple[int, int, bool]]:
    """(başlangıç, bitiş, etiketli_mi) üretir."""
    for m in _LABEL.finditer(text):
        span = _trim(text, m.start(2), m.end(2))
        if not span:
            continue
        strong = _STRONG.fullmatch(m.group(1).strip()) is not None
        if strong or any(_is_first(w) for w in text[span[0]:span[1]].split()):
            yield span[0], span[1], True
    # Sözlük yolu: sözcükleri sırayla gez; ad + (ikinci ad) + soyad.
    words = list(_TOKEN.finditer(text))
    i = 0
    while i < len(words) - 1:
        w = words[i]
        if not (_CAP.fullmatch(w.group()) and _is_first(w.group())):
            i += 1
            continue
        j = i + 1
        # İkinci ad ("Ayşe Nur Yılmaz"): ardından bir soyad daha gelmeli.
        if (
            j + 1 < len(words)
            and _adjacent(text, words[j - 1], words[j])
            and _is_first(words[j].group())
            and _adjacent(text, words[j], words[j + 1])
            and _CAP.fullmatch(words[j + 1].group())
            and _ok_surname(words[j + 1].group())
            and words[j + 1].group().casefold() not in _FIELD_WORDS
        ):
            j += 1
        last = words[j]
        after = words[j + 1] if j + 1 < len(words) else None
        is_place = after is not None and _adjacent(text, last, after) and after.group().casefold() in _PLACE_WORDS
        if (
            not is_place
            and _adjacent(text, words[j - 1], last)
            and _CAP.fullmatch(last.group())
            and _ok_surname(last.group())
            and last.group().casefold() not in _FIELD_WORDS
        ):
            yield w.start(), last.end(), False
            i = j + 1
        else:
            i += 1


# --- Ek tespit yolları: e-posta ipucu, belge başlığı, yazım benzerliği -------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# E-posta adresinin yerel kısmında ad olmayan, genel kullanılan sözcükler.
_GENERIC_LOCAL = frozenset(
    """info bilgi mail email eposta iletisim contact admin ik hr destek support satis sales muhasebe
    insan kaynaklari kariyer career jobs cv noreply no reply yonetim genel sekreter ofis office web
    posta test demo ornek example user""".split()
)
# Başlık satırı olamayacak sözcükler (bölüm başlıkları, unvanlar, kurum ve alan adları). Küçük harfle ASCII.
_HEADING_WORDS = frozenset(
    fold(w)
    for w in """
    Bilgileri Bilgi Bilgiler Deneyim Deneyimleri Eğitim Eğitimi İletişim Özel Özet Yetkinlikler Yetenekler
    Sertifika Sertifikalar Seminerler Kurslar Referanslar Kariyer Hedefi Pozisyon Firma Adı Sektörü Şehir
    Başlangıç Bitiş Tarihi Çalışma Şekli İş Tanımı Dil Seviye Yabancı Bilgisayar Sınav Skoru Açıklama
    Üniversite Fakülte Bölüm Enstitüsü Fakültesi Lisans Lise Mühendis Mühendisi Uzmanı Uzman Müdürü Müdür
    Yöneticisi Yönetici Sorumlusu Sorumlu Asistanı Asistan Şefi Şef Teknisyeni Teknisyen Stajyer Doktor
    Öğretmen Avukat Mimar Danışman Kişisel Özgeçmiş Hakkımda Hakkında Profil Genel Amaç Proje Projeler
    Ödüller Hobiler İlgi Alanları Askerlik Durumu Medeni Hal Cinsiyet Uyruk Adres Telefon Doğum Yeri Sürücü
    Belgesi Sayfa Form Başvuru Tarih Konu Sayın Rapor Liste Tablo Toplam Ek Notlar Not Özeti Rapor Sözleşme
    Madde Taraflar Giriş Sonuç Kapak İçindekiler Ltd Şti Anonim Şirketi Holding Grup Sanayi Ticaret
    Türkiye Cumhuriyeti İstanbul Ankara İzmir Bursa Kocaeli Antalya Adana Konya Mersin Gaziantep
    Work Experience Education Training Languages Language Skills Skill Summary Profile Contact Personal
    Information Details Projects Certifications Certificates Interests Hobbies References Objective Career
    Professional Employment History Courses Awards Achievements Curriculum Vitae Resume Computer Technical
    Date Birth Nationality Military Service Driving License Marital Status Gender Address Phone Email
    Intern Internship Engineer Manager Specialist Assistant Director Planning Production Quality Sales
    """.split()
)
_LINE_NAME = re.compile(r"^(?:" + _WORD + r")(?: (?:" + _WORD + r")){1,2}$")
_ALLCAPS_LINE = re.compile(r"^[A-ZÇĞİÖŞÜ0-9/&.,\- ]{6,}$")


_GIVEN = "ad:"  # name_hints içinde, ad soyad olarak görülmüş kişinin adını işaretler
# Soyadsız ad listesindeki ayraçlar: "Mustafa/Tuğçe", "Ayşe, Fatma", "Ali ve Veli".
_LIST_SEP = re.compile(r"\s*/\s*|\s*,\s+|\s+ve\s+")


def name_hints(texts: list[str]) -> frozenset[str]:
    """Belgedeki e-posta adreslerinin yerel kısmından ad/soyad ipuçları (ASCII katlanmış, en az 4 harf).

    "resul.catan@..." → {"resul", "catan", "resulcatan"}. Genel adresler (info@, ik@) ipucu vermez.
    """
    hints: set[str] = set()
    for text in texts:
        for m in _EMAIL.finditer(text):
            local = fold(m.group().split("@", 1)[0])
            parts = [p for p in re.split(r"[^a-z]+", local) if p]
            if not parts or all(p in _GENERIC_LOCAL for p in parts):
                continue
            joined = "".join(parts)
            hints.add(joined)
            hints.update(p for p in parts if len(p) >= 4 and p not in _GENERIC_LOCAL)
    # Web adreslerinde geçen ad ("nuribayar.meb.k12.tr") belgenin başka yerlerinde de aynı kişinin adıdır.
    for text in texts:
        for a, b, conf, _reason in find_url_names(text):
            if conf != "orta":
                continue
            parts = [fold(t.group()) for t in _URL_TOKEN.finditer(text[a:b])]
            joined = "".join(parts)
            if len(joined) >= 6:
                hints.add(joined)
                hints.update(p for p in parts if len(p) >= 4)
    kept = {h for h in hints if len(h) >= 4}
    # Belgenin bir yerinde ad soyad olarak yakalanan kişinin adı, başka yerde tek başına geçse de aynı kişidir.
    for text in texts:
        for a, b, _labeled in find_person_names(text):
            given = [w.group() for w in _TOKEN.finditer(text[a:b])][:-1]
            kept.update(_GIVEN + fold(w) for w in given if len(w) >= 3 and _is_first(w))
    return frozenset(kept)


def _hint_match(word: str, hints: frozenset[str]) -> bool:
    f = fold(word)
    if len(f) < 4:
        return False
    # Sözcük bir ipucuna eşit olmalı ya da (birleşik yazılmış adreste) onun içinde geçmeli.
    return any(not h.startswith(_GIVEN) and (f == h or (len(h) > len(f) and f in h)) for h in hints)


def _surname_like(word: str) -> bool:
    return _CAP.fullmatch(word) is not None and _ok_surname(word) and word.casefold() not in _FIELD_WORDS


def _edit1_index() -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for name in _FIRST_FOLDED:
        if len(name) < 5:
            continue
        for key in {name, *(name[:i] + name[i + 1:] for i in range(len(name)))}:
            index.setdefault(key, set()).add(name)
    return index


_EDIT1 = _edit1_index()


@lru_cache(maxsize=65536)
def _near_first_name(word: str) -> str | None:
    """Sözlükte olmayan ama sözlükteki bir adın tek harflik yazım farkı olan sözcük → o ad.

    Kısa sözcükler ("Bilgi" ~ "Bilge") sıradan kelimelerle karışacağı için en az 6 harf aranır.
    """
    f = fold(word)
    if len(f) < 6 or f in _FIRST_FOLDED:
        return None
    for key in {f, *(f[:i] + f[i + 1:] for i in range(len(f)))}:
        for name in _EDIT1.get(key, ()):
            if _edit1(f, name):
                return name
    return None


def _edit1(a: str, b: str) -> bool:
    """İki dizgenin düzenleme uzaklığı tam 1 mi (ekleme, silme ya da değiştirme)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    return any(a == b[:i] + b[i + 1:] for i in range(len(b)))


def find_name_candidates(
    text: str, hints: frozenset[str] = frozenset(), lead: bool = False
) -> Iterator[tuple[int, int, str, str]]:
    """Ek kişi adı adayları: (başlangıç, bitiş, güven, neden). Güven: "orta" ya da "dusuk".

    1. **E-posta ipucu** (orta): belgede ad.soyad@... gibi bir adres varsa, o ad ve soyadı belgenin her yerinde
       büyük harfle başlayan sözcük olarak aranır; bitişik ad+soyad tek aday olur.
    2. **Belge başlığı** (düşük): belgenin başında, yalnızca 2-3 büyük harfli sözcükten oluşan, bölüm başlığı
       ya da unvan olmayan satır; iletişim bilgisi ya da büyük harfli unvan satırı yanındaysa.
    3. **Yazım benzerliği** (düşük): ad listesindeki bir adın tek harf farkıyla yazılmış sözcük + soyad.
    """
    words = list(_TOKEN.finditer(text))
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in taken)

    if any(not h.startswith(_GIVEN) for h in hints):
        i = 0
        while i < len(words):
            w = words[i]
            if not (
                _surname_like(w.group())
                and fold(w.group()) not in _HEADING_WORDS
                and _hint_match(w.group(), hints)
            ):
                i += 1
                continue
            j = i
            # Komşu sözcük de ipucuna uyuyorsa ya da ad/soyad gibiyse aynı adaya kat (en çok 3 sözcük).
            while j + 1 < len(words) and j - i < 2 and _adjacent(text, words[j], words[j + 1]):
                nxt = words[j + 1].group()
                # Ad ipucuna uyan komşu sözcük küçük harfle de yazılmış olabilir ("Taner şahin").
                if (_surname_like(nxt) and (_hint_match(nxt, hints) or _is_first(nxt))) or (
                    _hint_match(nxt, hints) and fold(nxt) not in _HEADING_WORDS and nxt.casefold() not in _FIELD_WORDS
                ):
                    j += 1
                else:
                    break
            # Tek başına ad ("Ayşe") maskelenmez (tasarım: gündelik sözcüklerle karışır); tek sözcük soyad gibiyse alınır.
            if j == i and _is_first(w.group()):
                i += 1
                continue
            a, b = w.start(), words[j].end()
            if free(a, b):
                taken.append((a, b))
                yield a, b, "orta", "e-posta adresindeki adla eşleşiyor"
            i = j + 1

    # Soyadsız ad listesi ("Mustafa/Tuğçe", "Ayşe, Fatma ve Ali"): sözlükteki en az iki ad ayraçla bitişikse aday.
    i = 0
    while i < len(words) - 1:
        j = i
        while _CAP.fullmatch(words[j].group()) and _is_first(words[j].group()):
            k = j + 1
            if k + 1 < len(words) and words[k].group() == "ve":  # "ve" ayrı sözcük sayılır
                k += 1
            if not (
                k < len(words)
                and _CAP.fullmatch(words[k].group())
                and _is_first(words[k].group())
                and _LIST_SEP.fullmatch(text[words[j].end():words[k].start()])
            ):
                break
            j = k
        if j > i:
            a, b = words[i].start(), words[j].end()
            after = words[j + 1] if j + 1 < len(words) else None
            # Ardından soyad geliyorsa ("Ali/Veli Kaya") sözlük yolu ele alır.
            if not (after and _adjacent(text, words[j], after) and _CAP.fullmatch(after.group())) and free(a, b):
                taken.append((a, b))
                yield a, b, "orta", "soyadsız ad listesi (ayraçla birleşik adlar)"
            i = j + 1
        else:
            i += 1

    # Belgede ad soyad olarak maskelenen kişinin tek başına geçen adı (yalnızca o ad; sözlük adı her yerde aranmaz).
    given = {h[len(_GIVEN):] for h in hints if h.startswith(_GIVEN)}
    if given:
        for w in words:
            if _CAP.fullmatch(w.group()) and fold(w.group()) in given and free(w.start(), w.end()):
                taken.append((w.start(), w.end()))
                yield w.start(), w.end(), "orta", "belgede ad soyad olarak geçen kişinin adı"

    if lead:
        pos = 0
        lines = []
        for raw in text.split("\n"):
            lines.append((pos, raw))
            pos += len(raw) + 1
        lines = [(p, l) for p, l in lines if l.strip()][:30]
        for n, (p, line) in enumerate(lines):
            stripped = line.strip()
            if not _LINE_NAME.fullmatch(stripped):
                continue
            parts = stripped.split(" ")
            if any(fold(w) in _HEADING_WORDS or w.casefold() in _NOT_SURNAME or w.casefold() in _FIELD_WORDS for w in parts):
                continue
            if all(w.isupper() for w in parts) and len(parts) > 2:
                continue
            near = [l for _p, l in lines[max(0, n - 4): n + 5] if l is not line]
            contact = any(_EMAIL.search(l) or re.search(r"(?i)\b(tel|telefon|gsm|cep|adres|e-?posta)\b", l) for l in near)
            nxt = lines[n + 1][1].strip() if n + 1 < len(lines) else ""
            title = bool(_ALLCAPS_LINE.fullmatch(nxt)) and " " in nxt
            if not (contact or title):
                continue
            a = p + line.index(stripped)
            b = a + len(stripped)
            if free(a, b):
                taken.append((a, b))
                yield a, b, "dusuk", "belge başında ad soyad gibi duruyor"

    # Ad + yaygın soyad, harf büyüklüğünden bağımsız ("Taner şahin"): ad Baş harfi büyük, soyad sözlükte.
    for i in range(len(words) - 1):
        w, nx = words[i], words[i + 1]
        if (
            _CAP.fullmatch(w.group())
            and _is_first(w.group())
            and fold(nx.group()) in _COMMON_SURNAMES
            and not _CAP.fullmatch(nx.group())
            and _adjacent(text, w, nx)
            and free(w.start(), nx.end())
        ):
            taken.append((w.start(), nx.end()))
            yield w.start(), nx.end(), "orta", "ad ve yaygın bir soyad (soyad küçük harfle yazılmış)"

    i = 0
    while i < len(words) - 1:
        w, nx = words[i], words[i + 1]
        # Tamamı büyük yazılmış sözcükler (BAŞLIKLAR) sıradan kelimeleri çok yakalar; yalnızca "Ad" biçimi.
        near = _near_first_name(w.group()) if (_CAP.fullmatch(w.group()) and not w.group().isupper()) else None
        if (
            near
            and _adjacent(text, w, nx)
            and _surname_like(nx.group())
            and not nx.group().isupper()
            and len(nx.group()) >= 4
            and fold(nx.group()) not in _HEADING_WORDS
            and free(w.start(), nx.end())
        ):
            taken.append((w.start(), nx.end()))
            yield w.start(), nx.end(), "dusuk", "ad listesindeki bir ada yazım olarak çok benziyor"
            i += 2
        else:
            i += 1


# --- Web adreslerindeki adlar ("nuribayar.meb.k12.tr", "www.ahmetyilmaz.com") -------------------------

_URL = re.compile(
    r"(?i)(?:https?://|www\.)[^\s<>\"')\]]+"
    r"|(?<![@\w.\-])(?:[a-z0-9-]+\.)+(?:com|net|org|info|biz|edu|gov|tr|io|co|me)\b(?:/[^\s<>\"')\]]*)?"
)
_URL_TOKEN = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]+")
# Alan adı ve yol parçalarında ad olmayan sözcükler (şirket/hizmet adları, alt alan adları, uzantılar).
_URL_WORDS = frozenset(
    """http https www com net org info biz edu gov tr io co me k12 meb bel pol av dr web site mail blog portal shop
    store online app api cdn home index html htm php asp aspx pdf cv profil profile about contact iletisim bank
    banka bankasi soft yazilim tech teknoloji group grup holding market gida insaat tekstil lojistik medya sigorta
    otomotiv enerji bilisim danismanlik ticaret sanayi ltd sti anonim sirket company corp inc limited okulu lisesi
    okul universitesi egitim hastanesi hastane belediyesi kurs akademi medikal saglik turizm otel""".split()
)


def find_url_names(text: str, hints: frozenset[str] = frozenset()) -> Iterator[tuple[int, int, str, str]]:
    """Web adreslerinde geçen kişi adları: (başlangıç, bitiş, güven, neden). Yalnızca ad parçası maskelenir.

    - Bitişik yazılmış ad+soyad ("nuribayar"): ad sözlükte, kalan 5+ harf ve alan adı sözcüğü değil → orta;
      kalan 4 harf ya da yaygın soyad değilse belirsiz → düşük.
    - Ad ve soyad ayrı parça ("ahmet.yilmaz"): ad sözlükte, bir sonraki parça soyad gibi → orta.
    - E-posta ipucuyla birebir eşleşen parça → orta.
    """
    for m in _URL.finditer(text):
        base = m.start()
        toks = [(t.start() + base, t.end() + base, fold(t.group())) for t in _URL_TOKEN.finditer(m.group())]
        used: set[int] = set()
        for i, (a, b, f) in enumerate(toks):
            if i in used or f in _URL_WORDS or len(f) < 3:
                continue
            if any(f == h for h in hints if len(h) >= 6):
                used.add(i)
                yield a, b, "orta", "e-posta adresindeki adla eşleşiyor"
                continue
            # Ad ve soyad ayrı parçalarda ("ahmet.yilmaz"); araları yalnızca . - _ olmalı.
            if f in _FIRST_FOLDED and i + 1 < len(toks):
                na, nb, nf = toks[i + 1]
                if nf not in _URL_WORDS and len(nf) >= 4 and re.fullmatch(r"[.\-_]", text[b:na]):
                    used.update({i, i + 1})
                    yield a, nb, "orta", "web adresinde ad ve soyad"
                    continue
            # Bitişik ad+soyad ("nuribayar"): ad sözlükte olan en uzun önek.
            for k in range(len(f) - 3, 2, -1):
                if f[:k] in _FIRST_FOLDED:
                    rest = f[k:]
                    if rest in _URL_WORDS or not rest.isalpha():
                        break
                    if rest in _COMMON_SURNAMES or len(rest) >= 5:
                        used.add(i)
                        yield a, b, "orta", "web adresinde bitişik yazılmış ad ve soyad"
                    elif len(rest) == 4:
                        used.add(i)
                        yield a, b, "dusuk", "web adresinde ad gibi duran bir parça"
                    break


def initials(value: str) -> str:
    """"Ayşe Nur Yılmaz" → "A. N. Y." """
    return " ".join(w[0].upper() + "." for w in value.split() if w)

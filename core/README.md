# bulutbelge-core

Tespit, maskeleme ve belge işleme çekirdeği. Masaüstü uygulaması ve (ileride) sunucu aynı kütüphaneyi kullanır.

| Modül | İçerik |
|---|---|
| `validators.py` | TC kimlik, VKN, IBAN (mod-97), kredi kartı (Luhn) kontrol hanesi doğrulamaları |
| `rules.py` | Kullanıcı kuralları: veri türü + yöntem, özel ifade, özel kalıp, beyaz liste |
| `detect.py` | Metinde bulgu tespiti, çakışma çözümü |
| `mask.py` | Tek yönlü maskeleme: karartma, etiket, son 4 hane açık, bulanık |
| `blur.py` | Bulanık yöntemin dolgusu: rastgele, orijinalden bağımsız buzlu cam görüntüsü |
| `signatures.py` | İmza ve kaşe bölgesi tespiti (etiket yakınındaki görsel ve el çizimi) |
| `extra_types.py` | Adres, doğum tarihi, plaka, IP, tutar bulucuları ve genelleştirme |
| `pdf.py` | PDF tarama ve gerçek silmeyle maskeleme (elle seçilen alanlar dahil) |
| `batch.py` | Klasörle toplu işlem planı |

## Tespit edilen türler

TC kimlik no, VKN, TR IBAN, kredi kartı, Türkiye telefon numaraları, e-posta, adres ("Adres:" etiketi ya da mahalle/cadde/sokak + No; il genelleştirmesi), doğum tarihi ("doğum" bağlamıyla; on yıllık aralık), araç plakası, IP adresi (alt ağ genelleştirmesi), tutar (varsayılan kapalı; büyüklük aralığı). Numaralar kontrol hanesinden geçmezse bulgu sayılmaz. Kullanıcı ayrıca özel ifade (sözcük sınırıyla, büyük/küçük harf duyarsız) ve özel kalıp ekleyebilir. Kalıplar 2 saniyelik süre sınırıyla çalışır (ReDoS), boş metinle eşleşen kalıp reddedilir.

## PDF'te maskeleme

- Bulgunun altındaki metin içerik akışından silinir (PyMuPDF redaction), kapladığı görsel pikseller de temizlenir.
- Meta veri, XML meta veri, yorum ve notlar, form alanları, ekli dosyalar, JavaScript, bağlantılar ve gizli metin kaldırılır.
- Yeri bulunamayan bir bulgu varsa maskeleme yapılmaz (şüphede reddet).
- Çıktı yeniden okunur; işaretli bir değer hâlâ okunabiliyorsa dosya yazılmaz (kaçak tespiti).
- Orijinal dosyaya dokunulmaz.

## Bulanık yöntem

Orijinal bulanıklaştırılmaz ya da pikselleştirilmez; bunlar geri okunabilir (Depix, Unredacter). Değer önce gerçekten silinir, yerine rastgele üretilmiş bir dolgu konur. Karar: `docs/kararlar/2026-11-04-bulanik-yontem.md`.

## İmza ve kaşe

"İmza", "Kaşe", "Mühür", "Onaylayan" gibi bir etiketin yanında ya da altında duran görsel (taranmış imza, kaşe) ve çok sayıda eğriden oluşan el çizimi imza sayılır. Etiket eşleşmesi Türkçe karaktersiz yazımı da tanır ("Imza", "Kase"). Etiketsiz görseller (logo gibi) imza sayılmaz. Bulgular orta güvenlidir, kullanıcı onaylar.

Maskelemede imza görseli belgeden tamamen silinir; el çizimi imzanın çizgileri redaksiyonla kaldırılır. Kaçak tespiti çıktıda aynı görselin ya da bölgede çizginin kalmadığını doğrular. Elektronik imza alanı varsa uyarı verilir: maskeli kopyada e-imza kalmaz.

Henüz yok: etiketsiz imza, taranmış sayfadaki imza.

Henüz yok: takma ad (geri çevrilebilir maskeleme, `.bbmap`), Türkçe isim tanıma, taranmış PDF (OCR), filigran, Word ve Excel.

Etiketler (`[TC NO]` gibi) PDF'in standart yazı tipiyle yazıldığı için ASCII'dir.

## Test

```bash
pip install -e ".[dev]"
pytest
```

Test verisi `tests/fake_data.py` ile üretilir: kontrol hanesi doğru ama tamamen uydurma numaralar.

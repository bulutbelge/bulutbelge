---
name: bulutbelge
description: Kişisel veri içerebilecek yerel belgelerle (sözleşme, dilekçe, bordro, fatura, kimlik, CV, başvuru; PDF, Word, Excel, PowerPoint, görsel, UDF, e-posta) çalışırken BulutBelge masaüstü uygulamasının yerel komutunu kullanır. Önce değer göstermeden tarar (scan), kullanıcıya maskeli okumayı önerir; orijinal değerler ajana ulaşmaz.
---

# BulutBelge: kişisel veri içerebilecek belgeleri maskeli okuma

BulutBelge kullanıcının bilgisayarında çalışan bir masaüstü uygulamasıdır. Belgedeki kişisel veriyi
(ad, TC kimlik no, telefon, IBAN, adres…) **gerçekten siler** ve yalnızca maskeli çıktıyı verir. Hiçbir
sunucuya bağlanmaz. Komut yalnızca kullanıcının uygulamada izin verdiği klasörlerde çalışır ve her
çağrı uygulamanın hash zincirli işlem günlüğüne "Ajan" olarak yazılır.

## Ne zaman kullanılır

- Kullanıcı yerel bir belgeyi okumanı, özetlemeni ya da içinden bilgi çıkarmanı istediğinde ve belge
  kişisel veri içerebilecek türdeyse (sözleşme, dilekçe, bordro, fatura, kimlik, CV, başvuru, sağlık,
  banka, mahkeme evrakı; ya da adından/klasöründen emin olamadığın bir belge).
- Kullanıcı bir belgenin maskeli (paylaşılabilir) kopyasını istediğinde.

Kullanma: kaynak kod, yapılandırma dosyası, kişisel veri taşımadığı açık olan metinler. Kullanıcı
belgeyi doğrudan okumanı açıkça istiyorsa ona uy; bu beceri öneri sunar, zorlamaz.

## Akış

1. **Bak (yalnızca sayılar):** `bulutbelge scan "<dosya>" --ajan <ajan-adın>`
   Belge değişmez; çıktı veri türüne göre bulgu sayıları, sayfa sayısı ve uyarılardır, değer yoktur.
2. **Kullanıcıya öner:** bulgu varsa kullanıcıya kaç kişisel veri bulunduğunu söyle ve maskeli
   okumayı öner. Dosyayı kabukla (`cat`, `Read`, `pdftotext`…) doğrudan okuma.
3. **Maskeli oku:** `bulutbelge read "<dosya>" --ajan <ajan-adın>` (makine okunur: `--json`).
4. **Maskeli kopya (yalnızca kullanıcı isterse):** `bulutbelge mask "<dosya>" [--hedef "<yeni dosya>"] --ajan <ajan-adın>`
   Yazma kullanıcının onayıyla yapılır; kaynak belgeye dokunulmaz, var olan dosyanın üzerine yazılmaz.

İlk kez kullanıyorsan izinleri gör: `bulutbelge folders`. Liste boşsa kullanıcıdan BulutBelge ›
Ayarlar › Ajan erişimi bölümünden klasör eklemesini iste; ayar dosyasını kendin değiştirme.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `bulutbelge folders [--json]` | İzinli klasörler ve maskeli kopya yazma izni |
| `bulutbelge scan <dosya> [--profil ID] [--ajan AD] [--json]` | Değer göstermeden bulgu sayıları, sayfa sayısı, uyarılar |
| `bulutbelge read <dosya> [--profil ID] [--ajan AD] [--json]` | Belgenin maskeli metni ve özet |
| `bulutbelge mask <dosya> [--hedef YOL] [--profil ID] [--ajan AD] [--json]` | Maskeli kopyayı yeni dosyaya yazar (yazma izni gerekir) |
| `bulutbelge kilavuz` | Tam kılavuz (JSON şeması, sık görülen hatalar) |

`--profil` yalnızca ajan için atanan kural takımını ya da ondan sıkısını seçebilir; genelde verme.

## MCP araçları (yapılandırıldıysa)

BulutBelge yerel MCP sunucusu (`bulutbelge mcp`, yalnızca stdio) eklendiyse aynı işlemler araç olarak
da vardır; kabuk komutu yerine bunları kullanabilirsin. Kurallar ve izinler aynıdır.

| Araç | Komut karşılığı |
|---|---|
| `bulutbelge_folders` | `bulutbelge folders` |
| `bulutbelge_scan` (`path`) | `bulutbelge scan` |
| `bulutbelge_read` (`path`) | `bulutbelge read` |
| `bulutbelge_mask` (`path`, isteğe bağlı `target`) | `bulutbelge mask` |

Araç hata döndürürse (`isError`) `structuredContent.exit_code` aşağıdaki çıkış kodlarıyla aynı anlamdadır.
Claude Code'a eklemek için (kullanıcı yapar): `claude mcp add bulutbelge -- bulutbelge mcp`.

## Çıkış kodları

| Kod | Anlamı | Ne yapmalı |
|---|---|---|
| 0 | Başarılı | Devam et |
| 1 | Belge hatası (bozuk dosya, desteklenmeyen biçim, kaçak denetimi, `ocr_unavailable`) | Mesajı kullanıcıya ilet; dosyayı başka yoldan okuma |
| 2 | Kullanım hatası | Komutu düzelt |
| 3 | İzin yok (klasör, yazma izni, kasa koşulu, gevşek kural takımı) | **Dur**, mesajı aynen ilet; izni aşmaya çalışma |
| 4 | İşlem günlüğü yazılamıyor | **Dur**, kullanıcıya bildir |

## Kurallar

- Maskeli metindeki `[AD SOYAD]`, `█████` gibi yer tutucuları gerçek değerle doldurmaya, tahmin
  etmeye ya da başka kaynaktan eşleştirmeye çalışma. Maske kaldırma senin işin değil.
- Uyarıda "metin katmanı yok" ya da "OCR" geçiyorsa o sayfa okunamamıştır; çıktıyı belgenin tamamı sanma.
- "Kaçak tespiti" hatası dosyanın yazılmadığı anlamına gelir; başka yoldan okumayı deneme.
- Maskeleme %100 doğru değildir; önemli çıktıyı paylaşmadan önce kullanıcının kontrol etmesini öner.

## Örnek akış

```
Kullanıcı: Masaüstündeki sözleşmeyi özetler misin? (C:\Belgeler\sozlesme.pdf)
Ajan:      bulutbelge scan "C:\Belgeler\sozlesme.pdf" --ajan claude-code
           → Bulunan: 6 (Kişi adı: 2, TC kimlik no: 2, IBAN: 1, Adres: 1)
Ajan:      "Belgede 6 kişisel veri var (ad, TC kimlik no, IBAN, adres). Maskeli hâlini okuyup
           özetleyeyim mi?"
Kullanıcı: Evet.
Ajan:      bulutbelge read "C:\Belgeler\sozlesme.pdf" --ajan claude-code
           → maskeli metinden özet
```

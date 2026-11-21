# BulutBelge komut satırı kılavuzu (insanlar ve yapay zekâ ajanları için)

BulutBelge'yi terminalden kullanmak için: bir belgenin **maskeli metnini okumak** ve **maskeli kopyasını yazmak**. Claude Code, Codex, Gemini CLI, Cursor gibi kabuk çalıştırabilen her ajan ya da bir betik kullanabilir. Orijinal değerler ajana hiç ulaşmaz; yalnızca maskeli çıktı döner.

Yerel API ve MCP yoktur, yalnızca bu komut satırı (karar: `docs/kararlar/2026-11-05-ajan-yerel-kullanim.md`). Bu kılavuz uygulamanın içinde de gelir: `bulutbelge kilavuz`.

## Kısaca

| | |
|---|---|
| Ne yapar | Belgeyi **gerçekten maskeler** (görsel örtü değil, silme), maskeli metni ya da maskeli kopyayı verir |
| Biçimler | PDF, görsel (JPG/PNG/TIFF/BMP/WEBP), Word, Excel, PowerPoint, XML/TXT/CSV |
| Ne zaman çalışır | Kullanıcı önce **izin verdiyse** (aşağıda "Bir kez yapılacak ayar") |
| Ne yapmaz | Maskeyi kaldırmaz, kasayı açmaz, mevcut dosyanın üzerine yazmaz, izinli klasör dışına çıkmaz |
| Denetim | Her çağrı (reddedilenler dahil) hash zincirli işlem günlüğüne "Ajan" olarak yazılır |

## Hızlı başlangıç

1. **Kullanıcı** (bir kez): BulutBelge › Ayarlar › **Ajan erişimi** › klasörü ekle; kopya yazılacaksa **Maskeli kopya yazabilsin** anahtarını aç.
2. **Ajan/terminal**: izinleri gör, oku, kopya yaz:

```
bulutbelge folders
bulutbelge read  "C:\Belgeler\basvuru.pdf" --ajan claude-code
bulutbelge mask  "C:\Belgeler\basvuru.pdf" --ajan claude-code
```

3. Çıkış kodunu kontrol et (0 başarılı; 3 izin yok, 4 günlük yazılamıyor: durup kullanıcıya bildir).

`bulutbelge` komutu yoksa (MSI, geliştirme) tam yolunu kullanın (aşağıda "Komutu çalıştırmak"); `bulutbelge kilavuz --yonerge` size doğru komutu yazar.

## Bir kez yapılacak ayar (kullanıcı)

Ajan, bu ayar yapılmadan hiçbir dosyayı okuyamaz. Ayar uygulamanın **Ayarlar › Ajan erişimi** bölümündedir; ajan bunu değiştiremez, değiştirmeye çalışmamalıdır.

1. **İzinli klasörler.** Ajanın çalışacağı klasörleri ekleyin. Sürücünün tamamı, kullanıcı klasörünün tamamı ve uygulamanın ayar klasörü eklenemez. Maskeli kopyaların yazılacağı klasör de listede olmalıdır.
2. **Maskeli kopya yazabilsin.** `mask` komutu için gerekir. Yazılan her şey yeni dosyadır; var olan dosyanın ve kaynak belgenin üzerine yazılmaz.
3. **Özel ifade kasası** kullanıyorsanız: komut kasayı açamaz, bu yüzden kasadaki kişi/müşteri/proje adları ajan çıktısında **maskelenmez**. Kabul ediyorsanız **Özel ifadeler olmadan çalışabilsin** anahtarını açın; kapalıyken ajan hiç çalışmaz. Takma ad yöntemi kullanan kural takımı ajanla kullanılamaz.
4. İsterseniz ajan için ayrı bir **kural takımı** seçin (varsayılan: Ayarlar'da şu an kullanılan).
5. İşiniz bitince klasörleri kaldırabilir, yazma anahtarını kapatabilirsiniz.

Ayarlar'daki **Ajan yönergesini kopyala** düğmesi aşağıdaki hazır yönergeyi panoya alır.

## Komutu çalıştırmak

| Kurulum | Komut |
|---|---|
| Windows, NSIS kurulumu (önerilen) | `bulutbelge <komut>`: kurulum, klasörü kullanıcının PATH'ine ekler ve `bulutbelge` kısa adını yazar (**yeni açılan** terminalde geçerli). Dosya: `%LOCALAPPDATA%\BulutBelge\engine\bulutbelge-engine.exe` |
| Windows, MSI | MSI PATH'e dokunmaz: `"C:\Program Files\BulutBelge\engine\bulutbelge-engine.exe" <komut>` (varsayılan kurulum klasörü) |
| macOS | `/Applications/BulutBelge.app/Contents/Resources/engine/bulutbelge-engine <komut> ...` (macOS'ta denenmedi) |
| Linux (.deb) | `bulutbelge <komut> ...` (paket `/usr/bin/bulutbelge` kısa adını ve `man bulutbelge` sayfasını kurar; tam yol `/usr/lib/BulutBelge/engine/bulutbelge-engine`. Linux'ta denenmedi; AppImage'da komut satırı yoktur, .deb kullanın) |
| Geliştirme ortamı | `desktop/engine/.venv/bin/python -m bulutbelge_engine.cli <komut>` (Windows: `.venv\Scripts\python.exe`) |
| `pip install -e desktop/engine` yapıldıysa | `bulutbelge <komut>` |

Kurulu uygulamada komut, uygulamayla gelen motor dosyasıdır: aynı dosya argümansız çalışınca masaüstünün motorudur, komutla çalışınca ajan komutudur. Bu kurulumdaki gerçek komutu görmek için `bulutbelge kilavuz --yonerge` çıktısına bakın: yönergedeki komut adı, çalıştığınız kuruluma göre (kısa ad, tam yol ya da `python -m ...`) otomatik yazılır; Ayarlar'daki **Ajan yönergesini kopyala** düğmesi de aynısını yapar. PATH'e ekleme kurulumu kaldırınca geri alınır.

Bu kılavuzda kısalık için `bulutbelge <komut>` yazılır; sizdeki karşılığını kullanın. OCR için dil dosyaları motorun yanındadır (paketli sürümde gömülü); geliştirme ortamında `BULUTBELGE_TESSDATA` ile `desktop/engine/tessdata` gösterilmelidir, yoksa taranmış sayfalar okunamaz.

Ayar klasörü her zaman masaüstü uygulamasının klasörüdür (Windows `%APPDATA%\com.proteksistem.bulutbelge`, macOS `~/Library/Application Support/com.proteksistem.bulutbelge`, Linux `~/.local/share/com.proteksistem.bulutbelge`); izinler, kural takımları ve işlem günlüğü oradan okunur. Ajan bu klasörü seçemez: `--veri-klasoru` reddedilir (çıkış kodu 2), `BULUTBELGE_DATA_DIR` yok sayılır. İkisi yalnızca geliştirme ve testte, `BULUTBELGE_GELISTIRME=1` ortam değişkeniyle kabul edilir; ajana bu değişkeni verilen bir ortamda çalıştırmayın.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `read <dosya> [--profil ID] [--ajan AD] [--json]` | Belgenin **maskeli metnini** yazdırır, sonda özet. Belge önce gerçekten maskelenir (geçici kopya, kaçak denetimiyle), metin o kopyadan çıkarılır; geçici kopya silinir. |
| `mask <dosya> [--hedef YOL] [--profil ID] [--ajan AD] [--json]` | Maskeli kopyayı **yeni dosyaya** yazar (varsayılan: kaynağın yanında `_maskeli`). Hedef de izinli klasörde olmalıdır. |
| `folders [--json]` | İzinli klasörleri ve yazma iznini gösterir. İlk çağrı olarak iyi bir denetimdir. |
| `kilavuz [--yonerge]` | Bu kılavuzu (ya da yalnızca hazır yönergeyi) yazdırır. İzin ya da ayar gerektirmez, günlüğe girmez. |

Ortak seçenekler: `--ajan AD` günlüğe yazılacak ajan adı (örn. `claude-code`; yalnızca harf, rakam, `.`, `_`, `-`, harf ya da rakamla başlar, aksi hâlde çıkış kodu 2); `--profil ID` kural takımı; `--json` makine okunur çıktı.

### Örnek çıktılar (sahte veri)

`read` (metin biçimi):

```
Başvuran: [AD SOYAD]
TC Kimlik No: █████
E-posta: [E-POSTA]

--- BulutBelge özeti ---
Kural takımı: Varsayılan
Maskelenen: 3
  - Kişi adı: 1
  - TC kimlik no: 1
  - E-posta: 1
```

`mask --json`:

```json
{"ok": true, "summary": {"islem": "maskeleme", "kaynak": "C:\\Belgeler\\basvuru.pdf",
 "hedef": "C:\\Belgeler\\basvuru_maskeli.pdf", "kural_takimi": "Varsayılan", "maskelenen": 3,
 "turler": {"Kişi adı": 1, "TC kimlik no": 1, "E-posta": 1}, "uyarilar": [], "not": null}}
```

`read --json` aynı biçimde ayrıca `"text"` alanı taşır. Hata mesajları stderr'e `Hata (kod): ...` olarak yazılır; stdout yalnızca maskeli içeriği ve özeti taşır.

### Çıkış kodları

| Kod | Anlamı | Ajan ne yapmalı |
|---|---|---|
| 0 | Başarılı | Devam et |
| 1 | Belge ya da işlem hatası (bozuk dosya, desteklenmeyen biçim, **kaçak denetimi**) | Hata mesajını kullanıcıya ilet; dosyayı başka yoldan okuma |
| 2 | Kullanım hatası (yanlış argüman, kural takımı yok) | Komutu düzelt |
| 3 | İzin yok: dosya izinli klasör dışında, yazma izni yok, kasa koşulu | **Dur**, mesajı aynen ilet; izni aşmaya çalışma |
| 4 | İşlem günlüğü yazılamıyor; güvenlik için işlem yapılmadı | **Dur**, kullanıcıya bildir |

### Sık görülenler

| Mesaj / durum | Anlamı ve çözüm |
|---|---|
| Çıkış 3, "izinli klasör yok" | Kullanıcı Ayarlar › Ajan erişimi'nde klasör eklememiş. Kullanıcıdan isteyin. |
| Çıkış 3, hedef izinli klasör dışında | `--hedef` yolu izinli klasörlerin altında olmalı (ya da kullanıcı hedef klasörü de eklemeli). |
| "Kaçak tespiti: maskelenmesi gereken N değer çıktıda hâlâ okunuyor. Dosya yazılmadı." | Güvenlik denetimi çıktıda silinmemiş bir değer buldu; **dosya yazılmaz**. Bu bir hata değil korumadır. Belgede başka yerde geçen aynı değer ya da web adresi olabilir; kullanıcı uygulamada elle kontrol etsin. |
| Uyarı: "Taranmış 1 sayfa OCR ile okundu…" | Metin katmanı olmayan sayfa OCR ile okundu; OCR hata yapabilir. Çıktıyı kontrol edin. |
| Uyarı: "metin katmanı yok ve OCR dil dosyaları kurulu değil" | Taranmış sayfa **okunamadı**, içindeki kişisel veri maskelenmemiş olabilir; çıktıya güvenmeyin. `BULUTBELGE_TESSDATA` ayarlayın ya da uygulamada "Alan seç" ile elle işaretleyin. |

## JSON çıktı şeması

`--json` başarıda stdout'a **tek satır** JSON yazar (UTF-8). Hata olursa stdout'a JSON yazılmaz; hata stderr'e `Hata (kod): ...` olarak gider ve çıkış kodu sıfırdan farklıdır. `bulutbelge <komut> --help` aynı alanları gösterir.

`read --json`:

| Alan | Tür | Açıklama |
|---|---|---|
| `ok` | boolean | Başarıda her zaman `true` |
| `text` | string | Belgenin maskeli metni |
| `summary` | object | İşlem özeti (aşağıda) |

`mask --json`: `ok` ve `summary` alanları (`text` yoktur).

`folders --json`:

| Alan | Tür | Açıklama |
|---|---|---|
| `folders` | array of string | İzinli klasörler |
| `allow_write` | boolean | Maskeli kopya yazma izni |

`summary` nesnesi (read ve mask için aynı):

| Alan | Tür | Açıklama |
|---|---|---|
| `islem` | string | "okuma" ya da "maskeleme" |
| `kaynak` | string | Kaynak belgenin mutlak yolu |
| `hedef` | string \| null | Maskeli kopyanın yolu (yalnızca mask; read'de null) |
| `kural_takimi` | string | Kullanılan kural takımının adı |
| `maskelenen` | integer | Maskelenen değer sayısı |
| `turler` | object (string → integer) | Veri türü adına göre maskelenen sayı |
| `uyarilar` | array of string | Uyarılar (ör. OCR); yoksa boş liste |
| `not` | string \| null | İşlem notu; yoksa null |

`read --json` örneği (sahte veri):

```json
{"ok": true, "text": "Başvuran: [AD SOYAD]\nE-posta: [E-POSTA]\n",
 "summary": {"islem": "okuma", "kaynak": "C:\\Belgeler\\ornek_basvuru.pdf", "hedef": null,
 "kural_takimi": "Varsayılan", "maskelenen": 2,
 "turler": {"Kişi adı": 1, "E-posta": 1}, "uyarilar": [], "not": null}}
```

`mask --json` örneği yukarıda "Örnek çıktılar" bölümündedir.

## Güvenlik modeli

BulutBelge'nin **kodda zorladığı** kurallar (ajan aşamaz):
- Amaç olmadan erişim yok: izinli klasör dışındaki dosya okunmaz, yazılmaz. Yol kaçışları (`..`) reddedilir.
- Yazma ayrı bir izindir ve her zaman **yeni dosyaya** yapılır.
- Maske kaldırma (takma adı gerçek değere çevirme) ve kasa açma komut satırında **yoktur**.
- Çıktıda orijinal değer yoktur; işlem günlüğünde belge içeriği yoktur, yalnızca yol ve tür bazında sayılar.
- Günlük yazılamazsa işlem yapılmaz.

**Zorlanmayan** (ajanın kendi disiplini): ajan, izinli klasördeki dosyaları kabuktan doğrudan da okuyabilir; BulutBelge bunu engelleyemez. Engel, ajan aracının kendi izin ayarlarıdır (örn. Claude Code'da o klasörlere doğrudan okuma izni vermemek, yalnızca `bulutbelge` komutunu izinli saymak). Hazır yönerge bunu ajana söyler.

Maskeleme %100 doğru değildir: bir bilgiyi kaçırabilir ya da gerekenden fazlasını maskeleyebilir. Önemli belgelerde çıktıyı paylaşmadan önce kontrol edin (ayrıntı: Kullanım Koşulları).

## Ajana verilecek hazır yönerge

Aşağıdaki metni ajanın talimat dosyasına ekleyin: Claude Code için `CLAUDE.md`, Codex/Cursor/diğerleri için `AGENTS.md` ya da sistem yönergesi. Komut yolunu kurulumunuza göre düzeltin. Aynı metin `bulutbelge kilavuz --yonerge` ile de alınır.

<!-- yonerge-basla -->
```markdown
## Yerel belgeler: yalnızca BulutBelge ile oku

Kişisel veri içerebilecek yerel belgeleri (PDF, Word, Excel, PowerPoint, XML, CSV, JSON, TXT, LOG, görsel)
doğrudan açma, okuma ya da içeriklerini kopyalama. Her zaman BulutBelge komutunu kullan.
(Komut PATH'te değilse tam yolunu yaz; örn. bulutbelge-engine ya da python -m bulutbelge_engine.cli.)

- İzinler:        bulutbelge folders
- Okuma:          bulutbelge read "<dosya>" --ajan <ajan-adın>
  Çıktı belgenin maskeli metnidir; sonda "--- BulutBelge özeti ---" bölümü vardır.
  Makine okunur çıktı için --json ekle: {"ok": true, "text": "...", "summary": {...}}.
- Maskeli kopya:  bulutbelge mask "<dosya>" [--hedef "<yeni dosya>"] --ajan <ajan-adın>
  Kaynak belgeye dokunulmaz, var olan dosyanın üzerine yazılmaz. Hedef izinli klasörde olmalı.

Kurallar:
- Her çağrıdan sonra çıkış kodunu kontrol et. 3 (izin yok) ya da 4 (günlük yazılamıyor) ise işi
  durdur ve kullanıcıya hata mesajını aynen ilet. İzni aşmaya, dosyayı başka yoldan okumaya ya da
  kopyalamaya çalışma. Kullanıcıdan BulutBelge › Ayarlar › Ajan erişimi'nde izin vermesini iste.
- "Kaçak tespiti" hatası dosyanın yazılmadığı anlamına gelir; başka yoldan okumayı deneme,
  kullanıcıya bildir.
- Uyarılarda "OCR dil dosyaları kurulu değil" ya da "metin katmanı yok" geçiyorsa o sayfa
  okunamamıştır; çıktıdaki kişisel veri maskelenmemiş olabilir, çıktıya güvenme.
- Maskeli metindeki [AD SOYAD], [TC KİMLİK NO], █████ gibi yer tutucuları gerçek değerle
  doldurmaya, tahmin etmeye ya da başka kaynaktan eşleştirmeye çalışma.
- Maskeyi kaldırma (takma adı gerçek değere çevirme) senin işin değil; gerekirse kullanıcıdan
  BulutBelge uygulamasında yapmasını iste.
- Ürettiğin dosyaları izinli klasöre yaz; maskeli içerikten yeni belge oluşturuyorsan yine
  kişisel veri eklememeye dikkat et.
```
<!-- yonerge-bitis -->

## Sınırlar

- Ajan aracı izinli klasördeki dosyalara kabuktan doğrudan erişebiliyorsa BulutBelge bunu engellemez (yukarıda "Zorlanmayan").
- İşlem günlüğü dosya yollarını tutar; dosya adında kişi adı varsa günlükte de görünür.
- Başarılı `mask` işlemi arayüzdeki "Son yapılanlar" listesine "Ajan (ad)" etiketiyle de eklenir; `read` ve reddedilen çağrılar yalnızca işlem günlüğüne girer.
- Taranmış sayfa ve fotoğrafın metin katmanı yoktur: OCR kuruluysa okunur ve maskelenir (OCR hata yapabilir); kurulu değilse `read` çıktısında içerikleri yer almaz, özette uyarı olarak geçer ve o sayfadaki veri maskelenmemiş olabilir.
- Maske kaldırma ve kasa açma komut satırında yoktur.

## For agents (English summary)

BulutBelge masks personal data in local documents. Use it instead of reading documents directly.

- `bulutbelge folders` — show allowed folders and write permission (a human sets these in the app: Settings › Agent access).
- `bulutbelge read <file> --ajan <agent-name>` — print the **masked text** of the document (original values are never returned). Add `--json` for machine-readable output.
- `bulutbelge mask <file> [--hedef <new file>] --ajan <name>` — write a masked copy to a **new** file inside an allowed folder (never overwrites).
- Exit codes: 0 ok, 1 document/operation error (including "leak check": file not written), 2 usage error, 3 not allowed, 4 audit log not writable. On 3 or 4 **stop** and relay the error to the user; do not try to bypass permissions.
- Do not guess or restore masked values. Masking is not 100% accurate; warn the user to review important output.
- `bulutbelge kilavuz --yonerge` prints a ready-to-paste instruction block for your `AGENTS.md`/`CLAUDE.md`.

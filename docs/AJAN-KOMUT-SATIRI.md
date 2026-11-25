# BulutBelge komut satırı kılavuzu (insanlar ve yapay zekâ ajanları için)

BulutBelge'yi terminalden kullanmak için: bir belgede **kaç kişisel veri olduğuna bakmak** (değer göstermeden), belgenin **maskeli metnini okumak** ve **maskeli kopyasını yazmak**. Claude Code, Codex, Gemini CLI, Cursor gibi kabuk çalıştırabilen her ajan ya da bir betik kullanabilir. Orijinal değerler ajana hiç ulaşmaz; yalnızca maskeli çıktı döner.

Yerel API yoktur (karar: `docs/kararlar/2026-11-05-ajan-yerel-kullanim.md`). Aynı işlemleri aynı kurallarla sunan yerel bir MCP sunucusu vardır: `bulutbelge mcp`, yalnızca standart giriş/çıkış (stdio) üzerinden, ağ portu açmaz (aşağıda "MCP sunucusu"; karar: `docs/kararlar/2026-11-21-ajan-mcp-stdio.md`). Bu kılavuz uygulamanın içinde de gelir: `bulutbelge kilavuz`.

## Kısaca

| | |
|---|---|
| Ne yapar | Belgeyi **gerçekten maskeler** (görsel örtü değil, silme), maskeli metni ya da maskeli kopyayı verir; `scan` yalnızca bulgu sayılarını verir |
| Biçimler | PDF, görsel (JPG/PNG/TIFF/BMP/WEBP), Word, Excel, PowerPoint, XML/TXT/CSV |
| Ne zaman çalışır | Kullanıcı önce **izin verdiyse** (aşağıda "Bir kez yapılacak ayar") |
| Ne yapmaz | Maskeyi kaldırmaz, kasayı açmaz, mevcut dosyanın üzerine yazmaz, izinli klasör dışına çıkmaz |
| Denetim | Her çağrı (reddedilenler dahil) hash zincirli işlem günlüğüne "Ajan" olarak yazılır |
| MCP | `bulutbelge mcp`: yerel, yalnızca stdio; araçlar komutlarla aynı izin ve günlüğü kullanır |

## Hızlı başlangıç

1. **Kullanıcı** (bir kez): BulutBelge › Ayarlar › **Ajan erişimi** › klasörü ekle; kopya yazılacaksa **Maskeli kopya yazabilsin** anahtarını aç.
2. **Ajan/terminal**: izinleri gör, bak (yalnızca sayılar), oku, kopya yaz:

```
bulutbelge folders
bulutbelge scan  "C:\Belgeler\basvuru.pdf" --ajan claude-code
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
4. İsterseniz ajan için ayrı bir **kural takımı** seçin (varsayılan: Ayarlar'da şu an kullanılan). Bu takım ajan için **üst sınırdır**: ajan `--profil` ile yalnızca bu takımı ya da ondan sıkı bir takımı seçebilir; daha gevşek bir takım (ör. adları açık bırakan "Kurum içine") reddedilir.
5. İşiniz bitince klasörleri kaldırabilir, yazma anahtarını kapatabilirsiniz.

Ayarlar'daki **Ajan yönergesini kopyala** düğmesi aşağıdaki hazır yönergeyi panoya alır.

## Komutu çalıştırmak

| Kurulum | Komut |
|---|---|
| Windows, NSIS kurulumu (önerilen) | `bulutbelge <komut>`: kurulum, klasörü kullanıcının PATH'ine ekler ve `bulutbelge` kısa adını yazar (**yeni açılan** terminalde geçerli). Dosya: `%LOCALAPPDATA%\BulutBelge\engine\bulutbelge-engine.exe` |
| Windows, MSI | MSI PATH'e dokunmaz: `"<kurulum klasörü>\engine\bulutbelge-engine.exe" <komut>`. Varsayılan kurulum klasörü `C:\Program Files\BulutBelge`; Kurulum klasörünü PowerShell'de `(Get-ItemProperty 'HKCU:\Software\proteksistem\BulutBelge').InstallDir` gösterir |
| macOS | `/Applications/BulutBelge.app/Contents/Resources/engine/bulutbelge-engine <komut> ...` (macOS kurulumu `bulutbelge` kısa adını PATH'e eklemez; tam yolu yazın) |
| Linux (.deb) | `bulutbelge <komut> ...` (paket `/usr/bin/bulutbelge` kısa adını ve `man bulutbelge` sayfasını kurar; tam yol `/usr/lib/BulutBelge/engine/bulutbelge-engine`. Linux'ta denenmedi; AppImage'da komut satırı yoktur, .deb kullanın) |
| Geliştirme ortamı | `desktop/engine/.venv/bin/python -m bulutbelge_engine.cli <komut>` (Windows: `.venv\Scripts\python.exe`) |
| `pip install -e desktop/engine` yapıldıysa | `bulutbelge <komut>` |

Kurulu uygulamada komut, uygulamayla gelen motor dosyasıdır: aynı dosya argümansız çalışınca masaüstünün motorudur, komutla çalışınca ajan komutudur. Bu kurulumdaki gerçek komutu görmek için `bulutbelge kilavuz --yonerge` çıktısına bakın: yönergedeki komut adı, çalıştığınız kuruluma göre (kısa ad, tam yol ya da `python -m ...`) otomatik yazılır; Ayarlar'daki **Ajan yönergesini kopyala** düğmesi de aynısını yapar. PATH'e ekleme kurulumu kaldırınca geri alınır.

Bu kılavuzda kısalık için `bulutbelge <komut>` yazılır; sizdeki karşılığını kullanın. OCR için dil dosyaları motorun yanındadır (paketli sürümde gömülü); geliştirme ortamında `BULUTBELGE_TESSDATA` ile `desktop/engine/tessdata` gösterilmelidir, yoksa taranmış sayfalar okunamaz.

Ayar klasörü her zaman masaüstü uygulamasının klasörüdür (Windows `%APPDATA%\com.proteksistem.bulutbelge`, macOS `~/Library/Application Support/com.proteksistem.bulutbelge`, Linux `~/.local/share/com.proteksistem.bulutbelge`); izinler, kural takımları ve işlem günlüğü oradan okunur. Ajan bu klasörü seçemez: `--veri-klasoru` reddedilir (çıkış kodu 2), `BULUTBELGE_DATA_DIR` yok sayılır. İkisi yalnızca geliştirme ve testte, `BULUTBELGE_GELISTIRME=1` ortam değişkeniyle kabul edilir; ajana bu değişkeni verilen bir ortamda çalıştırmayın.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `scan <dosya> [--profil ID] [--ajan AD] [--json]` | Belgeyi **değiştirmeden** tarar; **değer göstermez**: veri türüne göre bulgu sayıları, sayfa sayısı ve uyarılar. İzin modeli `read` ile aynıdır, günlüğe "okuma" olarak girer. Kişisel veri içerebilecek bir belgede ilk adım budur. |
| `read <dosya> [--profil ID] [--ajan AD] [--json]` | Belgenin **maskeli metnini** yazdırır, sonda özet. Belge önce gerçekten maskelenir (geçici kopya, kaçak denetimiyle), metin o kopyadan çıkarılır; geçici kopya silinir. |
| `mask <dosya> [--hedef YOL] [--profil ID] [--ajan AD] [--json]` | Maskeli kopyayı **yeni dosyaya** yazar (varsayılan: kaynağın yanında `_maskeli`). Hedef de izinli klasörde olmalıdır. |
| `folders [--json]` | İzinli klasörleri ve yazma iznini gösterir. İlk çağrı olarak iyi bir denetimdir. |
| `mcp` | Yerel MCP sunucusunu başlatır (yalnızca stdio, ağ portu açmaz). Ajan aracı bunu alt süreç olarak çalıştırır; elle çalıştırmanız gerekmez. Aşağıda "MCP sunucusu". |
| `kilavuz [--yonerge] [--skill]` | Bu kılavuzu, yalnızca hazır yönergeyi (`--yonerge`) ya da Claude Code beceri dosyasını (`--skill`) yazdırır. İzin ya da ayar gerektirmez, günlüğe girmez. |

Ortak seçenekler: `--ajan AD` günlüğe yazılacak ajan adı (örn. `claude-code`; yalnızca harf, rakam, `.`, `_`, `-`, harf ya da rakamla başlar, aksi hâlde çıkış kodu 2); `--profil ID` kural takımı (yalnızca ajan için atanan takım ya da ondan sıkısı: atanan takımda maskelenen her veri türünü maskeleyen, beyaz listesi daha geniş olmayan; aksi hâlde çıkış kodu 3); `--json` makine okunur çıktı.

### Örnek çıktılar (sahte veri)

`scan` (metin biçimi):

```
--- BulutBelge tarama özeti ---
Kaynak: C:\Belgeler\basvuru.pdf
Kural takımı: Varsayılan
Sayfa: 2
Bulunan: 3
  - Kişi adı: 1
  - TC kimlik no: 1
  - E-posta: 1
Belge değiştirilmedi, değerler gösterilmez. Maskeli metin için: bulutbelge read
```

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
| 1 | Belge ya da işlem hatası (bozuk dosya, desteklenmeyen biçim, **kaçak denetimi**, OCR kullanılamıyor) | Hata mesajını kullanıcıya ilet; dosyayı başka yoldan okuma |
| 2 | Kullanım hatası (yanlış argüman, kural takımı yok) | Komutu düzelt |
| 3 | İzin yok: dosya izinli klasör dışında, yazma izni yok, kasa koşulu, atanandan gevşek kural takımı, masaüstü uygulaması kurulu değil | **Dur**, mesajı aynen ilet; izni aşmaya çalışma |
| 4 | İşlem günlüğü yazılamıyor; güvenlik için işlem yapılmadı | **Dur**, kullanıcıya bildir |

### Sık görülenler

| Mesaj / durum | Anlamı ve çözüm |
|---|---|
| Çıkış 3, `app_not_installed` | Masaüstü uygulaması kurulu değil ya da hiç açılmamış (ayar klasörü yok). Ajan komutu ve MCP sunucusu (MCPB paketi dahil) yalnızca uygulamanın ayarlarıyla çalışır: kullanıcı uygulamayı kurup bir kez açmalı ve klasör izni vermeli. |
| Çıkış 3, "izinli klasör yok" | Kullanıcı Ayarlar › Ajan erişimi'nde klasör eklememiş. Kullanıcıdan isteyin. |
| Çıkış 3, "kural takımı, ajan için atanan takımdan gevşek" | `--profil` ile seçilen takım, atanan takımın maskelediği bir türü açık bırakıyor. `--profil` vermeyin (atanan takım kullanılır) ya da daha sıkı bir takım seçin. |
| Çıkış 3, hedef izinli klasör dışında | `--hedef` yolu izinli klasörlerin altında olmalı (ya da kullanıcı hedef klasörü de eklemeli). |
| "Kaçak tespiti: maskelenmesi gereken N değer çıktıda hâlâ okunuyor (Adres, Kişi adı). Dosya yazılmadı." | Güvenlik denetimi çıktıda silinmemiş bir değer buldu; **dosya yazılmaz**. Bu bir hata değil korumadır. Parantez içinde kalan değerlerin türleri yazar (değerin kendisi yazılmaz). Belgede başka yerde geçen aynı değer ya da web adresi olabilir; kullanıcı uygulamada o türdeki bulguları elle kontrol etsin. |
| Uyarı: "Taranmış 1 sayfa OCR ile okundu…" | Metin katmanı olmayan sayfa OCR ile okundu; OCR hata yapabilir. Çıktıyı kontrol edin. |
| Uyarı: "metin katmanı yok ve OCR dil dosyaları kurulu değil" (`read`) | Taranmış sayfa **okunamadı**; içeriği okuma çıktısında yer almaz, içindeki veri hakkında bir şey bilinmez. Kurulum bozuk olabilir: kullanıcıya bildirin (geliştirmede `BULUTBELGE_TESSDATA` ayarlayın). |
| Çıkış 1, `Hata (ocr_unavailable): OCR kullanılamıyor …` (`mask`) | Metin katmanı olmayan sayfa ya da görsel var ve OCR yapılamıyor; maskesiz kalacağı için **dosya yazılmadı**. Durun, kullanıcıya bildirin; uygulamanın yeniden kurulması gerekir. |

## MCP sunucusu (yerel, yalnızca stdio)

`bulutbelge mcp`, ajan aracının alt süreç olarak başlattığı bir MCP sunucusudur (protokol sürümü 2025-06-18). Ağ portu açmaz, hiçbir sunucuya bağlanmaz. Araçlar komutlarla **aynı** izinli klasör ve yazma izni denetimini, kural takımı üst sınırını ve işlem günlüğünü kullanır; ajana orijinal değer dönmez. Ajana kabuk izni vermeden kullanılabildiği için, ajan aracında belgelerin bulunduğu klasörlere doğrudan okuma izni vermemek kolaylaşır.

| Araç | Komut karşılığı | Döner |
|---|---|---|
| `bulutbelge_folders` | `folders` | İzinli klasörler ve yazma izni |
| `bulutbelge_scan` | `scan` | Yalnızca sayılar (veri türüne göre bulgu, sayfa, uyarı) |
| `bulutbelge_read` | `read` | Maskeli metin ve özet |
| `bulutbelge_mask` | `mask` | Özet; maskeli kopya yeni dosyaya yazılır (yazma izni gerekir) |

Araç girdileri: `path` (zorunlu, `folders` dışında), `profile` (isteğe bağlı), `target` (yalnızca `mask`). Sonuç metin ve `structuredContent` olarak döner (`--json` çıktısıyla aynı alanlar). Hata olursa sonuç `isError: true` olur; `structuredContent` içinde `code`, `message` ve `exit_code` (yukarıdaki çıkış kodlarıyla aynı anlam) bulunur.

Ajan adı (işlem günlüğüne girer): yapılandırmadaki `BULUTBELGE_AJAN` ortam değişkeni, yoksa ajan aracının kendini tanıttığı ad; ikisi de `--ajan` kuralına göre temizlenir.

**Claude Code:**

```
claude mcp add bulutbelge -- bulutbelge mcp
```

Komut PATH'te değilse tam yolu yazın, ör. varsayılan MSI kurulumunda `claude mcp add bulutbelge -- "C:\Program Files\BulutBelge\engine\bulutbelge-engine.exe" mcp` (bu kurulumdaki yol: `bulutbelge kilavuz --yonerge` çıktısındaki komut).

macOS'ta (kısa ad yok, tam yol gerekir):

```
claude mcp add bulutbelge -- /Applications/BulutBelge.app/Contents/Resources/engine/bulutbelge-engine mcp
```

**Cursor** (`~/.cursor/mcp.json` ya da projede `.cursor/mcp.json`):

```json
{"mcpServers": {"bulutbelge": {"command": "bulutbelge", "args": ["mcp"], "env": {"BULUTBELGE_AJAN": "cursor"}}}}
```

**Genel stdio yapılandırması** (Codex, Gemini CLI, Claude Desktop ve diğerleri): komut `bulutbelge` (ya da motorun tam yolu), argüman `mcp`, isteğe bağlı ortam değişkeni `BULUTBELGE_AJAN`. Örnek, Codex `~/.codex/config.toml`:

```
[mcp_servers.bulutbelge]
command = "bulutbelge"
args = ["mcp"]
```

JSON yapılandırmalarında Windows yolundaki ters eğik çizgiler ikilenir (`"C:\\Program Files\\..."`). `BULUTBELGE_GELISTIRME` değişkenini MCP yapılandırmasına eklemeyin (ayar klasörü yalnızca geliştirmede değişebilir).

**MCPB paketi (Claude Desktop ve MCPB destekleyen araçlar):** 0.1.2'den itibaren her sürümde platform başına bir `bulutbelge-mcp-<sürüm>-<platform>.mcpb` dosyası yayımlanır (`macos-arm64`, `windows-x64`, `linux-x64`; GitHub Releases, özetler SHA256SUMS'ta). Dosya ajan aracında açılınca (Claude Desktop: çift tıklama ya da Ayarlar › Uzantılar) sunucu yukarıdaki elle yapılandırmaya gerek kalmadan eklenir. Sunucu resmî MCP kaydında `io.github.bulutbelge/bulutbelge` adıyla listelenir. Paketin içindeki motor uygulamadakinin aynısıdır ve **masaüstü uygulamasının ayarlarını** kullanır: izinli klasörler, kural takımı ve işlem günlüğü uygulamada kalır, paket bunları kuramaz ve başka klasöre yönlendirilemez. Uygulama kurulu değilse (ya da hiç açılmamışsa) araçlar `app_not_installed` hatası döndürür (çıkış 3): kullanıcıya uygulamayı https://bulutbelge.com/indir adresinden kurup bir kez açmasını ve Ayarlar › Ajan erişimi bölümünden klasör izni vermesini söyleyin.

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

`scan --json`: `ok` (boolean, başarıda `true`) ve `summary` (tarama özeti; değer ve metin yoktur).

`scan --json` `summary` nesnesi (değer yok, yalnızca sayılar):

| Alan | Tür | Açıklama |
|---|---|---|
| `islem` | string | "tarama" |
| `kaynak` | string | Kaynak belgenin mutlak yolu |
| `kural_takimi` | string | Kullanılan kural takımının adı |
| `bulunan` | integer | Bulunan değer sayısı (maskelenmez, gösterilmez) |
| `turler` | object (string → integer) | Veri türü adına göre bulunan sayı |
| `sayfa` | integer | Sayfa sayısı (PDF/görsel sayfa, sunum slayt, arşiv dosya; diğerleri 1) |
| `uyarilar` | array of string | Uyarılar (ör. OCR, özel nitelikli veri ipucu); yoksa boş liste |

`scan --json` örneği (sahte veri):

```json
{"ok": true, "summary": {"islem": "tarama", "kaynak": "C:\\Belgeler\\ornek_basvuru.pdf",
 "kural_takimi": "Varsayılan", "bulunan": 3, "turler": {"Kişi adı": 1, "TC kimlik no": 1, "E-posta": 1},
 "sayfa": 2, "uyarilar": []}}
```

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

Aşağıdaki metni ajanın talimat dosyasına ekleyin: Claude Code için `CLAUDE.md` (ya da aşağıdaki beceri), Codex/Cursor/Gemini CLI ve diğerleri için `AGENTS.md` ya da sistem yönergesi. Komut yolunu kurulumunuza göre düzeltin. Aynı metin `bulutbelge kilavuz --yonerge` ile de alınır (komut yolu bu kuruluma göre yazılır).

### Cursor, Codex, Gemini CLI: `AGENTS.md` parçası

Projenin kökündeki `AGENTS.md` dosyasına (Gemini CLI için `GEMINI.md`) aşağıdaki yönergeyi ekleyin. Terminalden:

```
bulutbelge kilavuz --yonerge >> AGENTS.md
```

Windows PowerShell 5.1'de `>>` dosyayı UTF-16 yazar; bunun yerine `cmd /c "bulutbelge kilavuz --yonerge >> AGENTS.md"` kullanın.

### Claude Code becerisi (skill)

BulutBelge, Claude Code için hazır bir beceri dosyasıyla gelir: ne zaman kullanılacağı, komutlar, çıkış kodları ve örnek akış. Claude Code kişisel veri içerebilecek bir belgeyle çalışırken beceriyi kendisi seçer; önce `scan` ile bakar ve size maskeli okumayı önerir. Kurulum (kullanıcının tüm projeleri için):

```
mkdir -p ~/.claude/skills/bulutbelge
bulutbelge kilavuz --skill > ~/.claude/skills/bulutbelge/SKILL.md
```

Windows: `mkdir %USERPROFILE%\.claude\skills\bulutbelge` ve `cmd /c "bulutbelge kilavuz --skill > %USERPROFILE%\.claude\skills\bulutbelge\SKILL.md"`. Yalnızca bir proje için `.claude/skills/bulutbelge/SKILL.md` yoluna yazın. Beceri yalnızca öneri sunar; kullanıcı onayı olmadan maskeli kopya yazmaz.

### Yönerge metni

<!-- yonerge-basla -->
```markdown
## Yerel belgeler: önce BulutBelge ile bak

Kişisel veri içerebilecek yerel belgelerle (sözleşme, dilekçe, bordro, fatura, kimlik, CV, başvuru vb.;
PDF, Word, Excel, PowerPoint, XML, CSV, JSON, TXT, LOG, görsel) çalışırken dosyayı kabukla doğrudan açma,
okuma ya da içeriğini kopyalama. Önce BulutBelge ile değer göstermeden bak, kullanıcıya maskeli okumayı öner.
(Komut PATH'te değilse tam yolunu yaz; örn. bulutbelge-engine ya da python -m bulutbelge_engine.cli.)

- İzinler:        bulutbelge folders
- Bakma:          bulutbelge scan "<dosya>" --ajan <ajan-adın>
  Değer göstermez: veri türüne göre bulgu sayıları, sayfa sayısı ve uyarılar. Belge değişmez.
- Okuma:          bulutbelge read "<dosya>" --ajan <ajan-adın>
  Çıktı belgenin maskeli metnidir; sonda "--- BulutBelge özeti ---" bölümü vardır.
  Makine okunur çıktı için --json ekle: {"ok": true, "text": "...", "summary": {...}}.
- Maskeli kopya:  bulutbelge mask "<dosya>" [--hedef "<yeni dosya>"] --ajan <ajan-adın>
  Kaynak belgeye dokunulmaz, var olan dosyanın üzerine yazılmaz. Hedef izinli klasörde olmalı.

Kurallar:
- Kişisel veri içerebilecek bir belgede ilk adım bulutbelge scan: bulgu varsa kullanıcıya kaç tane ve
  hangi türde olduğunu söyle, maskeli okumayı (read) öner. Kullanıcı açıkça istemedikçe dosyayı
  doğrudan okuma; bu bir öneridir, kullanıcıyı zorlama.
- Maskeli kopyayı (mask) yalnızca kullanıcı istediğinde ya da onay verdiğinde yaz.
- Her çağrıdan sonra çıkış kodunu kontrol et. 3 (izin yok) ya da 4 (günlük yazılamıyor) ise işi
  durdur ve kullanıcıya hata mesajını aynen ilet. İzni aşmaya, dosyayı başka yoldan okumaya ya da
  kopyalamaya çalışma. Kullanıcıdan BulutBelge › Ayarlar › Ajan erişimi'nde izin vermesini iste.
- "Kaçak tespiti" hatası dosyanın yazılmadığı anlamına gelir; başka yoldan okumayı deneme,
  kullanıcıya bildir.
- Uyarılarda "OCR dil dosyaları kurulu değil" ya da "metin katmanı yok" geçiyorsa o sayfa
  okunamamıştır; içeriği çıktıda yoktur, çıktıyı belgenin tamamı sanma. mask "ocr_unavailable"
  hatası verirse dosya yazılmamıştır: dur ve kullanıcıya bildir.
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
- Taranmış sayfa ve fotoğrafın metin katmanı yoktur: OCR kuruluysa okunur ve maskelenir (OCR hata yapabilir); kurulu değilse (kurulum bozuk) `read` çıktısında içerikleri yer almaz ve özette uyarı olarak geçer; `mask` ise maskesiz sayfa yazmamak için reddedilir (çıkış 1, `ocr_unavailable`).
- Maske kaldırma ve kasa açma komut satırında yoktur.

## For agents (English summary)

BulutBelge masks personal data in local documents. Use it instead of reading documents directly.

- `bulutbelge folders` — show allowed folders and write permission (a human sets these in the app: Settings › Agent access).
- `bulutbelge scan <file> --ajan <agent-name>` — scan without changing the document; returns **counts only** (findings per data type, page count, warnings), never values. Add `--json` for machine-readable output.
- `bulutbelge read <file> --ajan <agent-name>` — print the **masked text** of the document (original values are never returned). Add `--json` for machine-readable output.
- `bulutbelge mask <file> [--hedef <new file>] --ajan <name>` — write a masked copy to a **new** file inside an allowed folder (never overwrites).
- Exit codes: 0 ok, 1 document/operation error (including "leak check" and "ocr_unavailable": file not written), 2 usage error, 3 not allowed, 4 audit log not writable. On 3 or 4 **stop** and relay the error to the user; do not try to bypass permissions.
- Do not guess or restore masked values. Masking is not 100% accurate; warn the user to review important output.
- `bulutbelge mcp` — local MCP server over **stdio only** (no network port): tools `bulutbelge_folders`, `bulutbelge_scan`, `bulutbelge_read`, `bulutbelge_mask` with the same permissions and audit log as the commands. Claude Code: `claude mcp add bulutbelge -- bulutbelge mcp`.
- `bulutbelge kilavuz --yonerge` prints a ready-to-paste instruction block for your `AGENTS.md`/`CLAUDE.md`; `bulutbelge kilavuz --skill` prints a Claude Code skill (`~/.claude/skills/bulutbelge/SKILL.md`).
- With a document that may hold personal data: run `scan` first, tell the user what was found and suggest a masked `read`; do not read the file directly and do not write masked copies without the user's consent.

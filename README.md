# BulutBelge

Kurum verisi ile yapay zekâ ajanları ve dış alıcılar arasında duran, amaç bazlı erişim ve maskeleme kapısı.

Tasarım: [docs/mimari/BulutBelge — Mimari Tasarım.pdf](docs/mimari/BulutBelge%20—%20Mimari%20Tasarım.pdf)

## Klasörler

| Klasör | İçerik |
|---|---|
| `core/` | Tespit motoru, belge işleyici, maskeleme çekirdeği (Python kütüphanesi) |
| `server/` | Paylaşım katmanı (FastAPI + MCP), politika, kasa, onay, denetim |
| `desktop/` | Tauri masaüstü uygulaması |
| `web/` | Web arayüzü ve profil düzenleyici |
| `docs/` | Tasarım, kararlar, takip dosyaları |

Uygulamayı kullanmak için: [docs/kullanici/masaustu.md](docs/kullanici/masaustu.md) (kurulum, `desktop/BASLAT.cmd` ile açma, adım adım maskeleme, ayarlar, sorunlar).

Yeni başlıyorsanız (kod): [docs/GELISTIRICI-REHBERI.md](docs/GELISTIRICI-REHBERI.md) (mimari, teknolojiler, kurulum, kodu görme ve değiştirme).

## Sorumluluk reddi

BulutBelge yardımcı bir araçtır; kişisel bilgileri %100 doğrulukla bulamayabilir ya da gizleyemeyebilir. "Bulunamadı", "gizlendi" ya da "iz kalmadı" bildirimleri kesin sonuç değildir; gizlenmiş belgeyi paylaşmadan önce kendiniz gözden geçirmelisiniz. Sorumluluk sınırı ve kabul için [Kullanım Koşulları](site/kosullar.html) (bulutbelge.com/kosullar.html). Uygulama ilk açılışta bu özeti gösterir ve kabul ister; Ayarlar › "Hakkında ve koşullar"da her zaman okunabilir. LICENSE eklendiğinde (TAKIP 1.83) garanti reddi hükümleri oraya da yazılır.

## Lisans

GNU Affero Genel Kamu Lisansı sürüm 3 (AGPL-3.0): bkz. [LICENSE](LICENSE). Üçüncü taraf bileşenlerin lisansları [NOTICE.md](NOTICE.md) içindedir. Yazılım "olduğu gibi" sunulur; ayrıntı yukarıdaki sorumluluk reddinde.

## Ekip ve çalışma düzeni

Ekip: üç kişi (ürün sahibi dahil). Çalışma kuralları için [CONTRIBUTING.md](CONTRIBUTING.md), iş takibi için [docs/TAKIP.md](docs/TAKIP.md).

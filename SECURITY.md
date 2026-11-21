# Güvenlik politikası

> Bildirim adresi `info@bulutbelge.com` (ürün sahibi kararı, 17 Kasım 2026). Yanıt süreleri ürün sahibi tarafından onaylanmıştır (21 Kasım 2026).

## Güvenlik açığı bildirimi

BulutBelge'de güvenlik açığı ya da belgeden kişisel veri sızdıran bir maskeleme hatası bulduysanız
**herkese açık bir kayıt (issue, forum, sosyal medya) açmayın**. Önce özel olarak bildirin:

- Bildirim adresi: [info@bulutbelge.com](mailto:info@bulutbelge.com) (konu satırına "Güvenlik" yazın). Aynı adres `https://bulutbelge.com/.well-known/security.txt` içinde de yayımlıdır.
- Bildirime ekleyin: etkilenen sürüm, işletim sistemi, adımlar, beklenen ve gerçekleşen sonuç.
- Belge örneği gönderirken **yalnızca sahte veri** kullanın. Gerçek kişisel veri içeren belge göndermeyin.

## Ne bekleyebilirsiniz

- Bildirimin alındığına dair yanıt: 5 iş günü içinde.
- Doğrulama ve düzeltme planı: 30 gün içinde (kritik açıklarda daha kısa).
- Düzeltme yayınlandıktan sonra sürüm notunda açığın özeti; isterseniz bildirenin adı anılır.

## Kapsam

Kapsama giren: masaüstü uygulaması, `core/` maskeleme kütüphanesi, komut satırı (`bulutbelge`), kurulum paketi.
Maskelemede kaçak (kopyada kalan kişisel veri), şifreli depolamanın aşılması, uygulamanın beklenmedik ağ
bağlantısı kurması ve yetkisiz dosya yazma/okuma öncelikli konulardır.

Kapsam dışı: sahte ya da bozuk belgelerle yapılan hizmet reddi denemeleri, fiziksel erişim gerektiren saldırılar,
üçüncü taraf bağımlılıklarındaki henüz yayımlanmamış açıklar (ilgili projeye bildirin; bize de haber verin).

## Desteklenen sürümler

Yalnızca en son yayımlanan sürüm düzeltme alır.

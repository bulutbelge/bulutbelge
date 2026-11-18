# Güvenlik politikası

> **TASLAK.** Bildirim adresi ve yanıt süreleri ürün sahibi tarafından onaylanıp doldurulacak (TAKIP 1.93).

## Güvenlik açığı bildirimi

BulutBelge'de güvenlik açığı ya da belgeden kişisel veri sızdıran bir maskeleme hatası bulduysanız
**herkese açık bir kayıt (issue, forum, sosyal medya) açmayın**. Önce özel olarak bildirin:

- Bildirim adresi: `<ürün sahibi tarafından belirlenecek>`
- Bildirime ekleyin: etkilenen sürüm, işletim sistemi, adımlar, beklenen ve gerçekleşen sonuç.
- Belge örneği gönderirken **yalnızca sahte veri** kullanın. Gerçek kişisel veri içeren belge göndermeyin.

## Ne bekleyebilirsiniz

- Bildirimin alındığına dair yanıt: `<süre belirlenecek>`.
- Doğrulama ve düzeltme planı: `<süre belirlenecek>`.
- Düzeltme yayınlandıktan sonra sürüm notunda açığın özeti; isterseniz bildirenin adı anılır.

## Kapsam

Kapsama giren: masaüstü uygulaması, `core/` maskeleme kütüphanesi, komut satırı (`bulutbelge`), kurulum paketi.
Maskelemede kaçak (kopyada kalan kişisel veri), şifreli depolamanın aşılması, uygulamanın beklenmedik ağ
bağlantısı kurması ve yetkisiz dosya yazma/okuma öncelikli konulardır.

Kapsam dışı: sahte ya da bozuk belgelerle yapılan hizmet reddi denemeleri, fiziksel erişim gerektiren saldırılar,
üçüncü taraf bağımlılıklarındaki henüz yayımlanmamış açıklar (ilgili projeye bildirin; bize de haber verin).

## Desteklenen sürümler

Yalnızca en son yayımlanan sürüm düzeltme alır.

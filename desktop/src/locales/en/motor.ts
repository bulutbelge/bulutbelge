// Motorun (Python) kullanıcıya ulaşan mesajları: hata yanıtları, tarama uyarıları, doğrulama nedenleri.
// Sabit metinler birebir, sayı ve ad içerenler {ad} kalıbı olarak yazılır (i18n.tsx kalıpları sırayla dener:
// daha özel kalıp, daha genel olandan ÖNCE gelmelidir). Belgeye yazılan çıktılar ([AD SOYAD], Kişi-1 vb.) çevrilmez.
export default {
  // Genel istek ve parametre hataları (protocol.py, commands.py)
  "Geçersiz JSON": "Invalid JSON",
  "İstek nesne olmalı": "The request must be an object",
  "params nesne olmalı": "params must be an object",
  "Bilinmeyen komut: {komut}": "Unknown command: {komut}",
  "'{ad}' gerekli": "'{ad}' is required",
  "'excluded_ids' liste olmalı": "'excluded_ids' must be a list",
  "'manual_cells' liste olmalı": "'manual_cells' must be a list",
  "'manual_areas' liste olmalı": "'manual_areas' must be a list",
  "'password' metin olmalı": "'password' must be text",
  "'drop_pages' sayı listesi olmalı": "'drop_pages' must be a list of numbers",
  "'terms' nesne olmalı": "'terms' must be an object",
  "'values' liste olmalı": "'values' must be a list",
  "'folders' liste olmalı": "'folders' must be a list",
  "Satır ve sütun seçimi yalnızca Excel için": "Row and column selection is only for Excel",
  "Satır/sütun seçimi biçimi geçersiz": "The row/column selection format is invalid",
  "Satır ya da sütun seçimi geçersiz": "The row or column selection is invalid",
  "Satır/sütun için geçersiz yöntem: {yontem}": "Invalid method for the row/column: {yontem}",
  "Excel sayfası bulunamadı: {sayfa}": "Excel sheet not found: {sayfa}",
  "Elle seçilen alan biçimi geçersiz": "The manually selected area format is invalid",
  "Parolayla koruma yalnızca PDF için": "Password protection is only for PDF",
  "Yalnızca Word belgeleri için": "Only for Word documents",
  "Yalnızca PowerPoint sunumları için": "Only for PowerPoint presentations",
  "Yalnızca Excel dosyaları için": "Only for Excel files",
  "Yalnızca XML, TXT ve CSV için": "Only for XML, TXT and CSV",
  "Dosya önizleme için çok büyük": "The file is too large to preview",
  "(yapıştırılan metin)": "(pasted text)",
  "Bilgi": "Information",

  // Kasa ve takma ad (mask.py, office.py, commands.py, settings.py)
  "Takma ad yöntemi için önce özel ifade kasasının kilidini açın": "To use the pseudonym method, first unlock the custom terms vault",
  "Takma ad için önce özel ifade kasasının kilidini açın": "To use pseudonyms, first unlock the custom terms vault",
  "Bilinmeyen yöntem: {yontem}": "Unknown method: {yontem}",
  "Parola en az {n} karakter olmalı": "The password must be at least {n} characters",

  // Kaydetme (commands.py, batch.py, office.py, pdf.py, textdoc.py)
  "Bu klasöre yazma izni yok. Başka bir klasör seçin. Mac'te: Sistem Ayarları › Gizlilik ve Güvenlik › Dosyalar ve Klasörler bölümünden BulutBelge'ye izin verin.":
    "There is no permission to write to this folder. Choose another folder. On a Mac: allow BulutBelge in System Settings › Privacy & Security › Files and Folders.",
  "Kopya kaydedilemedi: dosya hedef klasörde bulunamadı": "The copy could not be saved: the file was not found in the target folder",
  "Kopya seçtiğiniz klasöre değil, başka bir yere kaydedildi": "The copy was saved to a different place, not the folder you chose",
  "Kopya kaynak belgeyle aynı biçimde kalsın diye {uzanti} uzantısıyla kaydedildi": "The copy was saved with the {uzanti} extension so that it keeps the same format as the source document",
  "Seçtiğiniz adda bir dosya vardı; o dosyanın üzerine yazılmadı, kopya yeni bir adla kaydedildi": "A file with the name you chose already existed; it was not overwritten and the copy was saved under a new name",
  "Hedef, kaynak dosyanın kendisi olamaz": "The target cannot be the source file itself",
  "Hedef klasör bulunamadı": "Target folder not found",
  "Kaynak klasör bulunamadı": "Source folder not found",
  "Hedef klasör, kaynak klasörün kendisi ya da içinde olamaz": "The target folder cannot be the source folder or inside it",
  "Klasörde {n} belge var; tek seferde en fazla {en} işlenebilir": "The folder has {n} {n:document|documents}; at most {en} can be processed at once",
  "Dışa aktarma ayar klasörüne yazılamaz": "Export cannot be written to the settings folder",

  // Dosya açma (documents.py, office.py, pdf.py, textdoc.py, image.py, paste.py)
  "Dosya bulunamadı": "File not found",
  "Dosya çok büyük; en fazla {n} MB": "The file is too large; at most {n} MB",
  "Metin çok uzun; en fazla {n} karakter": "The text is too long; at most {n} characters",
  "Eski {uygulama} biçimi ({uzanti}) desteklenmiyor; {uygulama}'de {uzanti}x olarak kaydedip deneyin": "The old {uygulama} format ({uzanti}) is not supported; save it as {uzanti}x in {uygulama} and try again",
  "Bu dosya türü desteklenmiyor (uzantısız)": "This file type is not supported (no extension)",
  "Bu dosya türü desteklenmiyor ({uzanti})": "This file type is not supported ({uzanti})",
  "{ad} dosyası açılamadı (parolalı, bozuk ya da eski biçimde olabilir)": "The {ad} file could not be opened (it may be password-protected, corrupt or in an old format)",
  "{ad} dosyasının içeriği beklenmeyecek kadar büyük": "The contents of the {ad} file are unexpectedly large",
  "Dosya bir {ad} belgesi değil": "The file is not a {ad} document",
  "Belgede beklenmeyen DOCTYPE; güvenlik nedeniyle açılmadı": "The document has an unexpected DOCTYPE; it was not opened for security reasons",
  "Belgenin içi bozuk": "The document contents are corrupt",
  "Dosya PDF olarak açılamadı": "The file could not be opened as a PDF",
  "Dosya PDF değil": "The file is not a PDF",
  "Parolalı PDF'ler henüz desteklenmiyor": "Password-protected PDFs are not supported yet",
  "Dosya görsel olarak açılamadı": "The file could not be opened as an image",
  "Çok sayfalı görseller (TIFF, animasyon) henüz desteklenmiyor": "Multi-page images (TIFF, animation) are not supported yet",
  "Dosyanın karakter kodlaması tanınamadı": "The file's character encoding could not be recognized",
  "Dosyanın karakter kodlaması bozuk": "The file's character encoding is corrupt",
  "DOCTYPE içeren XML güvenlik nedeniyle desteklenmiyor": "XML with a DOCTYPE is not supported for security reasons",
  "Maskeleme XML yapısını bozacaktı; dosya yazılmadı": "Masking would have broken the XML structure; the file was not written",
  "OCR dil dosyaları bulunamadı": "OCR language files not found",
  "Yüz modeli yüklenemedi": "The face model could not be loaded",

  // Sayfa seçimi ve elle seçilen alan (pdf.py)
  "Elle seçilen alan geçersiz sayfada: {sayfa}": "The manually selected area is on an invalid page: {sayfa}",
  "Elle seçilen alan çok küçük ya da sayfanın dışında": "The manually selected area is too small or outside the page",
  "Sayfa yok": "No such page",
  "Görsel parolayla korunamaz; yalnızca PDF": "An image cannot be password-protected; PDF only",
  "Görselden sayfa çıkarılamaz": "A page cannot be removed from an image",
  "Çıkarılacak sayfa belgede yok": "The page to remove is not in the document",
  "Bütün sayfalar çıkarılamaz; en az bir sayfa kalmalı": "All pages cannot be removed; at least one page must remain",
  "{n} bulgunun belgedeki yeri bulunamadı. Bunları listeden çıkarıp elle kontrol edin.": "The location of {n} {n:finding|findings} in the document could not be found. Remove them from the list and check them manually.",
  "Parolalı kopya doğrulanamadı. Dosya yazılmadı.": "The password-protected copy could not be verified. The file was not written.",

  // Kaçak tespiti (rules.kacak_iletisi: office.py, pdf.py, textdoc.py, eposta.py, udf.py).
  // {turler} virgülle ayrılmış tür adlarıdır; i18n.tsx her adı ayrıca çevirir.
  "Kaçak tespiti: maskelenmesi gereken {n} değer belgenin başka bir yerinde (gizli alan, bağlantı, formül, özellik) hâlâ okunuyor ({turler}). Dosya yazılmadı.":
    "Leak detection: {n} {n:value|values} that should be masked can still be read elsewhere in the document (hidden field, link, formula, property) ({turler}). The file was not written.",
  "Kaçak tespiti: maskelenmesi gereken {n} değer belgenin başka bir yerinde hâlâ okunuyor ({turler}). Dosya yazılmadı.":
    "Leak detection: {n} {n:value|values} that should be masked can still be read elsewhere in the document ({turler}). The file was not written.",
  "Kaçak tespiti: maskelenmesi gereken {n} değer kopyada hâlâ okunuyor ({turler}). Dosya yazılmadı.":
    "Leak detection: {n} {n:value|values} that should be masked can still be read in the copy ({turler}). The file was not written.",
  "Kaçak tespiti: maskelenmesi gereken {n} değer çıktıda hâlâ okunuyor ({turler}). Dosya yazılmadı.":
    "Leak detection: {n} {n:value|values} that should be masked can still be read in the output ({turler}). The file was not written.",
  "Gizli alan": "Hidden field",

  // Tarama uyarıları (office.py, pdf.py, textdoc.py, image.py)
  "Belgede taranamayan {n} görsel var ({turler}): içlerindeki yazı ve yüzler taranmadı, maskeli kopyada olduğu gibi kalır. Kendiniz kontrol edin; gerekirse belgeyi PDF'e çevirip “Alan seç” ile maskeleyin.":
    "The document has {n} {n:image|images} that cannot be scanned ({turler}): text and faces in them were not scanned and stay as they are in the masked copy. Check them yourself; if needed, convert the document to PDF and mask them with “Select area”.",
  "Belgede {n} görsel var: UDF içindeki görseller taranmadı, maskeli kopyada olduğu gibi kalır. Kendiniz kontrol edin.":
    "The document has {n} {n:image|images}: images inside a UDF file were not scanned and stay as they are in the masked copy. Check them yourself.",
  "Belgede metin dışı başka dosyalar var; içleri taranmaz, maskeli kopyada olduğu gibi kalır.":
    "The document has other non-text files; their contents are not scanned and stay as they are in the masked copy.",
  "Belgede {n} grafik var. Grafikteki başlık, etiket ve önbellek değerleri de taranır; maskelenen sayı değerleri grafikte boş görünür.":
    "The document has {n} {n:chart|charts}. Chart titles, labels and cached values are scanned too; masked numbers appear empty in the chart.",
  "Çalışma kitabında {n} özet tablo (pivot) önbelleği var. Maskeli kopyada önbellek kayıtları silinir, önbellekteki değerler taranır; Excel tabloyu açılışta maskeli veriden yeniden oluşturur.":
    "The workbook has {n} pivot table {n:cache|caches}. In the masked copy the cache records are removed and cached values are scanned; Excel rebuilds the pivot table from the masked data when the file is opened.",
  "Belgedeki bir görselin meta verisi (EXIF) silinemedi. Dosya yazılmadı.":
    "The metadata (EXIF) of an image in the document could not be removed. The file was not written.",
  "Excel'de tarih biçimli hücreler (doğum tarihi gibi) sayı olarak saklanır ve bu türde bulunamaz; gerekirse sütunu metin olarak kaydedin.":
    "Date-formatted cells in Excel (such as a date of birth) are stored as numbers and cannot be found as this type; if needed, save the column as text.",
  "Seçilen satır ve sütunlarda {n} hücre silindi. Bu hücrelere başvuran formüllerin son hesaplanan değerleri başka hücrelerde kalabilir; gerekirse o hücreleri de seçin.":
    "{n} {n:cell was|cells were} cleared in the selected rows and columns. Formulas that refer to these cells may keep their last calculated values in other cells; select those cells too if needed.",
  "Belgede {n} gömülü dosya var (ör. e-Fatura PDF görünümü). İçerikleri taranamaz; maskeli kopyada silinir.":
    "The document has {n} embedded {n:file|files} (e.g. an e-invoice PDF view). Their contents cannot be scanned; they are removed in the masked copy.",
  "Görseldeki yazı OCR ile okundu. OCR hata yapabilir; sonucu önizlemede kontrol edin, kaçanları “Alan seç” ile ekleyin.":
    "The text in the image was read with OCR. OCR can make mistakes; check the result in the preview and add anything it missed with “Select area”.",
  "Taranmış {n} sayfa OCR ile okundu. OCR hata yapabilir; sonucu önizlemede kontrol edin, kaçanları “Alan seç” ile ekleyin.":
    "{n} scanned {n:page was|pages were} read with OCR. OCR can make mistakes; check the result in the preview and add anything it missed with “Select area”.",
  "Görselde imza ya da kaşe etiketi var. Taranmış görseldeki imza otomatik bulunamaz; önizlemede “Alan seç” ile işaretleyin.":
    "The image has a signature or stamp label. A signature in a scanned image cannot be found automatically; mark it in the preview with “Select area”.",
  "Sayfa {sayfalar}: imza ya da kaşe etiketi var. Taranmış görseldeki imza otomatik bulunamaz; önizlemede “Alan seç” ile işaretleyin.":
    "Page(s) {sayfalar}: there is a signature or stamp label. A signature in a scanned image cannot be found automatically; mark it in the preview with “Select area”.",
  "Görselde metin katmanı yok ve OCR dil dosyaları kurulu değil (kurulum bozuk olabilir). Otomatik tespit yapılamadı; bu sayfalar maskelenecekse maskeli kopya yazılmaz. BulutBelge'yi yeniden kurun.":
    "The image has no text layer and the OCR language files are not installed (the installation may be broken). Automatic detection could not be done; no masked copy is written while these pages are to be masked. Reinstall BulutBelge.",
  "Sayfa {sayfalar}: metin katmanı yok ve OCR dil dosyaları kurulu değil (kurulum bozuk olabilir). Otomatik tespit yapılamadı; bu sayfalar maskelenecekse maskeli kopya yazılmaz. BulutBelge'yi yeniden kurun.":
    "Page(s) {sayfalar}: there is no text layer and the OCR language files are not installed (the installation may be broken). Automatic detection could not be done; no masked copy is written while these pages are to be masked. Reinstall BulutBelge.",
  "Belgedeki görsellerde yazı okunamadı (OCR dil dosyaları kurulu değil); yalnızca yüz tarandı. OCR kullanılamadan maskeli kopya yazılmaz; BulutBelge'yi yeniden kurun.":
    "Text in the document's images could not be read (OCR language files are not installed); only faces were scanned. No masked copy is written without OCR; reinstall BulutBelge.",
  "OCR kullanılamıyor (kurulum bozuk olabilir): Görselin metin katmanı yok ve OCR yapılamadığı için içindeki kişisel veri bulunamıyor. Maskeleme yapılmadı, dosya yazılmadı. BulutBelge'yi yeniden kurun.":
    "OCR is not available (the installation may be broken): the image has no text layer and, without OCR, personal data in it cannot be found. Nothing was masked and the file was not written. Reinstall BulutBelge.",
  "OCR kullanılamıyor (kurulum bozuk olabilir): Sayfa {sayfalar}: metin katmanı yok ve OCR yapılamadığı için içindeki kişisel veri bulunamıyor. Maskeleme yapılmadı, dosya yazılmadı. BulutBelge'yi yeniden kurun.":
    "OCR is not available (the installation may be broken): page(s) {sayfalar} have no text layer and, without OCR, personal data on them cannot be found. Nothing was masked and the file was not written. Reinstall BulutBelge.",
  "OCR kullanılamıyor (kurulum bozuk olabilir): belgedeki {n} görselin metin katmanı yok ve OCR yapılamadığı için içindeki kişisel veri bulunamıyor. Maskeleme yapılmadı, dosya yazılmadı. BulutBelge'yi yeniden kurun.":
    "OCR is not available (the installation may be broken): {n} {n:image|images} in the document have no text layer and, without OCR, personal data in them cannot be found. Nothing was masked and the file was not written. Reinstall BulutBelge.",

  // Rust kabuğunun motor köprüsü hataları (src-tauri/src/engine.rs): arayüze aynı yoldan ulaşır
  "kilit hatası": "lock error",
  "motora yazılamadı: {neden}": "could not write to the engine: {neden}",
  "motordan okunamadı: {neden}": "could not read from the engine: {neden}",
  "motor beklenmedik şekilde kapandı": "the engine closed unexpectedly",
  "motordan geçersiz yanıt": "invalid response from the engine",
  "motor yanıtı istekle eşleşmiyor": "the engine response does not match the request",
  "motor başlatılamadı: {neden}": "the engine could not be started: {neden}",
  "motor stdin alınamadı": "could not get the engine stdin",
  "motor stdout alınamadı": "could not get the engine stdout",
  "uygulama yolu bulunamadı: {neden}": "the app path was not found: {neden}",
  "uygulama dizini bulunamadı": "the app directory was not found",

  // Bulgu nedenleri (detect.py, pdf.py): bulgu satırında ve ipucunda görünür
  "kontrol hanesi tutmuyor": "check digit does not match",
  "kart numarasına benziyor": "looks like a card number",
  "görsel": "image",
  "çizim": "drawing",
  "fotoğraf": "photo",
  "“{etiket}” etiketli; kontrol hanesi tutmuyor, yazım hatası olabilir": "labeled “{etiket}”; check digit does not match, may be a typo",
  "“{etiket}” etiketli; kontrol hanesi tutmuyor": "labeled “{etiket}”; check digit does not match",
  "“{etiket}” etiketli; kart numarasına benziyor": "labeled “{etiket}”; looks like a card number",
  "“{etiket}” etiketli; 11 hane değil": "labeled “{etiket}”; not 11 digits",
  "“{etiket}” etiketli; {kaynak}": "labeled “{etiket}”; {kaynak}",
  "“{etiket}” etiketli;": "labeled “{etiket}”",
  "“{etiket}” etiketli; ": "labeled “{etiket}”",
  "'{ad}' kalıbı bu belgede çok uzun sürdü; kalıbı sadeleştirin": "The pattern '{ad}' took too long on this document; simplify the pattern",
  "'{ad}' kalıbı geçersiz: {neden}": "The pattern '{ad}' is invalid: {neden}",
  "'{ad}' kalıbı boş metinle eşleşiyor; her yeri maskelerdi": "The pattern '{ad}' matches empty text; it would mask everywhere",
  "Bilinmeyen veri türü: {tur}": "Unknown data type: {tur}",

  // İşlem günlüğü (audit.py, journal.py)
  "İşlem günlüğü yazılamıyor; güvenlik için işlem yapılmadı": "The activity log cannot be written; nothing was done for safety",
  "İşlem günlüğü okunamadı (Günlük okunamıyor ({tur}))": "The activity log could not be read (the log cannot be read ({tur}))",
  "İşlem günlüğü okunamadı (Günlüğün {n}. satırı okunamadı)": "The activity log could not be read (line {n} of the log could not be read)",
  "İşlem günlüğü okunamadı ({neden})": "The activity log could not be read ({neden})",
  "Günlük kilidi alınamadı": "The log lock could not be acquired",
  "Günlüğün son kaydı okunamadı": "The last log entry could not be read",
  "Günlük yazılamıyor ({tur})": "The log cannot be written ({tur})",
  "Günlük okunamıyor ({tur})": "The log cannot be read ({tur})",
  "Günlüğün {n}. satırı okunamadı": "Line {n} of the log could not be read",
  "Kayıt okunamıyor": "The entry cannot be read",
  "Zincir kopuk: önceki kayıt silinmiş ya da değiştirilmiş": "Broken chain: the previous entry was deleted or changed",
  "Sıra numarası beklenmeyen": "Unexpected sequence number",
  "Kayıt sonradan değiştirilmiş": "The entry was changed afterwards",
  "Kayıt mührü (HMAC) tutmuyor: kayıt değiştirilmiş ya da zincir anahtarsız yeniden hesaplanmış": "The entry seal (HMAC) does not match: the entry was changed or the chain was recomputed without the key",
  "Mühürsüz kayıt: anahtarlı mühür zorunluyken HMAC'siz kayıt eklenmiş": "Unsealed entry: an entry without HMAC was added where the keyed seal is required",
  "Günlük mühür anahtarı okunamadı": "The log seal key could not be read",
  "Günlük mühür anahtarı geçersiz": "The log seal key is invalid",
  "Günlük mühür anahtarı bulunamadı; mühürlü kayıtlar doğrulanamaz. Anahtarı geri koyun ya da eski günlüğü başka bir yere taşıyın": "The log seal key was not found; sealed entries cannot be verified. Restore the key or move the old log elsewhere",
  "Günlük mühür anahtarı yazılamadı ({tur})": "The log seal key could not be written ({tur})",

  // Ayarlar, profil ve kasa (settings.py)
  "Ayar klasörü bilinmiyor": "The settings folder is unknown",
  "Profil nesne olmalı": "The rule set must be an object",
  "Profilin kimliği ve adı olmalı": "A rule set needs an ID and a name",
  "En az bir profil olmalı": "There must be at least one rule set",
  "Profil kimlikleri tekrarlanıyor": "Rule set IDs are duplicated",
  "Kural takımı bulunamadı": "Rule set not found",
  "Klasör yolu boş olamaz": "The folder path cannot be empty",
  "Klasör tam yol olmalı: {yol}": "The folder must be a full path: {yol}",
  "Klasör bulunamadı: {yol}": "Folder not found: {yol}",
  "Klasör değil: {yol}": "Not a folder: {yol}",
  "Sürücünün tamamına izin verilemez; bir klasör seçin": "A whole drive cannot be allowed; choose a folder",
  "Kullanıcı klasörünün tamamına izin verilemez; bir alt klasör seçin": "The whole user folder cannot be allowed; choose a subfolder",
  "Uygulamanın ayar klasörü (ve onu içeren klasör) izinli olamaz": "The app's settings folder (and the folder containing it) cannot be allowed",
  "En fazla {n} klasör": "At most {n} folders",

  // Hazır kural takımı adları (settings.py)
  "Varsayılan": "Default",
  "Müşteriye": "To customer",
  "Denetçiye": "To auditor",
  "Kurum içine": "Internal use",

  // Görselin meta verisi uyarısı (image.py): öğe birleşimleri
  "Görselin meta verisinde konum (GPS) var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains location (GPS). All metadata is removed from the saved file.",
  "Görselin meta verisinde cihaz bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains device information. All metadata is removed from the saved file.",
  "Görselin meta verisinde konum (GPS), cihaz bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains location (GPS), device information. All metadata is removed from the saved file.",
  "Görselin meta verisinde çekim tarihi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains capture date. All metadata is removed from the saved file.",
  "Görselin meta verisinde konum (GPS), çekim tarihi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains location (GPS), capture date. All metadata is removed from the saved file.",
  "Görselin meta verisinde cihaz bilgisi, çekim tarihi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains device information, capture date. All metadata is removed from the saved file.",
  "Görselin meta verisinde konum (GPS), cihaz bilgisi, çekim tarihi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains location (GPS), device information, capture date. All metadata is removed from the saved file.",
  "Görselin meta verisinde sahip bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains owner information. All metadata is removed from the saved file.",
  "Görselin meta verisinde konum (GPS), sahip bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains location (GPS), owner information. All metadata is removed from the saved file.",
  "Görselin meta verisinde cihaz bilgisi, sahip bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains device information, owner information. All metadata is removed from the saved file.",
  "Görselin meta verisinde konum (GPS), cihaz bilgisi, sahip bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains location (GPS), device information, owner information. All metadata is removed from the saved file.",
  "Görselin meta verisinde çekim tarihi, sahip bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains capture date, owner information. All metadata is removed from the saved file.",
  "Görselin meta verisinde konum (GPS), çekim tarihi, sahip bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains location (GPS), capture date, owner information. All metadata is removed from the saved file.",
  "Görselin meta verisinde cihaz bilgisi, çekim tarihi, sahip bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains device information, capture date, owner information. All metadata is removed from the saved file.",
  "Görselin meta verisinde konum (GPS), cihaz bilgisi, çekim tarihi, sahip bilgisi var. Kaydedilen dosyada tüm meta veri silinir.":
    "The image metadata contains location (GPS), device information, capture date, owner information. All metadata is removed from the saved file.",

  // Veri türüne göre geçersiz yöntem hatası (rules.py): tür adı sabit olduğu için ayrı ayrı yazılır
  "Kişi adı için geçersiz yöntem: {method}": "Invalid method for Person name: {method}",
  "TC kimlik no için geçersiz yöntem: {method}": "Invalid method for National ID no: {method}",
  "Vergi kimlik no için geçersiz yöntem: {method}": "Invalid method for Tax ID no: {method}",
  "IBAN için geçersiz yöntem: {method}": "Invalid method for IBAN: {method}",
  "Kredi kartı no için geçersiz yöntem: {method}": "Invalid method for Credit card no: {method}",
  "Telefon için geçersiz yöntem: {method}": "Invalid method for Phone: {method}",
  "E-posta için geçersiz yöntem: {method}": "Invalid method for Email: {method}",
  "Adres için geçersiz yöntem: {method}": "Invalid method for Address: {method}",
  "Doğum tarihi için geçersiz yöntem: {method}": "Invalid method for Date of birth: {method}",
  "Araç plakası için geçersiz yöntem: {method}": "Invalid method for License plate: {method}",
  "IP adresi için geçersiz yöntem: {method}": "Invalid method for IP address: {method}",
  "Tutar ve fiyat için geçersiz yöntem: {method}": "Invalid method for Amounts and prices: {method}",
  "Pasaport no için geçersiz yöntem: {method}": "Invalid method for Passport no: {method}",
  "Sürücü belgesi no için geçersiz yöntem: {method}": "Invalid method for Driver's license no: {method}",
  "SGK / sicil no için geçersiz yöntem: {method}": "Invalid method for Social security / registry no: {method}",
  "MERSİS no için geçersiz yöntem: {method}": "Invalid method for MERSIS no: {method}",
  "Müşteri / poliçe no için geçersiz yöntem: {method}": "Invalid method for Customer / policy no: {method}",
  "Yüz (fotoğraf) için geçersiz yöntem: {method}": "Invalid method for Face (photo): {method}",
  "İmza ve kaşe için geçersiz yöntem: {method}": "Invalid method for Signature and stamp: {method}",
  "Elle seçilen alan için geçersiz yöntem: {method}": "Invalid method for Manually selected area: {method}",
  "Özel ifade için geçersiz yöntem: {method}": "Invalid method for Custom term: {method}",
  "Özel kalıp için geçersiz yöntem: {method}": "Invalid method for Custom pattern: {method}",
  "e-posta adresindeki adla eşleşiyor": "matches a name in an email address in the document",
  "belge başında ad soyad gibi duruyor": "looks like a name at the top of the document",
  "ad listesindeki bir ada yazım olarak çok benziyor": "spelled very similarly to a name in the name list",
  "ad ve yaygın bir soyad (soyad küçük harfle yazılmış)": "a first name and a common surname (surname written in lowercase)",
  "web adresinde bitişik yazılmış ad ve soyad": "a first name and surname written together in a web address",
  "web adresinde ad ve soyad": "a first name and surname in a web address",
  "web adresinde ad gibi duran bir parça": "a part of a web address that looks like a name",
} as Record<string, string>;

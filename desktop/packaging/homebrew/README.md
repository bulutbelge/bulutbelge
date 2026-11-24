# Homebrew cask (macOS)

`bulutbelge.rb`, kendi tap depomuz `bulutbelge/homebrew-tap` içindeki `Casks/bulutbelge.rb` dosyasının kaynağıdır. Ana Homebrew deposu (`homebrew/cask`) kendi başvurduğumuz projelerde 225 yıldız / 90 çatal eşiği ister; o eşiğe kadar kendi tap'imiz kullanılır.

Kullanıcı tarafı:

```bash
brew tap bulutbelge/tap
brew trust bulutbelge/tap
brew install --cask bulutbelge/tap/bulutbelge
```

Homebrew 7 ve sonrası, dışarıdan eklenen depoları kullanmadan önce `brew trust` ile açık onay ister.

Cask uygulamayı `/Applications`'a kurar ve motoru `bulutbelge` adıyla PATH'e bağlar (sembolik bağlantıyla motor çalışır, 24 Kasım 2026'da denendi). Böylece macOS'ta da `bulutbelge mcp` ve `claude mcp add bulutbelge -- bulutbelge mcp` kısa yazımı geçerli olur.

Her sürümde: `version` ve `sha256` (sürümün `SHA256SUMS` dosyasındaki `.dmg` satırı) güncellenir, tap deposuna aynı dosya kopyalanır.

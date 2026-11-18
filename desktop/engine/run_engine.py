# PyInstaller giriş noktası (paket içi göreli içe aktarma için ayrı dosya).
#
# Masaüstü uygulaması motoru argümansız başlatır (stdin/stdout protokolü). Ajan ve kullanıcı aynı
# dosyayı komutla çağırır: `bulutbelge-engine read <dosya>`, `mask`, `folders` (her işletim sisteminde).
import sys

if len(sys.argv) > 1:
    from bulutbelge_engine.cli import main
else:
    from bulutbelge_engine.__main__ import main

main()

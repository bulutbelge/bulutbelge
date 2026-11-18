@echo off
rem BulutBelge masaustu uygulamasini gelistirme modunda acar.
rem Cift tiklayin. Ilk acilis birkac dakika surebilir (derleme); sonrakiler hizlidir.
rem Ayrinti: docs\kullanici\masaustu.md, "Uygulamayi acmak" bolumu.

chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

echo.
echo  BulutBelge baslatiliyor...
echo.

where node >nul 2>nul || (
  echo  [EKSIK] Node.js kurulu degil. https://nodejs.org adresinden LTS surumunu kurun.
  goto :hata
)
where cargo >nul 2>nul || (
  echo  [EKSIK] Rust kurulu degil. https://rustup.rs adresinden rustup-init.exe ile kurun.
  goto :hata
)
if not exist "engine\.venv\Scripts\python.exe" (
  echo  [EKSIK] Python motor ortami yok. Kilavuzdaki "Ilk kurulum" adimlarini uygulayin:
  echo          python -m venv engine\.venv
  echo          engine\.venv\Scripts\python -m pip install -e "..\core[dev]" -e "engine[dev]"
  goto :hata
)
if not exist "node_modules" (
  echo  Arayuz paketleri kuruluyor - yalnizca ilk seferde...
  call npm install || goto :hata
)
if not exist "engine\tessdata\tur.traineddata" (
  echo  OCR dil dosyalari indiriliyor - yalnizca ilk seferde, yaklasik 9 MB...
  engine\.venv\Scripts\python engine\tessdata_indir.py || goto :hata
)

echo  Uygulama aciliyor. Bu pencereyi kapatmayin; kapatirsaniz uygulama da kapanir.
echo.
call npm run tauri dev
goto :eof

:hata
echo.
echo  Uygulama acilamadi. Yukaridaki mesaja bakin.
pause
exit /b 1

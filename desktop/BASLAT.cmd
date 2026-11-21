@echo off
rem BulutBelge masaustu uygulamasini gelistirme modunda acar.
rem Cift tiklayin. Ilk acilis birkac dakika surebilir (derleme); sonrakiler hizlidir.
rem Hangi klasorden calistirirsaniz o klasordeki kod acilir (git calisma kopyasi). Motor ortami (engine\.venv)
rem baska bir klasorun cekirdegine bagliysa otomatik bu klasore baglanir; eski surum acilmasin diye.
rem Ayrinti: docs\kullanici\masaustu.md

chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

echo.
echo  BulutBelge baslatiliyor...
where git >nul 2>nul && (
  for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "DAL=%%b"
  for /f "delims=" %%h in ('git rev-parse --short HEAD 2^>nul') do set "SURUM=%%h"
  echo  Klasor: %~dp0
  echo  Dal: !DAL!  Surum: !SURUM!
)
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
  where python >nul 2>nul || (
    echo  [EKSIK] Python kurulu degil. https://www.python.org adresinden 3.12 surumunu kurun.
    goto :hata
  )
  echo  Python motor ortami kuruluyor - yalnizca ilk seferde, birkac dakika surer...
  python -m venv engine\.venv || goto :hata
  engine\.venv\Scripts\python -m pip install -e "..\core[dev]" -e "engine[dev]" || goto :hata
)

rem Motor ortami bu klasorun cekirdegine bagli mi? Degilse (ornegin baska klasorden kopyalanmis) yeniden bagla.
set "CEKIRDEK="
for /f "delims=" %%i in ('engine\.venv\Scripts\python -c "import os,bulutbelge_core;print(os.path.dirname(os.path.dirname(os.path.abspath(bulutbelge_core.__file__))))" 2^>nul') do set "CEKIRDEK=%%i"
for %%i in ("%~dp0..\core") do set "BEKLENEN=%%~fi"
if /i not "%CEKIRDEK%"=="%BEKLENEN%" (
  echo  Motor ortami baska bir klasore bagliydi ^(%CEKIRDEK%^); bu klasore baglaniyor...
  engine\.venv\Scripts\python -m pip install -q -e "..\core[dev]" -e "engine[dev]" || goto :hata
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

@echo off
chcp 65001 >nul
title 大阪支社 配布コスト管理アプリ ランチャー
cd /d "C:\Users\moro\posting-automation"
set "STREAMLIT=C:\Users\moro\AppData\Local\Programs\Python\Python311\Scripts\streamlit.exe"
set "URL=http://localhost:8502/"

echo 大阪支社のアプリを起動しています...

REM --- すでに起動中なら、いったん止めて「最新の内容」で立ち上げ直す ---
REM     （画面ファイルは毎回読み直されるが、common\*.py は起動時のまま残るため、
REM      止めずに開くと更新が反映されずエラーになることがある）
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://localhost:8502/_stcore/health').Content } catch { '' }" | findstr /i "ok" >nul
if not %errorlevel%==0 goto notrunning

echo 起動中のアプリを停止しています（最新の内容で開き直すため）...
REM 8502番を使っているプロセスだけを止める（テレアポアプリ8501などは止めません）
powershell -NoProfile -Command "$ids = @(); try { $ids = @(Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique) } catch {}; foreach ($procId in $ids) { if ($procId -gt 0) { try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {} } }"

REM --- ポートが空くまで最大10秒待つ ---
set /a stops=0
:stopwait
timeout /t 1 >nul
set /a stops+=1
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if %errorlevel%==0 goto stopped
if %stops% geq 10 goto stopped
goto stopwait

:stopped
echo 停止しました。最新の内容で起動し直します。

:notrunning

REM --- サーバーを起動（バックグラウンド・ウィンドウ非表示） ---
echo サーバーを起動中です。しばらくお待ちください...
REM --server.address 0.0.0.0 = 同じWi-Fiのスマホ・他PCからも開けるようにする
powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath '%STREAMLIT%' -ArgumentList 'run','app.py','--server.port','8502','--server.address','0.0.0.0','--server.headless','true' -WorkingDirectory 'C:\Users\moro\posting-automation'"

REM --- 起動完了(health=ok)まで最大30秒待つ ---
set /a tries=0
:waitloop
timeout /t 2 >nul
set /a tries+=1
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://localhost:8502/_stcore/health').Content } catch { '' }" | findstr /i "ok" >nul
if %errorlevel%==0 goto ready
if %tries% geq 15 goto timeout_err
goto waitloop

:ready
echo 起動しました。ブラウザを開きます。
echo.
echo ---------------------------------------------
echo  スマホから使う場合（同じWi-Fiに繋いでください）
REM パイプ(^|)はここでは正しく渡らないため、.Where() でパイプを使わずに書く
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "@(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue).Where({ $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' })[0].IPAddress"`) do echo   http://%%I:8502/
echo.
echo  ※ 初回はWindowsのファイアウォールの確認が出ることがあります。
echo    「アクセスを許可する」を押してください。
echo ---------------------------------------------
echo.
start "" "%URL%"
timeout /t 5 >nul
exit /b 0

:timeout_err
echo.
echo 起動確認に時間がかかっています。手動でブラウザから %URL% を開いてみてください。
echo （初回や更新後は少し時間がかかることがあります）
start "" "%URL%"
pause
exit /b 1

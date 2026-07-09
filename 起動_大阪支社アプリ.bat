@echo off
chcp 65001 >nul
title 大阪支社 配布コスト管理アプリ ランチャー
cd /d "C:\Users\moro\posting-automation"
set "STREAMLIT=C:\Users\moro\AppData\Local\Programs\Python\Python311\Scripts\streamlit.exe"
set "URL=http://localhost:8502/"

echo 大阪支社のアプリを起動しています...

REM --- すでに起動中か確認 ---
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://localhost:8502/_stcore/health').Content } catch { '' }" | findstr /i "ok" >nul
if %errorlevel%==0 (
    echo すでに起動中です。ブラウザを開きます。
    start "" "%URL%"
    timeout /t 2 >nul
    exit /b 0
)

REM --- サーバーを起動（バックグラウンド・ウィンドウ非表示） ---
echo サーバーを起動中です。しばらくお待ちください...
powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath '%STREAMLIT%' -ArgumentList 'run','app.py','--server.port','8502','--server.headless','true' -WorkingDirectory 'C:\Users\moro\posting-automation'"

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
start "" "%URL%"
timeout /t 2 >nul
exit /b 0

:timeout_err
echo.
echo 起動確認に時間がかかっています。手動でブラウザから %URL% を開いてみてください。
echo （初回や更新後は少し時間がかかることがあります）
start "" "%URL%"
pause
exit /b 1

@echo off
chcp 65001 > nul
echo ============================================================
echo      591 Telegram Bot GitHub 雲端一鍵部署工具
echo ============================================================
echo.
echo 請確認您已在 GitHub 上建立了一個新的私有 (Private) 儲存庫。
echo.
set /p repo_url="請貼上您的 GitHub 儲存庫網址 (例如 https://github.com/username/repo.git): "

if "%repo_url%"=="" (
    echo.
    echo [錯誤] 網址不可為空！
    echo.
    pause
    exit /b
)

echo.
echo [*] 正在連結 GitHub 儲存庫...
git remote remove origin >nul 2>&1
git remote add origin %repo_url%

echo [*] 正在上傳程式碼到 GitHub...
echo [提示] 若畫面跳出 GitHub 登入驗證視窗，請點選登入並完成瀏覽器授權。
echo.
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo [✓] 程式碼成功部署至 GitHub！
    echo ============================================================
    echo.
    echo 接下來請至您的 GitHub 網頁完成最後兩步設定：
    echo 1. 前往儲存庫網頁的 Settings ➔ Secrets and variables ➔ Actions
    echo    新增以下兩個 Secret 變數：
    echo    - TELEGRAM_BOT_TOKEN
    echo    - TELEGRAM_CHAT_ID
    echo 2. 前往 Settings ➔ Actions ➔ General ➔ 往下捲動至 Workflow permissions
    echo    將選項更改為 "Read and write permissions" 並存檔。
    echo.
    echo 大功告成！每天晚上 8:00 點雲端就會自動替您抓取最新房源囉！
) else (
    echo.
    echo [X] 上傳失敗，請檢查網址是否正確，或您是否已登入 GitHub 帳號。
)
echo.
pause

@echo off
chcp 65001 > nul
echo ============================================================
echo      591租屋機器人 - Windows 自動排程安裝工具
echo ============================================================
echo.
echo 此工具會自動將機器人註冊到 Windows 工作排程器中。
echo 機器人將會在每天晚上 8:00 (20:00) 於背景自動執行，並發送 Telegram 通知。
echo 執行時使用背景靜態啟動，完全不會彈出任何視窗，不會打擾您的日常使用。
echo.

:: 檢查 Python 是否存在
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [錯誤] 系統中找不到 Python。請確認您已安裝 Python 並勾選 "Add Python to PATH"。
    echo.
    pause
    exit /b
)

set "script_path=D:\antigravity\telegram_591_bot\bot.py"
set "task_name=591_Telegram_Bot"

echo [*] 正在向 Windows 系統註冊排程工作...
:: 建立工作排程：每天 20:00 執行，使用 powershell 隱藏視窗執行 python
schtasks /create /tn "%task_name%" /tr "powershell -WindowStyle Hidden -Command \"python '%script_path%' --once\"" /sc daily /st 20:00 /f

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo [✓] 註冊排程成功！
    echo ============================================================
    echo 機器人現在已成功加入 Windows 系統排程。
    echo 每天晚上 8:00，電腦會自動在背景啟動它，抓完新房源並發送通知後自動關閉。
    echo.
    echo 提示：若您想立刻測試，可以在 CMD 輸入下指令手動測試執行：
    echo schtasks /run /tn "%task_name%"
) else (
    echo.
    echo [X] 註冊失敗。這通常需要管理員權限，請右鍵點擊此檔案並選擇「以系統管理員身分執行」。
)
echo.
pause

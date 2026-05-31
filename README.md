# 591 租屋網 Telegram 自動推播機器人

這是一個使用 Python 開發的 591 租屋網新物件監控與推播工具。它可以幫助您即時監控特定地區與篩選條件下的租屋資訊，並在有新物件發佈時，第一時間將資訊（包含照片、租金、坪數、地址等）推播至您的 Telegram 頻道、群組或個人對話中。

---

## 🛠️ 功能特點
* **自動繞過 CSRF 驗證**：自動模擬瀏覽器請求並處理首頁 cookies 和 `csrf-token`，繞過 591 的 `419` 限制。
* **精美 Telegram 推播**：自動識別物件的封面圖片，以圖文並茂的形式發送推播訊息，並提供直達房屋詳情頁面的連結。
* **防重複通知**：本地保存歷史已讀 `seen_listings.json`，即使重啟程式也不會重複推播相同的房屋。
* **首輪背景初始化**：首次執行時會自動載入當前所有租屋作為已讀，避免第一次啟動時瞬間塞爆您的 Telegram。
* **自訂搜尋參數**：支援完整的 591 API 參數（如地區、租屋類型、坪數、樓層等）。

---

## 🚀 快速開始步驟

### 第一步：申請 Telegram Bot
1. 在 Telegram 中搜尋官方帳號 [@BotFather](https://t.me/BotFather)。
2. 發送指令 `/newbot`，並按照指示設定機器人的名稱與帳號（Username，必須以 `bot` 結尾）。
3. 申請成功後，BotFather 會給您一串 **HTTP API Token**（格式例如：`123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`）。請保存好此 Token。

### 第二步：取得您的 Chat ID
您需要讓機器人知道要把訊息傳給誰（個人、群組或頻道）。
1. **個人**：
   * 搜尋並點擊 [@userinfobot](https://t.me/userinfobot) 並發送 `/start`。
   * 它會回傳您的 `Id`（一串數字，例如：`987654321`）。
2. **群組 / 頻道**：
   * 將您的 Bot 邀請進該群組或頻道。
   * 將 Bot 設為管理員（如果是頻道）。
   * 隨便發送一則訊息到該群組，接著在瀏覽器打開以下網址（將 `{TOKEN}` 替換成您的 Bot Token）：
     `https://api.telegram.org/bot{TOKEN}/getUpdates`
   * 在回傳的 JSON 之中，尋找 `"chat":{"id": -100xxxxxxxxxx}`，該負數就是您的群組/頻道 `chat_id`。

### 第三步：安裝依賴環境
本專案僅需安裝 `requests` 套件：
```bash
pip install requests
```

### 第四步：配置設定檔 `config.json`
打開 [config.json](file:///D:/antigravity/telegram_591_bot/config.json) 進行編輯：
```json
{
    "telegram_bot_token": "您的_TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID",
    "check_interval_seconds": 86400,
    "region": 1,
    "kind": 0,
    "rentprice_min": 0,
    "rentprice_max": 30000,
    "other_params": {},
    "run_once": false
}
```

#### 📌 常用代碼參考：
* **`region` (縣市代碼)**:
  * `1`: 台北市 | `3`: 新北市 | `6`: 桃園市 | `8`: 新竹市 | `10`: 新竹縣 | `12`: 台中市 | `21`: 台南市 | `22`: 高雄市
* **`kind` (租屋類型)**:
  * `0`: 全部 | `1`: 整層住家 | `2`: 獨立套房 | `3`: 分租套房 | `4`: 雅房
* **`other_params` (自訂篩選參數)**:
  * 如果您想篩選坪數介於 10~20 坪，可以寫成：
    ```json
    "other_params": {
        "area": "10,20"
    }
    ```
  * 如果您想篩選電梯大樓，可以寫成（`shape` 參數）：
    ```json
    "other_params": {
        "shape": "2"
    }
    ```

### 第五步：啟動機器人
在專案目錄下執行：
```bash
python bot.py
```

---

## ☁️ 雲端自動執行部署指引 (GitHub Actions)

如果您不想把個人電腦開著，本專案已內建 **GitHub Actions 自動排程工作流程**，可以免費、全自動在雲端每天執行一次並推播！

### 步驟：
1. **在 GitHub 建立儲存庫 (Repository)**:
   * 在您的 GitHub 帳號下建立一個新的儲存庫（私有 Private 或公開 Public 皆可，建議設為 **Private** 以保護您的隱私資料）。
2. **上傳本專案檔案**:
   * 將此目錄下的所有檔案（包含隱藏資料夾 `.github`）提交並 Push 到該 GitHub 儲存庫。
   * *提示：請勿將您的實體 Token 寫在 `config.json` 中上傳，雲端版會直接讀取 GitHub 的 Secrets 設定！*
3. **設定 GitHub Secrets (安全環境變數)**:
   * 開啟您 GitHub 儲存庫的網頁 ➔ 點擊 **Settings** ➔ **Secrets and variables** ➔ **Actions**。
   * 點選 **New repository secret**，分別新增以下兩個 Secret：
     * **`TELEGRAM_BOT_TOKEN`**: 填入您的 Telegram Bot Token。
     * **`TELEGRAM_CHAT_ID`**: 填入您的 Telegram Chat ID。
4. **設定儲存庫寫入權限 (重要)**:
   * 為了讓 GitHub Actions 能夠記錄「哪些物件已經通知過」，我們需要讓它有權限更新 `seen_listings.json` 並推回儲存庫。
   * 在儲存庫網頁點擊 **Settings** ➔ **Actions** ➔ **General** ➔ 捲動到 **Workflow permissions**。
   * 將權限更改為 **Read and write permissions**，並點擊 **Save**。
5. **啟動排程**:
   * 預設的排程設定在 [.github/workflows/run_bot.yml](file:///D:/antigravity/telegram_591_bot/.github/workflows/run_bot.yml) 中，設定為每天的台北時間 **晚上 8:00 (20:00)** 自動執行。
   * 您可以點擊 GitHub 儲存庫網頁的 **Actions** 分頁 ➔ 選擇 **Run 591 Telegram Bot** ➔ 點選 **Run workflow** 來手動立刻測試執行！

---

## ⚠️ 法律與免責聲明
* **個人學術研究**：本專案僅供程式開發、網路技術研究與個人學習交流使用。
* **遵守使用規範**：請遵守 591 的 `robots.txt` 規範，禁止將本程式用於任何商業用途。
* **調整頻率**：請不要將 `check_interval_seconds` 設定得太低（建議至少維持 300 秒 / 5 分鐘以上），頻繁且大量的請求將會造成 591 伺服器負載，並可能導致您的 IP 被封鎖，甚至面臨法律風險。

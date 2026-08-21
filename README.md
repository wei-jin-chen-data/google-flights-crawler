# Google Flights 自動化監測系統

本系統為基於 Python 與 Playwright 開發的高效能機票價格自動監測引擎，支援多航線、動態天數、去回程詳細時間與價格抓取，並具備自動日誌記錄與 Webhook 警報功能。

---

## 🛠️ 環境需求 (Prerequisites)
* **Python** 版本：`3.8` 或以上（完全支援至 Python 3.14 最新版本）
* **作業系統**：Windows 10/11、macOS、Linux (Ubuntu 20.04+)

---

## 🚀 一鍵部署與安裝指南 (Deployment Guide)

1. **安裝 Python**（若電腦未安裝）：
   請至 [Python 官網](https://www.python.org/downloads/) 下載並安裝 Python 3.8 或以上版本。
   *(⚠️ 注意：Windows 用戶在安裝時，務必勾選「Add Python to PATH」)*

2. **複製或下載專案至本機資料夾**：
   確認資料夾內包含 `main.py`、`config.json` 與 `requirements.txt`。

3. **切換終端機目錄並安裝依賴套件**：
   開啟終端機 (Terminal / PowerShell)，**務必先將路徑切換至專案所在的資料夾**，再執行安裝指令：
   ```bash
   # 請將下方路徑替換為你實際存放專案的資料夾位置
   cd /path/to/your/project_folder

   # 安裝 Python 依賴套件
   pip install -r requirements.txt

4. **安裝 自動化瀏覽器驅動**：
   套件安裝完成後，須執行以下指令，讓系統下載爬蟲需要的 Chromium 瀏覽器
   ```bash
   playwright install chromium
   如果上述指令無效，請嘗試輸入
    ```bash
   python3 -m playwright install chromium

5. **執行說明**：
   請根據您的作業系統與終端機環境，選擇以下其中一種指令來手動執行：
   推薦方式（若終端機同時安裝多個版本，建議優先嘗試此指令）：
   python3 main.py
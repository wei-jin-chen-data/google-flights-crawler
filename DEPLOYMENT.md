# 航班監控爬蟲 - 部署與操作手冊

本系統採用 GitHub Actions 進行雲端自動化監測，部署完成後將於背景自動執行，無需開啟電腦。

## 一、 本地環境初始化 (首次部署)
在將專案推送到 GitHub 之前，請在專案根目錄的終端機（PowerShell / Terminal）執行以下指令：

```bash
# 1. 初始化 Git
git init

# 2. 將所有檔案加入暫存區
git add .

# 3. 提交版本說明
git commit -m "Initial commit for flight monitor"

# 4. 連接至您的 GitHub 倉庫 (請將網址替換為倉庫連結)
git remote add origin https://github.com/帳號/倉庫名稱.git

# 5. 推送至 GitHub (首次執行會跳出瀏覽器視窗，請點選 Sign in with your browser)
git branch -M main
git push -u origin main

## 二、 雲端自動執行機制
* **頻率**：目前設定每日執行 4 次 (08:00, 14:00, 20:00, 02:00 台灣時間)。
* **自動化**：由 GitHub 雲端伺服器自動開機執行，即使電腦關機也能穩定運行。

## 三、 資料下載流程 (如何取得 CSV/JSON)
爬蟲完成後，數據會封裝在「產出物 (Artifacts)」中：
1. 登入 GitHub 倉庫，點擊上方的 **[Actions]** 分頁。
2. 點擊該次成功執行（綠色勾勾）的任務名稱。
3. 將網頁視窗**捲動至最底部**，找到 **[Artifacts]** 區塊。
4. 點擊 **`flight-data-windows`** 連結即可下載包含 CSV 與 JSON 的壓縮檔。

## 四、 維護與開發
* **修改程式**：直接在本地修改程式碼，並透過 Git 推送 (`git push`) 到 GitHub，雲端系統將自動更新。
* **手動測試**：若需立即跑一次爬蟲，請至 GitHub 網頁的 **[Actions]** 分頁，點選右側的 **[Run workflow]** 按鈕即可。
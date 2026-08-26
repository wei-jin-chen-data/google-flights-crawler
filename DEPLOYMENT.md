# 航班監控爬蟲 - 部署與操作手冊

本手冊提供系統建置、雲端排程運作機制與維護說明。

---

## 一、 本地環境初始化 (首次推送至 GitHub)

若為全新建立的專案，請在專案根目錄開啟終端機（PowerShell / Terminal），執行以下指令將程式碼推送到 GitHub：

```bash
# 1. 初始化 Git 倉庫
git init

# 2. 將所有檔案加入暫存區
git add .

# 3. 提交版本說明
git commit -m "Initial commit for flight monitor"

# 4. 連接至您的 GitHub 倉庫 (請替換為實際倉庫網址)
git remote add origin [https://github.com/帳號/倉庫名稱.git]

# 5. 推送至 GitHub 主分支
git branch -M main
git push -u origin main

```
## 二、 雲端自動執行機制
執行頻率：每日固定執行 4 次 (台灣時間 08:00, 14:00, 20:00, 02:00)。
伺服器環境：採用 GitHub 提供之 Windows 雲端虛擬機 (windows-latest) 自動開機執行。
無須開機：所有抓取與打包流程均在雲端完成，本機電腦關機完全不影響排程。

## 三、 資料與日誌下載流程
每次爬蟲執行完畢後，資料均會暫存於 GitHub 伺服器 90 天：
登入 GitHub 倉庫，進入 [Actions] 分頁。
點擊左側工作流程 Flight Monitor (Windows)，並選擇任一筆成功執行的任務。
將頁面捲動至最底部，找到 [Artifacts] 區塊。
點擊 flight-data-windows 連結，下載 ZIP 壓縮包（內含 data/ 數據檔與 logs/ 執行日誌）。

## 四、 開發與系統維護
更新程式碼：直接在本地修改 main.py 或 config.json 等檔案，修改後推送到 GitHub 即可套用最新邏輯：
git add .
git commit -m "更新爬蟲邏輯"
git push

手動即時測試：若不想等待定時排程，可至 GitHub [Actions] 分頁，點選左側 Flight Monitor (Windows)，點擊右側的 [Run workflow] 按鈕即可立即觸發執行。
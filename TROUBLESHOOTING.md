#  故障排除與維護手冊 

本手冊針對系統在日常運作或長期監測 Google Flights 期間可能遇到的常見問題提供標準應變與修復程序。

---

##  常見故障與排除 SOP

###狀況一：IP 遭到短暫封鎖 
* **現象**：日誌連續出現抓取失敗。
* **原因**：短時間內請求頻率過高，遭 Google 觸發安全防護機制。
* **排解步驟**：
  1. **調高延遲參數**：開啟 `config.json`，將 `min_jitter_seconds` 與 `max_jitter_seconds` 的數值調大（例如拉高至 8~15 秒）。
  2. **增加批次冷卻時間**：將 `batch_pause_seconds` 從 20 秒調高至 60 秒以上。
  3. **更換 IP**：若使用雲端伺服器 (AWS/GCP等)，建議更換 IP 或改用住宅代理伺服器 (Residential Proxy)。

---

###狀況二：網頁結構微調導致抓取不到資料 (`Selector Error`)
* **現象**：終端機日誌顯示「未能在去程頁面找到機票卡片」或欄位內容變為「時間未明」。
* **原因**：Google Flights 官方前端網頁 DOM 結構（CSS Class 名稱）進行了改版。
* **排解步驟**：
  1. **手動確認元素**：以手動瀏覽器開啟 Google Flights，按 `F12` 檢查機票主卡片與時間標籤的最新 HTML Class。
  2. **更新選擇器**：對應修改 `main.py` 裡的 `query_selector` 或 `query_selector_all` 參數（例如將 `div.yR1fYc` 替換為最新的 Class）。

---

###狀況三：網路逾時 (`TimeoutError` / `ERR_CONNECTION_TIMED_OUT`)
* **現象**：執行時因網路不穩導致 `page.goto` 逾時。
* **排解步驟**：
  1. 檢查主機網路連線是否正常。
  2. 系統內建的重試機制 (`max_retries`) 會自動重試，若頻繁發生可至 `config.json` 將 `retry_delay_seconds` 調高以等待網路恢復。

---

##  穩定度監控與日誌檢查
* **日誌檔案位置**：所有的執行紀錄皆會自動儲存於 `./logs/` 目錄下。
* **建議維護頻率**：建議每週檢查一次 `./logs/` 內的錯誤訊息比例，確保 7 天連續抓取成功率維持在 95% 標標準以上。
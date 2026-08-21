Google Flights 自動化監測系統 - 技術架構檔案 
本檔案說明本機票價格自動監測系統的系統架構、技術選型、模組設計與資料流向，以利後續的維護、擴充與伺服器部署。

1. 系統架構總覽 
本系統採用模組化與分層設計，結合現代化網頁自動化技術與定時排程機制，定時抓取 Google Flights 的航班價格、時間、轉機次數與行李額度，並進行結構化輸出與警報通知。

Plaintext
[ 定時排程器 (GitHub actions) ] 
       │ (定時觸發)
       ▼
[ 核心監測引擎 (main.py / FlightMonitorEngine) ]
       │
       ├──> Playwright 瀏覽器自動化核心 (Chromium Headless)
       │         └──> 目標網站: Google Flights (動態渲染頁面)
       │
       ├──> 資料解析與清洗模組 (BeautifulSoup / Regex / DOM Locator)
       │
       └──> 輸出與通知模組
                 ├──> 檔案輸出: CSV / JSON (`./data/`)
                 ├──> 日誌記錄: `.log` 檔案 (`./logs/`)
                 └──> 即時警報: Webhook (Discord / Slack)
2. 核心技術棧
程式語言：Python 3.8+

瀏覽器自動化 ：Playwright for Python（高效、支援 Headless 模式、完美應對現代 SPA 動態網頁）

資料解析 ：BeautifulSoup4、Regular Expressions (re)

資料處理與匯出 :Pandas (負責 CSV 與 JSON 結構化輸出)

HTTP 請求 ：Requests (負責發送遠端 Webhook 警報通知)

排程管理 ：自定義定時觸發機制 (GitHub actions)

3. 核心模組與職責 
A. 設定管理 (config.json)
集中管理所有動態參數，包含監測航線 (routes)、提前天數、停留天數、爬蟲重試次數、隨機延遲（Jitter）及批次冷卻時間，實現「組態與程式碼分離」。

B. 爬蟲與解析引擎 (main.py -> FlightMonitorEngine)
瀏覽器生命週期管理：透過 Playwright 啟動 Chromium 實例，支援從 config.json 讀取 headless 開關（支援本機有畫面除錯，以及伺服器無頭背景執行）。

多層次防呆與重試機制：針對網頁逾時或動態載入失敗，內建自動重試（Max Retries）與錯誤例外捕捉（Exception Capture），並會自動儲存發生錯誤時的網頁截圖與 HTML 原始碼於 ./debug/ 供開發者排查。

資料爬取：

價格與時間：解析含稅總價、去回程起降時間與總飛行時數。

航司與航班編號：針對聯營航班進行優化，能精準抓取排序第一的主要航空公司與第一組航班編號。

行李額度：透過展開航班詳細資料與區段掃描，解析免費隨身與託運行李額度。

C. 執行結算與日誌系統 
即時日誌與原因追蹤：所有的成功、失敗及具體錯誤原因（如逾時、找不到卡片）皆會即時寫入 ./logs/ 目錄下的日誌檔。

執行統計結算：每次排程任務跑完後，會在終端機與日誌中自動計算並顯示：總掃描筆數、成功筆數、失敗筆數以及整體成功率（%）。

4. 資料流向與生命週期 
初始化：系統讀取 config.json，初始化日誌記錄器與輸出資料夾。

組合 URL：依據航線設定與動態天數，自動生成 Google Flights 查詢網址。

網頁渲染與點擊：Playwright 載入頁面，依序抓取去程與回程的第一個最優航班卡片，並模擬點擊展開詳細資訊。

清洗與結構化：透過正則表達式與 DOM 解析器，將雜亂的網頁文字轉換為乾淨的結構化字典。

落盤與通知：

成功時：寫入記憶體清單，任務結束後統一匯出為 CSV 與 JSON 格式。

失敗時：記錄失敗原因至 Log，若有開啟 Webhook 則主動發送警報通知。

5. 部署與擴充性考量 
雲端伺服器相容：支援 Linux 系統（如 Ubuntu Server / Docker 容器）。只需在 config.json 設定 "headless": true，即可在無圖形介面（Headless）環境下穩定運行。

反爬蟲對策：內建隨機延遲（Jitter）與批次暫停機制（Batch Pause），有效降低頻繁請求遭到 Google 阻擋的風險。
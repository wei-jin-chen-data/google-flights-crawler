from datetime import datetime, timedelta
import json
import logging
import os
import random
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 載入 JSON 設定
CONFIG_PATH = "config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# 初始化目錄
os.makedirs(CONFIG["output"]["data_dir"], exist_ok=True)
os.makedirs(CONFIG["output"]["logs_dir"], exist_ok=True)
os.makedirs("./debug", exist_ok=True)

# 設定 Logging (精簡輸出)
log_filename = os.path.join(
    CONFIG["output"]["logs_dir"],
    f"flight_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

class FlightMonitorEngine:
    def __init__(self, config):
        self.config = config
        self.routes = config["routes"]
        self.settings = config["scraping_settings"]
        self.output = config["output"]
        self.notification = config["notification"]
        self.all_results = []
        
        self.success_count = 0
        self.fail_count = 0

    def send_webhook(self, message):
        """發送 Webhook 通知"""
        url = self.notification.get("webhook_url")
        if not url:
            return
        try:
            payload = {"content": message, "text": message}
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"⚠️ Webhook 發送失敗: {str(e)}")

    def clean_airline_name(self, raw_airline_text):
        """💡 嚴格只抓取第一個出現的主要航空公司名稱"""
        if not raw_airline_text:
            return "未知航司"

        known_airlines = [
            "中華航空", "長榮航空", "星宇航空", "樂桃航空", "台灣虎航",
            "酷航", "捷星日本", "捷星日本航空", "捷星航空", "捷星",
            "日本航空", "全日空", "泰越捷航空", "泰越捷", "大韓航空",
            "韓亞航空", "香港航空", "國泰航空", "巴迪航空", "大灣區航空",
            "亞洲航空", "AirAsia", "泰國獅子航空", "泰國獅航", "泰獅航",
            "新加坡航空", "越南航空", "達美航空", "菲律賓航空", "德威航空", "泰瑞航空",
            "美國航空", "阿拉斯加航空"
        ]

        found_matches = []
        for airline in known_airlines:
            idx = raw_airline_text.find(airline)
            if idx != -1:
                found_matches.append((idx, airline))

        if found_matches:
            found_matches.sort(key=lambda x: x[0])
            return found_matches[0][1]

        cleaned = re.sub(r"分段購票.*?(?=機票|$)", "", raw_airline_text)
        cleaned = cleaned.replace("你將分段購買這趟行程的機票", "")
        cleaned = re.split(r"(\d+\s*小時|轉機|\b[A-Z]{3}\b|,|・)", cleaned)[0]
        final_text = re.sub(r"\s+", " ", cleaned).strip()
        return final_text if final_text else "未知航司"

    def normalize_text(self, text):
        return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()

    def extract_stops(self, raw_text):
        if "直達" in raw_text:
            return "直達"
        match = re.search(r"轉機\s*\d+\s*次", raw_text)
        if match:
            return match.group(0).replace(" ", "")
        return "轉機資訊未明"

    def extract_times(self, raw_text, card_element=None):
        time_values = []
        if card_element:
            try:
                candidates = card_element.query_selector_all(
                    'span[role="text"], [aria-label*="出發時間"], [aria-label*="抵達時間"]'
                )
                for el in candidates:
                    txt = self.normalize_text(el.text_content())
                    aria = self.normalize_text(el.get_attribute("aria-label"))
                    for source in (txt, aria):
                        if source and (
                            any(k in source for k in ["上午", "下午", "晚上", "凌晨"])
                            or re.search(r"\d{1,2}:\d{2}", source)
                        ):
                            if len(source) < 50 and source not in time_values:
                                time_values.append(source)
            except Exception:
                pass

        if not time_values:
            matches = re.findall(r"(?:上午|下午|晚上|凌晨)?\s*\d{1,2}:\d{2}", raw_text)
            time_values.extend(self.normalize_text(x) for x in matches if x.strip())

        cleaned = []
        for value in time_values:
            m = re.search(r"(上午|下午|晚上|凌晨)?\s*(\d{1,2}:\d{2})", value)
            if not m:
                continue
            period = m.group(1)
            hm = m.group(2)
            if period:
                label = {"上午": "AM", "下午": "PM", "晚上": "PM", "凌晨": "AM"}[period]
            else:
                hour = int(hm.split(":")[0])
                label = "AM" if hour < 12 else "PM"
            result = f"{label} {hm}"
            if result not in cleaned:
                cleaned.append(result)

        if len(cleaned) >= 2:
            return f"{cleaned[0]} ~ {cleaned[1]}"
        if len(cleaned) == 1:
            return cleaned[0]

        all_raw = re.findall(r"\d{1,2}:\d{2}", raw_text)
        if len(all_raw) >= 2:
            values = []
            for hm in all_raw[:2]:
                hour = int(hm.split(":")[0])
                values.append(f"{'AM' if hour < 12 else 'PM'} {hm}")
            return f"{values[0]} ~ {values[1]}"

        return "時間未明"

    def parse_price(self, raw_text):
        match = re.search(r"(US\$\s?[\d,]+|NT\$\s?[\d,]+|\$\s?[\d,]+)", raw_text)
        return match.group(1).strip() if match else "NT$0"

    def extract_basic_card_details(self, card_element):
        raw_text = self.normalize_text(card_element.inner_text())
        duration_el = card_element.query_selector("div.gvkrdb")
        duration = self.normalize_text(duration_el.text_content()) if duration_el else "未知時間"

        airline_text = ""
        airline_candidates = card_element.query_selector_all("div.sSHqwe")
        for el in airline_candidates:
            txt = self.normalize_text(el.text_content())
            if txt:
                airline_text += " " + txt
        airline = self.clean_airline_name(airline_text or raw_text)
        stops = self.extract_stops(raw_text)

        return {
            "price": self.parse_price(raw_text),
            "airline": airline,
            "time_str": self.extract_times(raw_text, card_element),
            "duration": duration,
            "stops": stops,
            "raw_text": raw_text,
        }

    def _visible(self, element):
        try:
            return element.is_visible()
        except Exception:
            return False

    def find_card_container(self, card_element):
        try:
            locator = card_element.locator("xpath=ancestor::div[contains(@class,'gQ6yfe') and contains(@class,'m7VU8c')][1]")
            if locator.count() > 0:
                return locator.first
        except Exception:
            pass
        return card_element

    def extract_flight_number_from_page_data(self, page, container):
        """💡 嚴格限制在該卡片容器內，抓取第一個出現的航班編號"""
        try:
            # 優先從當前點擊容器內尋找航班編號元素
            elements = container.query_selector_all('span.Xsgmwe.QS0io')
            for el in elements:
                if not self._visible(el):
                    continue
                text = self.normalize_text(el.evaluate("el => el.textContent"))
                if re.fullmatch(r'[A-Z0-9]{2}\s*\d{1,4}', text):
                    return re.sub(r'\s+', ' ', text)

            # 若容器內找不到，備用全頁尋找（只比對第一個）
            elements_all = page.query_selector_all('span.Xsgmwe.QS0io')
            for el in elements_all:
                if not self._visible(el):
                    continue
                text = self.normalize_text(el.evaluate("el => el.textContent"))
                if re.fullmatch(r'[A-Z0-9]{2}\s*\d{1,4}', text):
                    return re.sub(r'\s+', ' ', text)
        except Exception:
            pass
        return "航班編號未明"

    def _extract_baggage_candidates(self, root_element):
        candidates = []
        keywords = (
            "免費攜帶", "免費隨身行李", "免費託運", "免費托運",
            "手提行李", "隨身行李", "登機行李", "託運行李", "托運行李",
            "件行李", "沒有託運行李"
        )
        try:
            html_content = root_element.evaluate("el => el.outerHTML") if hasattr(root_element, 'evaluate') else str(root_element)
            soup = BeautifulSoup(html_content, 'html.parser')
            items = soup.select("li.oi0btb, li, [aria-label*='行李'], [aria-label*='免費']")
            for item in items:
                for svg in item.find_all('svg'):
                    svg.decompose()
                text = self.normalize_text(item.get("aria-label", ""))
                if not text:
                    text = self.normalize_text(item.get_text())
                if text and len(text) <= 150:
                    if "行李費用" in text:
                        continue
                    if any(k in text for k in keywords) and text not in candidates:
                        candidates.append(text)
        except Exception:
            pass

        unique = []
        for value in candidates:
            if not any(value != other and value in other for other in candidates):
                if value not in unique:
                    unique.append(value)
        return unique[:4]

    def extract_expanded_details(self, page, card_element):
        baggage = "行李額度未明"
        detail_clicked = False
        container = self.find_card_container(card_element)

        try:
            detail_buttons = container.query_selector_all('button[aria-label^="航班詳細資料"]')
            detail_buttons = [b for b in detail_buttons if self._visible(b)]

            if not detail_buttons:
                all_buttons = page.query_selector_all('button[aria-label^="航班詳細資料"]')
                card_text = self.normalize_text(card_element.inner_text())
                card_times = re.findall(r'(?:上午|下午|晚上|凌晨)?\s*\d{1,2}:\d{2}', card_text)
                matched = []
                for b in all_buttons:
                    if not self._visible(b):
                        continue
                    aria = self.normalize_text(b.get_attribute('aria-label'))
                    if any(t in aria for t in card_times):
                        matched.append(b)
                detail_buttons = matched

            if detail_buttons:
                button = detail_buttons[0]
                if button.get_attribute('aria-expanded') != 'true':
                    button.scroll_into_view_if_needed()
                    button.click(force=True)
                    detail_clicked = True

                try:
                    page.wait_for_function(
                        """
                        () => {
                            const btns = [...document.querySelectorAll('button[aria-label^="航班詳細資料"]')];
                            const expanded = btns.some(b => b.getAttribute('aria-expanded') === 'true');
                            const fn = [...document.querySelectorAll('span.Xsgmwe.QS0io')].some(e => e.offsetParent !== null);
                            return expanded || fn;
                        }
                        """,
                        timeout=7000,
                    )
                except Exception:
                    time.sleep(1)

            # 💡 此處將容器傳入，確保抓取當前卡片第一段航程的航班編號
            flight_number = self.extract_flight_number_from_page_data(page, container)

        except Exception:
            flight_number = "航班編號未明"

        return {
            "flight_number": flight_number,
            "baggage": baggage,
            "detail_clicked": detail_clicked,
        }

    def extract_lowest_tier_baggage_by_section(self, page):
        """💡 兼顧全頁預設 DOM 抓取與獨立去回程區塊比對的相容函數"""
        outbound_baggage = ""
        inbound_baggage = ""
        try:
            try:
                page.wait_for_selector("ul.BABTTc, div.gi0tie, div.OabD8b, div.gQ6yfe", timeout=6000)
            except Exception:
                time.sleep(2)

            containers = page.query_selector_all("div.gi0tie, div.OabD8b, div.Rk10dc, div.vJRrcb")
            for container in containers:
                if not self._visible(container):
                    continue
                c_text = container.inner_text()
                
                if "去程航班" in c_text and not outbound_baggage:
                    bag_cands = self._extract_baggage_candidates(container)
                    if bag_cands:
                        outbound_baggage = "、".join(bag_cands)
                        
                if "回程航班" in c_text and not inbound_baggage:
                    bag_cands = self._extract_baggage_candidates(container)
                    if bag_cands:
                        inbound_baggage = "、".join(bag_cands)

            if not outbound_baggage and not inbound_baggage:
                lists = page.query_selector_all("ul.BABTTc")
                visible_lists = [l for l in lists if self._visible(l)]
                if visible_lists:
                    cands = self._extract_baggage_candidates(visible_lists[0])
                    if cands:
                        shared_bag = "、".join(cands)
                        outbound_baggage = shared_bag
                        inbound_baggage = shared_bag
                else:
                    columns = page.query_selector_all("div.OabD8b, div.gQ6yfe, div.Rk10dc, div.vJRrcb")
                    visible_cols = [c for c in columns if self._visible(c)]
                    if visible_cols:
                        cands = self._extract_baggage_candidates(visible_cols[0])
                        if cands:
                            shared_bag = "、".join(cands)
                            outbound_baggage = shared_bag
                            inbound_baggage = shared_bag

            if outbound_baggage and not inbound_baggage:
                inbound_baggage = outbound_baggage
            elif inbound_baggage and not outbound_baggage:
                outbound_baggage = inbound_baggage

        except Exception:
            pass

        return outbound_baggage or "行李額度未明", inbound_baggage or "行李額度未明"

    def log_debug_snapshot(self, page, tag):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        try:
            html_path = os.path.join("debug", f"{tag}_{timestamp}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
        except Exception:
            pass
        try:
            png_path = os.path.join("debug", f"{tag}_{timestamp}.png")
            page.screenshot(path=png_path, full_page=False)
        except Exception:
            pass

    def get_flight_cards(self, page):
        cards = page.query_selector_all("div.yR1fYc")
        return cards if cards else page.query_selector_all('li[role="listitem"]')

    def click_selected_card(self, card_element):
        container = self.find_card_container(card_element)
        try:
            link = container.locator('div[role="link"]').first
            if link.count() > 0:
                link.click(force=True)
                return
        except Exception:
            pass
        try:
            card_element.scroll_into_view_if_needed()
            card_element.click(force=True)
            return
        except Exception:
            raise

    def fetch_round_trip_flight(self, context, url):
        retries = self.settings["max_retries"]
        delay = self.settings["retry_delay_seconds"]
        last_error = ""

        for attempt in range(1, retries + 1):
            page = None
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_selector("div.yR1fYc", timeout=15000)
                except PlaywrightTimeoutError:
                    raise Exception("Google Flights 機票卡片載入逾時")

                page.mouse.wheel(0, 300)
                time.sleep(1.5)

                body_text = self.normalize_text(page.locator("body").inner_text())
                if "系統發生錯誤" in body_text or "重新載入" in body_text:
                    raise Exception("Google Flights 顯示系統錯誤頁")

                outbound_cards = self.get_flight_cards(page)
                if not outbound_cards:
                    raise Exception("未能在去程頁面找到機票卡片")

                target_outbound_card = outbound_cards[0]
                outbound_info = self.extract_basic_card_details(target_outbound_card)
                outbound_extra = self.extract_expanded_details(page, target_outbound_card)
                outbound_info.update(outbound_extra)

                self.click_selected_card(target_outbound_card)
                time.sleep(2.5)

                try:
                    page.wait_for_selector("div.yR1fYc", state="visible", timeout=15000)
                except PlaywrightTimeoutError:
                    pass

                time.sleep(1.5)

                inbound_cards = self.get_flight_cards(page)
                if not inbound_cards:
                    inbound_cards = page.query_selector_all('li[role="listitem"]')

                if not inbound_cards:
                    raise Exception("進入回程頁後找不到回程機票卡片")

                target_inbound_card = inbound_cards[0]
                inbound_info = self.extract_basic_card_details(target_inbound_card)
                inbound_extra = self.extract_expanded_details(page, target_inbound_card)
                inbound_info.update(inbound_extra)

                self.click_selected_card(target_inbound_card)
                time.sleep(3.5)

                page_out_bag, page_in_bag = self.extract_lowest_tier_baggage_by_section(page)

                outbound_baggage = page_out_bag if page_out_bag else "行李額度未明"
                inbound_baggage = page_in_bag if page_in_bag else "行李額度未明"

                outbound_airline = outbound_info["airline"]
                inbound_airline = inbound_info["airline"]

                # 💡 特殊邏輯：泰國獅航行李覆蓋規則
                lion_keywords = ["泰國獅子航空", "泰國獅航", "泰獅航"]
                is_lion_air = any(k in outbound_airline for k in lion_keywords) or any(k in inbound_airline for k in lion_keywords)

                if is_lion_air:
                    outbound_baggage = "免費攜帶 1 件手提行李"
                    inbound_baggage = "免費攜帶 1 件手提行李"

                return {
                    "total_price": outbound_info["price"],
                    "outbound_airline": outbound_airline,
                    "inbound_airline": inbound_airline,
                    "outbound_flight_number": outbound_info["flight_number"],
                    "inbound_flight_number": inbound_info["flight_number"],
                    "outbound_baggage": outbound_baggage,
                    "inbound_baggage": inbound_baggage,
                    "outbound_time": outbound_info["time_str"],
                    "inbound_time": inbound_info["time_str"],
                    "outbound_duration": outbound_info["duration"],
                    "inbound_duration": inbound_info["duration"],
                    "outbound_stops": outbound_info["stops"],
                    "inbound_stops": inbound_info["stops"],
                }

            except Exception as e:
                last_error = str(e)
                if page:
                    self.log_debug_snapshot(page, f"attempt_{attempt}")
                    try:
                        page.close()
                    except Exception:
                        pass

                if attempt < retries:
                    time.sleep(delay)
                else:
                    if self.notification.get("enable_alert_on_failure"):
                        self.send_webhook(
                            f"🚨 [機票監測失敗] 抓取 URL 失敗超越重試上限: {url} | 原因: {last_error}"
                        )
                    return {"error": last_error}
            else:
                try:
                    page.close()
                except Exception:
                    pass
        return {"error": "未知錯誤"}

    def save_data(self):
        if not self.all_results:
            logging.warning("⚠️ 沒有抓取到任何資料，跳過匯出。")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if "json" in self.output["export_format"]:
            json_path = os.path.join(self.output["data_dir"], f"flights_{timestamp}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.all_results, f, ensure_ascii=False, indent=2)
            logging.info(f"📁 JSON 資料已成功匯出至: {json_path}")

        if "csv" in self.output["export_format"]:
            csv_path = os.path.join(self.output["data_dir"], f"flights_{timestamp}.csv")
            df = pd.DataFrame(self.all_results)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            logging.info(f"📊 CSV 資料已成功匯出至: {csv_path}")

    def run(self):
        logging.info("=================== 啟動大規模機票自動監測引擎 ===================")
        total_scanned = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.settings.get("headless", True),
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                locale="zh-TW",
            )

            for route in self.routes:
                origin = route["origin"]
                destination = route["destination"]
                days_ahead = route["days_ahead"]
                trip_length = route["trip_length_days"]

                logging.info(f"✈️ 開始航線任務: {origin} -> {destination} (未來 {days_ahead} 天)")
                start_date = datetime.now() + timedelta(days=1)

                for day_idx in range(days_ahead):
                    dep_date = (start_date + timedelta(days=day_idx)).strftime("%Y-%m-%d")
                    ret_date = (start_date + timedelta(days=day_idx + trip_length)).strftime("%Y-%m-%d")

                    url = (
                        "https://www.google.com/travel/flights?"
                        f"q=Flights%20to%20{destination}%20from%20{origin}%20on%20{dep_date}%20"
                        f"through%20{ret_date}&hl=zh-TW&curr=TWD"
                    )

                    res = self.fetch_round_trip_flight(context, url)

                    if res and "error" not in res:
                        self.success_count += 1
                        
                        formatted_price = f"台幣 {res['total_price']}(含稅)"

                        data_row = {
                            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")[:-3],
                            "origin": origin,
                            "destination": destination,
                            "departure_date": dep_date,
                            "return_date": ret_date,
                            "lowest_price": formatted_price,
                            "outbound_airline": res["outbound_airline"],
                            "inbound_airline": res["inbound_airline"],
                            "outbound_flight_number": res["outbound_flight_number"],
                            "inbound_flight_number": res["inbound_flight_number"],
                            "outbound_stops": res["outbound_stops"],
                            "inbound_stops": res["inbound_stops"],
                            "outbound_baggage": res["outbound_baggage"],
                            "inbound_baggage": res["inbound_baggage"],
                            "outbound_time": res["outbound_time"],
                            "inbound_time": res["inbound_time"],
                            "outbound_duration": res["outbound_duration"],
                            "inbound_duration": res["inbound_duration"],
                            "url": url,
                        }
                        self.all_results.append(data_row)

                        logging.info(
                            f"[{day_idx + 1}/{days_ahead}] {origin}->{destination} | "
                            f"{dep_date} ~ {ret_date} 最低價: {formatted_price} | "
                            f"(去) {res['outbound_airline']} {res['outbound_flight_number']} {res['outbound_stops']} {res['time_str'] if 'time_str' in res else res['outbound_time']} | "
                            f"(回) {res['inbound_airline']} {res['inbound_flight_number']} {res['inbound_stops']} {res['inbound_time']} | "
                            f"[去程行李: {res['outbound_baggage']}] [回程行李: {res['inbound_baggage']}]"
                        )
                    else:
                        self.fail_count += 1
                        error_msg = res.get("error", "未知錯誤") if res else "未知錯誤"
                        logging.error(
                            f"[{day_idx + 1}/{days_ahead}] {origin}->{destination} | "
                            f"{dep_date} ~ {ret_date} ❌ 抓取失敗 | 原因: {error_msg}"
                        )

                    total_scanned += 1

                    if total_scanned % self.settings["batch_size"] == 0:
                        pause_sec = self.settings["batch_pause_seconds"]
                        logging.info(f"☕ 已達到批次大小 ({self.settings['batch_size']})，冷卻暫停 {pause_sec} 秒...")
                        time.sleep(pause_sec)
                    else:
                        jitter = random.uniform(
                            self.settings["min_jitter_seconds"],
                            self.settings["max_jitter_seconds"],
                        )
                        time.sleep(jitter)

            browser.close()

        self.save_data()
        
        total_attempts = self.success_count + self.fail_count
        success_rate = (self.success_count / total_attempts * 100) if total_attempts > 0 else 0.0
        
        logging.info("=================== 執行統計結果報告 ===================")
        logging.info(f"📊 總掃描筆數: {total_attempts} 筆")
        logging.info(f"✅ 成功筆數: {self.success_count} 筆")
        logging.info(f"❌ 失敗筆數: {self.fail_count} 筆")
        logging.info(f"📈 成功率: {success_rate:.2f}%")
        logging.info("=======================================================")
        logging.info("=================== 任務全部完成，引擎順利關閉 ===================")

if __name__ == "__main__":
    engine = FlightMonitorEngine(CONFIG)
    engine.run()
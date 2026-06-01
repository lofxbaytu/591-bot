import os
import re
import sys
import json
import time
import requests
from datetime import datetime

CONFIG_PATH = 'config.json'
SEEN_LISTINGS_PATH = 'seen_listings.json'
CRITERIA_PATH = 'search_criteria.json'

def escape_html(text):
    """Escapes HTML special characters for Telegram HTML parse mode."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def load_config():
    """Loads bot secrets configuration. If it doesn't exist, creates a default one."""
    config = {
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID"),
        "check_interval_seconds": int(os.environ.get("CHECK_INTERVAL_SECONDS", 86400)),
        "run_once": os.environ.get("RUN_ONCE", "False").lower() in ("true", "1", "yes")
    }

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                filtered_file_config = {
                    k: v for k, v in file_config.items() 
                    if v not in ("YOUR_TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_CHAT_ID")
                }
                config.update(filtered_file_config)
        except Exception as e:
            print(f"[ERROR] Failed to load config.json: {e}")
    else:
        if config["telegram_bot_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
            try:
                default_config = {
                    "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
                    "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID",
                    "check_interval_seconds": 86400,
                    "run_once": False
                }
                with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                print(f"[!] Created default config file template: {CONFIG_PATH}")
            except Exception as e:
                print(f"[!] Warning: Could not create config template: {e}")

    return config

def load_criteria():
    """Loads search criteria. Falls back to default if missing."""
    if os.path.exists(CRITERIA_PATH):
        try:
            with open(CRITERIA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Warning: Failed to parse search criteria, using default: {e}")

    # Default criteria: Taipei City (all) + New Taipei City (板橋, 汐止, 永和, 三重)
    default_criteria = {
        "rentprice_min": 0,
        "rentprice_max": 30000,
        "targets": [
            {
                "region": 1,
                "kind": 0
            },
            {
                "region": 3,
                "section": "26,27,37,43",
                "kind": 0
            }
        ],
        "other_params": {}
    }
    try:
        with open(CRITERIA_PATH, 'w', encoding='utf-8') as f:
            json.dump(default_criteria, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to save default criteria: {e}")
    return default_criteria

def load_seen_listings():
    """Loads previously seen house IDs and last Telegram update ID."""
    state = {"seen_ids": set(), "last_update_id": 0}
    if os.path.exists(SEEN_LISTINGS_PATH):
        try:
            with open(SEEN_LISTINGS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    state["seen_ids"] = set(str(x) for x in data)
                elif isinstance(data, dict):
                    state["seen_ids"] = set(str(x) for x in data.get("seen_ids", []))
                    state["last_update_id"] = data.get("last_update_id", 0)
        except Exception as e:
            print(f"[!] Warning: Failed to parse seen listings database, starting fresh: {e}")
            return state
    return state

def save_seen_listings(state):
    """Saves the seen listing IDs and last Telegram update ID."""
    try:
        data = {
            "seen_ids": list(state["seen_ids"]),
            "last_update_id": state["last_update_id"]
        }
        with open(SEEN_LISTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to save seen listings: {e}")

def send_telegram_notification(token, chat_id, house_info):
    """Sends notification to Telegram via Bot API, preferring photo format if available."""
    post_id = house_info.get('post_id') or house_info.get('id')
    title = escape_html(house_info.get('title') or house_info.get('name') or "無標題")
    price = house_info.get('price', '未提供')
    price_unit = house_info.get('price_unit', '元/月')
    area = house_info.get('area', '未提供')
    room_str = escape_html(house_info.get('room_str') or house_info.get('layout') or house_info.get('kind_name', '未提供格局'))
    floor_str = escape_html(house_info.get('floor_str') or house_info.get('floor') or '未提供樓層')
    
    location = escape_html(
        house_info.get('address') or 
        house_info.get('location') or 
        f"{house_info.get('section_name', '')}{house_info.get('street_name', '')}" or 
        "無地址資訊"
    )
    
    url = f"https://rent.591.com.tw/rent-detail-{post_id}.html"
    
    caption = (
        f"🏠 <b>發現新房源！</b>\n\n"
        f"📌 <b>標題：</b> {title}\n"
        f"💰 <b>租金：</b> {price} {price_unit}\n"
        f"📏 <b>坪數：</b> {area} 坪\n"
        f"🛏️ <b>格局：</b> {room_str}\n"
        f"🏢 <b>樓層：</b> {floor_str}\n"
        f"📍 <b>地點：</b> {location}\n\n"
        f"🔗 <a href='{url}'>點此查看 591 房屋詳情</a>"
    )
    
    photo_url = house_info.get('cover')
    if not photo_url:
        photo_list = house_info.get('photo_list')
        if photo_list and isinstance(photo_list, list) and len(photo_list) > 0:
            photo_url = photo_list[0]
            
    base_url = f"https://api.telegram.org/bot{token}"
    
    if photo_url:
        send_photo_url = f"{base_url}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
        try:
            res = requests.post(send_photo_url, json=payload, timeout=10)
            if res.status_code == 200:
                print(f"[OK] Sent photo notification for house ID: {post_id}")
                return True
        except Exception as e:
            print(f"[!] Error sending photo: {e}, falling back to sendMessage.")

    send_msg_url = f"{base_url}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(send_msg_url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")
        return False

def get_591_listings(session, config, target):
    """Fetches the latest rental listings from 591 rsList API for a specific target."""
    region = target.get("region", 1)
    kind = target.get("kind", 0)
    section = target.get("section", "")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }

    # Step 1: Visit main site to obtain base session cookies and CSRF token
    try:
        main_url = 'https://www.591.com.tw/'
        session.cookies.set('urlJumpIp', str(region), domain='.591.com.tw')
        response = session.get(main_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"[ERROR] Failed to fetch 591 homepage: HTTP {response.status_code}")
            return []
            
        csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
        if not csrf_match:
            print("[ERROR] CSRF token not found on the page.")
            return []
        
        csrf_token = csrf_match.group(1)
        
        new_session_val = None
        for cookie in session.cookies:
            if cookie.name == '591_new_session':
                new_session_val = cookie.value
                break
        if new_session_val:
            session.cookies.set('591_new_session', new_session_val, domain='.591.com.tw')
        
    except Exception as e:
        print(f"[ERROR] Exception occurred during session initiation: {e}")
        return []

    # Step 2: Formulate API headers and search parameters
    api_headers = headers.copy()
    api_headers.update({
        'X-CSRF-TOKEN': csrf_token,
        'X-Requested-With': 'XMLHttpRequest',
        'Device': 'pc',
        'Referer': f'https://rent.591.com.tw/?kind={kind}&region={region}'
    })

    api_params = {
        'is_format_data': '1',
        'is_new_list': '1',
        'type': '1',
        'region': str(region),
        'kind': str(kind),
        'order': 'posttime',      
        'orderType': 'desc',      
    }

    if section:
        api_params['section'] = str(section)

    min_price = config.get("rentprice_min", 0)
    max_price = config.get("rentprice_max", 0)
    if max_price > 0:
        api_params['rentprice'] = f"{min_price},{max_price}"

    if config.get("other_params"):
        api_params.update(config.get("other_params"))

    # Step 3: Fetch listings
    api_url = 'https://rent.591.com.tw/home/search/rsList'
    try:
        api_params['_'] = int(time.time() * 1000)
        res = session.get(api_url, headers=api_headers, params=api_params, timeout=15)
        
        if res.status_code == 419:
            print("[ERROR] HTTP 419: Session or CSRF token expired.")
            return []
        elif res.status_code != 200:
            print(f"[ERROR] HTTP {res.status_code} requesting 591 API.")
            return []

        response_data = res.json()
        if response_data.get('status') == 1 and 'data' in response_data:
            inner_data = response_data['data']
            if isinstance(inner_data, dict) and 'data' in inner_data:
                return inner_data['data']
            elif isinstance(inner_data, list):
                return inner_data
                
        return []
    except Exception as e:
        print(f"[ERROR] Exception during API request: {e}")
        return []

def process_telegram_commands(token, chat_id, criteria, state):
    """Fetches new Telegram messages and updates search criteria accordingly."""
    last_update_id = state.get("last_update_id", 0)
    base_url = f"https://api.telegram.org/bot{token}"
    get_updates_url = f"{base_url}/getUpdates"
    
    params = {"timeout": 5}
    if last_update_id > 0:
        params["offset"] = last_update_id + 1
        
    try:
        res = requests.get(get_updates_url, params=params, timeout=10)
        if res.status_code != 200:
            return False
            
        updates = res.json().get("result", [])
        if not updates:
            return False
            
        criteria_changed = False
        latest_update_id = last_update_id
        
        district_map = {
            "板橋": "26",
            "汐止": "27",
            "永和": "37",
            "三重": "43"
        }
        
        for update in updates:
            update_id = update.get("update_id")
            if update_id:
                latest_update_id = max(latest_update_id, update_id)
                
            message = update.get("message")
            if not message:
                continue
                
            # Security check: verify message is from configured chat ID
            sender_id = message.get("chat", {}).get("id")
            if str(sender_id) != str(chat_id):
                continue
                
            text = message.get("text", "").strip()
            if not text:
                continue
                
            reply_text = ""
            
            # 1. /price or /租金
            if text.startswith("/price ") or text.startswith("/租金 "):
                try:
                    price_str = text.split(maxsplit=1)[1]
                    new_price = int(price_str)
                    criteria["rentprice_max"] = new_price
                    criteria_changed = True
                    reply_text = f"⚙️ <b>設定成功</b>\n租金上限已更新為：{new_price:,} 元/月"
                except Exception:
                    reply_text = "❌ <b>格式錯誤</b>\n請輸入 `/租金 <金額>` (例如：`/租金 25000`)"
                    
            # 2. /region or /地區
            elif text.startswith("/region ") or text.startswith("/地區 "):
                try:
                    regions_str = text.split(maxsplit=1)[1]
                    has_taipei = "台北" in regions_str or "臺北" in regions_str
                    
                    new_targets = []
                    if has_taipei:
                        new_targets.append({"region": 1, "kind": 0})
                        
                    selected_sections = []
                    for d_name, d_id in district_map.items():
                        if d_name in regions_str:
                            selected_sections.append(d_id)
                            
                    if selected_sections:
                        new_targets.append({
                            "region": 3,
                            "section": ",".join(selected_sections),
                            "kind": 0
                        })
                        
                    if new_targets:
                        criteria["targets"] = new_targets
                        criteria_changed = True
                        
                        target_descs = []
                        for t in new_targets:
                            if t["region"] == 1:
                                target_descs.append("台北市 (全部)")
                            elif t["region"] == 3:
                                sec_names = [d_name for d_name, d_id in district_map.items() if d_id in t["section"].split(",")]
                                target_descs.append(f"新北市 ({', '.join(sec_names)})")
                                
                        reply_text = f"⚙️ <b>設定成功</b>\n搜尋地區已更新為：\n" + "\n".join(f"- {d}" for d in target_descs)
                    else:
                        reply_text = "❌ <b>找不到匹配地區</b>\n支援的地區包含：台北、板橋、三重、永和、汐止。"
                except Exception as e:
                    reply_text = f"❌ <b>設定失敗</b>\n解析錯誤: {e}"
                    
            # 3. /kind or /類型
            elif text.startswith("/kind ") or text.startswith("/類型 "):
                try:
                    kind_str = text.split(maxsplit=1)[1]
                    kind_map = {
                        "全部": 0, "整層": 1, "整層住家": 1, 
                        "獨立套房": 2, "獨套": 2, 
                        "分租套房": 3, "分套": 3, 
                        "雅房": 4
                    }
                    new_kind = None
                    for k_name, k_val in kind_map.items():
                        if k_name in kind_str:
                            new_kind = k_val
                            break
                            
                    if new_kind is not None:
                        for target in criteria.get("targets", []):
                            target["kind"] = new_kind
                        criteria_changed = True
                        
                        reverse_kind_map = {0: "全部", 1: "整層住家", 2: "獨立套房", 3: "分租套房", 4: "雅房"}
                        reply_text = f"⚙️ <b>設定成功</b>\n租屋類型已更新為：{reverse_kind_map.get(new_kind)}"
                    else:
                        reply_text = "❌ <b>類型錯誤</b>\n支援的類型有：全部、整層、獨立套房、分租套房、雅房。"
                except Exception as e:
                    reply_text = f"❌ <b>設定失敗</b>: {e}"
                    
            # 4. /status or /狀態
            elif text == "/status" or text == "/狀態":
                target_descs = []
                for t in criteria.get("targets", []):
                    kind_desc = {0: "全部", 1: "整層住家", 2: "獨立套房", 3: "分租套房", 4: "雅房"}.get(t.get("kind", 0), "未知")
                    if t["region"] == 1:
                        target_descs.append(f"• 台北市 (全部) [{kind_desc}]")
                    elif t["region"] == 3:
                        sec_names = [d_name for d_name, d_id in district_map.items() if d_id in t.get("section", "").split(",")]
                        target_descs.append(f"• 新北市 ({', '.join(sec_names)}) [{kind_desc}]")
                        
                reply_text = (
                    f"⚙️ <b>目前篩選條件設定</b>\n\n"
                    f"💰 <b>租金上限：</b> {criteria.get('rentprice_max', 0):,} 元/月\n"
                    f"📍 <b>監控地區：</b>\n" + "\n".join(target_descs) + "\n\n"
                    f"💡 <b>修改指令：</b>\n"
                    f"修改租金： `/租金 25000`\n"
                    f"修改地區： `/地區 台北,板橋,三重`\n"
                    f"修改類型： `/類型 獨立套房`"
                )
                
            if reply_text:
                send_msg_url = f"{base_url}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": reply_text,
                    "parse_mode": "HTML"
                }
                requests.post(send_msg_url, json=payload, timeout=10)
                
        state["last_update_id"] = latest_update_id
        
        if criteria_changed:
            try:
                # Save only the fields that belong to search_criteria
                filtered_criteria = {
                    "rentprice_min": criteria.get("rentprice_min", 0),
                    "rentprice_max": criteria.get("rentprice_max", 30000),
                    "targets": criteria.get("targets", []),
                    "other_params": criteria.get("other_params", {})
                }
                with open(CRITERIA_PATH, 'w', encoding='utf-8') as f:
                    json.dump(filtered_criteria, f, indent=4, ensure_ascii=False)
                print("[✓] Search criteria updated and saved.")
            except Exception as e:
                print(f"[ERROR] Failed to save updated criteria: {e}")
                
        return criteria_changed
        
    except Exception as e:
        print(f"[!] Error processing Telegram commands: {e}")
        return False

def main():
    print("="*60)
    print("      591 Rental Site Telegram Alert Bot - Active      ")
    print("="*60)
    
    config = load_config()
    criteria = load_criteria()
    
    # Merge global configurations
    config.update(criteria)
    
    if (config.get("telegram_bot_token") == "YOUR_TELEGRAM_BOT_TOKEN" or 
        config.get("telegram_chat_id") == "YOUR_TELEGRAM_CHAT_ID"):
        print("[!] Setup Required: Please fill in your Telegram Token and Chat ID.")
        return

    session = requests.Session()
    state = load_seen_listings()
    seen_listings = state["seen_ids"]
    print(f"[*] Loaded {len(seen_listings)} previously seen listings.")
    
    # Process commands from Telegram chat
    token = config["telegram_bot_token"]
    chat_id = config["telegram_chat_id"]
    print("[*] Processing incoming Telegram commands...")
    criteria_changed = process_telegram_commands(token, chat_id, config, state)
    if criteria_changed:
        # Re-apply merged settings if changed
        criteria = load_criteria()
        config.update(criteria)
        
    is_first_run = len(seen_listings) == 0
    if is_first_run:
        print("[*] First run: Bot will index current listings and start notifying on subsequent checks.")
        
    check_interval = config.get("check_interval_seconds", 86400)
    run_once = config.get("run_once", False) or ("--once" in sys.argv)
    
    targets_desc = []
    for t in config.get("targets", []):
        if t["region"] == 1:
            targets_desc.append("台北市(全部)")
        elif t["region"] == 3:
            district_map = {"26": "板橋", "27": "汐止", "37": "永和", "43": "三重"}
            sec_names = [district_map.get(sid, sid) for sid in t.get("section", "").split(",")]
            targets_desc.append(f"新北市({', '.join(sec_names)})")
            
    print(f"[*] Search Targets: {', '.join(targets_desc)} | Max Price: {config.get('rentprice_max')} TWD")
    if run_once:
        print("[*] Running in single-check mode (Run Once).")
    else:
        print(f"[*] Checking every {check_interval} seconds...")
    print("-" * 60)

    while True:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time}] Fetching listings from 591...")
        
        all_listings = []
        seen_post_ids = set()
        
        for target in config.get("targets", []):
            print(f"[{current_time}] Fetching target: Region {target.get('region')} Section {target.get('section', 'All')}...")
            target_listings = get_591_listings(session, config, target)
            for item in target_listings:
                post_id = item.get('post_id') or item.get('id')
                if post_id and post_id not in seen_post_ids:
                    seen_post_ids.add(post_id)
                    all_listings.append(item)
            time.sleep(2)
            
        if all_listings:
            print(f"[{current_time}] Successfully fetched {len(all_listings)} combined listings.")
            new_listings_count = 0
            
            for listing in reversed(all_listings):
                post_id = listing.get('post_id') or listing.get('id')
                if not post_id:
                    continue
                    
                post_id = str(post_id)
                
                if post_id not in seen_listings:
                    seen_listings.add(post_id)
                    new_listings_count += 1
                    
                    if not is_first_run:
                        send_telegram_notification(
                            token=token,
                            chat_id=chat_id,
                            house_info=listing
                        )
                        time.sleep(1.5)
            
            # Save progress
            state["seen_ids"] = seen_listings
            save_seen_listings(state)
            if is_first_run:
                print(f"[{current_time}] Initialized seen listings with {new_listings_count} houses.")
                is_first_run = False
            else:
                print(f"[{current_time}] Processed {new_listings_count} new listings.")
                
        else:
            print(f"[{current_time}] Failed to fetch listings or no listings returned.")
            
        if run_once:
            print("[*] Single check complete. Exiting.")
            break
            
        print(f"[*] Waiting {check_interval} seconds for next check...")
        print("-" * 60)
        time.sleep(check_interval)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Bot stopped by user.")

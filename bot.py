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
        "kinds": [0],
        "not_cover": 0,
        "lift": 0,
        "balcony_1": 0,
        "exclude_keywords": ["林森北路"],
        "min_area": 15,
        "floor_ratio_filter": 1,
        "mrt_within_500": 1,
        "other_params": {}
    }
    
    if os.path.exists(CRITERIA_PATH):
        try:
            with open(CRITERIA_PATH, 'r', encoding='utf-8') as f:
                criteria = json.load(f)
                if "kinds" not in criteria:
                    kinds = set()
                    for t in criteria.get("targets", []):
                        if "kind" in t:
                            kinds.add(t["kind"])
                    criteria["kinds"] = list(kinds) if kinds else [0]
                if "exclude_keywords" not in criteria:
                    criteria["exclude_keywords"] = ["林森北路"]
                if "min_area" not in criteria:
                    criteria["min_area"] = 15
                if "floor_ratio_filter" not in criteria:
                    criteria["floor_ratio_filter"] = 1
                if "mrt_within_500" not in criteria:
                    criteria["mrt_within_500"] = 1
                return criteria
        except Exception as e:
            print(f"[!] Warning: Failed to parse search criteria, using default: {e}")

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

def get_detail_info(post_id, default_area, default_address, region_id, section_name):
    """
    Fetches the detail page for a post and extracts BOTH:
    1. The correct area in 坪.
    2. The correct real address (bypassing 591 obfuscation).
    """
    url = f"https://rent.591.com.tw/rent-detail-{post_id}.html"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    area_val = default_area
    address_val = default_address
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            html = res.text
            
            # 1. Extract Area
            area_match = re.search(r'"使用坪數"\s*,\s*"([\d\.]+)\s*坪"', html)
            if not area_match:
                area_match = re.search(r'"坪數"\s*,\s*"([\d\.]+)\s*坪"', html)
            if not area_match:
                area_match = re.search(r'([\d\.]+)\s*坪', html)
            if area_match:
                area_val = area_match.group(1)
                
            # 2. Extract Address
            meta_desc = ""
            desc_match = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
            if desc_match:
                meta_desc = desc_match.group(1)
            else:
                desc_match = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
                if desc_match:
                    meta_desc = desc_match.group(1)
                    
            street_address = ""
            if meta_desc:
                located_match = re.search(r'位於([^，。！\?]+)', meta_desc)
                if located_match:
                    street_address = located_match.group(1).strip()
            
            if not street_address:
                located_match = re.search(r'位於([^，。！\?]+)', html)
                if located_match:
                    street_address = located_match.group(1).strip()
                    
            if street_address:
                region_name = "台北市" if str(region_id) == "1" else "新北市"
                address_val = f"{region_name}{section_name}{street_address}"
            else:
                addr_match = re.search(r'((?:台北市|新北市)[^"<>\s]+(?:路|街|巷|弄|號))', html)
                if addr_match:
                    address_val = addr_match.group(1)
    except Exception as e:
        print(f"[!] Error fetching detail info for {post_id}: {e}")
        
    # Format area fallback estimation if needed
    try:
        val = float(area_val)
        if val > 100:
            area_val = f"{round(val / 10 * 0.3025, 2)} (估)"
        else:
            area_val = str(area_val)
    except Exception:
        area_val = str(area_val)
        
    return area_val, address_val

def parse_floor(floor_str):
    """
    Parses floor_str (e.g. '6F/7F', '1~2F/5F', '頂樓加蓋/5F')
    returns (current_floor, total_floors) as (int, int)
    If parsing fails, returns (None, None).
    """
    if not floor_str:
        return None, None
    try:
        parts = floor_str.split('/')
        if len(parts) != 2:
            return None, None
            
        cur_part = parts[0].strip()
        tot_part = parts[1].strip()
        
        tot_match = re.search(r'(\d+)', tot_part)
        if not tot_match:
            return None, None
        total_floors = int(tot_match.group(1))
        
        current_floor = None
        if "整棟" in cur_part:
            current_floor = total_floors
        elif "頂樓加蓋" in cur_part or "頂加" in cur_part:
            current_floor = total_floors
        else:
            is_basement = "B" in cur_part or "地下" in cur_part
            cur_match = re.search(r'(\d+)', cur_part)
            if cur_match:
                val = int(cur_match.group(1))
                current_floor = -val if is_basement else val
                
        if current_floor is not None:
            return current_floor, total_floors
    except Exception:
        pass
    return None, None

def check_mrt_constraint(surrounding, max_dist=500):
    """
    Checks if the listing has a surrounding subway station within max_dist meters.
    Returns True if:
      - surrounding is a dict
      - surrounding['type'] == 'subway_station'
      - distance parsed as int is <= max_dist
    Otherwise returns False.
    """
    if not surrounding or not isinstance(surrounding, dict):
        return False
    
    if surrounding.get("type") != "subway_station":
        return False
        
    dist_str = surrounding.get("distance", "")
    match = re.search(r'(\d+)', dist_str)
    if not match:
        return False
        
    try:
        dist_val = int(match.group(1))
        return dist_val <= max_dist
    except ValueError:
        return False

def send_telegram_notification(token, chat_id, house_info):
    """Sends notification to Telegram via Bot API, preferring photo format if available."""
    post_id = house_info.get('post_id') or house_info.get('id')
    title = escape_html(house_info.get('title') or house_info.get('name') or "無標題")
    price = house_info.get('price', '未提供')
    price_unit = house_info.get('price_unit', '元/月')
    
    correct_area = house_info.get('correct_area')
    correct_address = house_info.get('correct_address')
    
    if not correct_area or not correct_address:
        raw_area = house_info.get('area', '未提供')
        raw_address = house_info.get('address') or house_info.get('location') or ""
        region_id = house_info.get('region', 1)
        section_name = house_info.get('section_name', '')
        
        detail_area, detail_address = get_detail_info(post_id, raw_area, raw_address, region_id, section_name)
        if not correct_area:
            correct_area = detail_area
        if not correct_address:
            correct_address = detail_address
            
    area = correct_area
    location = escape_html(correct_address or "無地址資訊")
    room_str = escape_html(house_info.get('room_str') or house_info.get('layout') or house_info.get('kind_name', '未提供格局'))
    floor_str = escape_html(house_info.get('floor_str') or house_info.get('floor') or '未提供樓層')
    
    url = f"https://rent.591.com.tw/{post_id}"
    
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

    # Global search config parameters
    min_price = config.get("rentprice_min", 0)
    max_price = config.get("rentprice_max", 0)
    if max_price > 0:
        api_params['rentprice'] = f"{min_price},{max_price}"

    # Advanced options mapping
    if config.get("not_cover") == 1:
        api_params['not_cover'] = '1'
    if config.get("lift") == 1:
        api_params['lift'] = '1'
    if config.get("balcony_1") == 1:
        api_params['balcony_1'] = '1'

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

def render_menu(criteria, menu_name):
    """
    Renders the text and inline keyboard markup for the specified menu.
    menu_name: 'main', 'region', 'price', 'kind'
    """
    district_map = {"26": "板橋", "27": "汐止", "37": "永和", "43": "三重"}
    kind_map_desc = {0: "全部", 1: "整層住家", 2: "獨立套房", 3: "分租套房", 4: "雅房"}
    
    if menu_name == "region":
        taipei_active = any(t.get("region") == 1 for t in criteria.get("targets", []))
        
        npt_targets = [t for t in criteria.get("targets", []) if t.get("region") == 3]
        npt_sections = []
        if npt_targets:
            npt_sections = npt_targets[0].get("section", "").split(",")
            
        banqiao_active = "26" in npt_sections
        xizhi_active = "27" in npt_sections
        yonghe_active = "37" in npt_sections
        sanchong_active = "43" in npt_sections
        
        text = (
            "📍 <b>地區設定選單</b>\n\n"
            "請點選以下按鈕啟用或停用要搜尋的地區（顯示 🟢 代表啟用中，🔴 代表停用中）。\n"
            "變更後系統會即時儲存設定並套用。\n"
        )
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": f"台北市: {'🟢 啟用' if taipei_active else '🔴 停用'}", "callback_data": "toggle_reg_1"}
                ],
                [
                    {"text": f"板橋區: {'🟢 啟用' if banqiao_active else '🔴 停用'}", "callback_data": "toggle_sec_26"},
                    {"text": f"三重區: {'🟢 啟用' if sanchong_active else '🔴 停用'}", "callback_data": "toggle_sec_43"}
                ],
                [
                    {"text": f"永和區: {'🟢 啟用' if yonghe_active else '🔴 停用'}", "callback_data": "toggle_sec_37"},
                    {"text": f"汐止區: {'🟢 啟用' if xizhi_active else '🔴 停用'}", "callback_data": "toggle_sec_27"}
                ],
                [
                    {"text": "🔙 返回主選單", "callback_data": "menu_main"}
                ]
            ]
        }
        return text, keyboard
        
    elif menu_name == "price":
        current_max = criteria.get("rentprice_max", 30000)
        text = (
            f"💰 <b>租金上限設定選單</b>\n\n"
            f"目前租金上限：<b>{current_max:,}</b> 元/月\n\n"
            f"💡 您可以透過點選下方按鈕直接進行微調或快速設定，或直接在對話框輸入 `/租金 <金額>` 設定特定數值。"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "➖ 1,000 元", "callback_data": "adj_price_-1000"},
                    {"text": "➕ 1,000 元", "callback_data": "adj_price_1000"}
                ],
                [
                    {"text": "➖ 5,000 元", "callback_data": "adj_price_-5000"},
                    {"text": "➕ 5,000 元", "callback_data": "adj_price_5000"}
                ],
                [
                    {"text": "💵 15k", "callback_data": "set_price_15000"},
                    {"text": "💵 20k", "callback_data": "set_price_20000"},
                    {"text": "💵 25k", "callback_data": "set_price_25000"}
                ],
                [
                    {"text": "💵 30k", "callback_data": "set_price_30000"},
                    {"text": "💵 35k", "callback_data": "set_price_35000"},
                    {"text": "💵 40k", "callback_data": "set_price_40000"}
                ],
                [
                    {"text": "🔙 返回主選單", "callback_data": "menu_main"}
                ]
            ]
        }
        return text, keyboard
        
    elif menu_name == "kind":
        current_kinds = criteria.get("kinds", [0])
        kind_desc = ", ".join(kind_map_desc.get(k, "未知") for k in current_kinds)
        text = (
            f"🏠 <b>房屋類型設定選單（可複選）</b>\n\n"
            f"目前搜尋類型：<b>{kind_desc}</b>\n\n"
            f"請點選以下按鈕啟用或停用搜尋類型（變更後系統會即時儲存設定並套用）："
        )
        
        def btn_text(name, val):
            return f"🟢 {name}" if val in current_kinds else f"⚪ {name}"
            
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": btn_text("全部房源", 0), "callback_data": "set_kind_0"}
                ],
                [
                    {"text": btn_text("整層住家", 1), "callback_data": "set_kind_1"},
                    {"text": btn_text("獨立套房", 2), "callback_data": "set_kind_2"}
                ],
                [
                    {"text": btn_text("分租套房", 3), "callback_data": "set_kind_3"},
                    {"text": btn_text("雅房", 4), "callback_data": "set_kind_4"}
                ],
                [
                    {"text": "🔙 返回主選單", "callback_data": "menu_main"}
                ]
            ]
        }
        return text, keyboard
        
    else:  # 'main' menu
        target_descs = []
        current_kinds = criteria.get("kinds", [0])
        kind_desc = ", ".join(kind_map_desc.get(k, "未知") for k in current_kinds)
        
        for t in criteria.get("targets", []):
            if t["region"] == 1:
                target_descs.append(f"• 台北市 (全部) [{kind_desc}]")
            elif t["region"] == 3:
                sec_names = [district_map.get(sid, sid) for sid in t.get("section", "").split(",") if sid]
                target_descs.append(f"• 新北市 ({', '.join(sec_names)}) [{kind_desc}]")
                
        if not target_descs:
            target_descs.append("• ⚠️ 未設定搜尋地區（請點選下方按鈕修改地區）")
                
        not_cover_status = "🟢 開" if criteria.get("not_cover", 0) == 1 else "🔴 關"
        lift_status = "🟢 開" if criteria.get("lift", 0) == 1 else "🔴 關"
        balcony_status = "🟢 開" if criteria.get("balcony_1", 0) == 1 else "🔴 關"
        floor_ratio_status = "🟢 開" if criteria.get("floor_ratio_filter", 1) == 1 else "🔴 關"
        mrt_within_500_status = "🟢 開" if criteria.get("mrt_within_500", 1) == 1 else "🔴 關"
        
        not_cover_desc = "✅ 已排除頂樓加蓋" if criteria.get("not_cover", 0) == 1 else "❌ 未排除頂樓加蓋"
        lift_desc = "✅ 限制必須有電梯" if criteria.get("lift", 0) == 1 else "❌ 不限制電梯"
        balcony_desc = "✅ 限制必須有陽台" if criteria.get("balcony_1", 0) == 1 else "❌ 不限制陽台"
        floor_ratio_desc = "✅ 限制大於總樓層一半" if criteria.get("floor_ratio_filter", 1) == 1 else "❌ 不限制高樓層"
        mrt_within_500_desc = "✅ 限制捷運 500m 內" if criteria.get("mrt_within_500", 1) == 1 else "❌ 不限制捷運距離"
        
        min_area = criteria.get("min_area", 0)
        area_limit_desc = f"{min_area} 坪以上" if min_area > 0 else "不限制"
        exclude_list = criteria.get("exclude_keywords", [])
        exclude_desc = ", ".join(exclude_list) if exclude_list else "無"
        
        text = (
            f"⚙️ <b>目前篩選條件設定</b>\n\n"
            f"💰 <b>租金上限：</b> {criteria.get('rentprice_max', 0):,} 元/月\n"
            f"📍 <b>監控地區：</b>\n" + "\n".join(target_descs) + "\n\n"
            f"🛠️ <b>進階篩選狀態：</b>\n"
            f"• {not_cover_desc}\n"
            f"• {lift_desc}\n"
            f"• {balcony_desc}\n"
            f"• {floor_ratio_desc}\n"
            f"• {mrt_within_500_desc}\n"
            f"• 📏 <b>最小坪數：</b> {area_limit_desc}\n"
            f"• 🚫 <b>排除字詞：</b> {exclude_desc}\n\n"
            f"💡 點選下方按鈕即可即時切換或進入子選單設定。"
        )
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": f"📶 排除頂加: {not_cover_status}", "callback_data": "toggle_not_cover"},
                    {"text": f"🏢 樓層限制(>一半): {floor_ratio_status}", "callback_data": "toggle_floor_ratio"}
                ],
                [
                    {"text": f"🛗 有電梯: {lift_status}", "callback_data": "toggle_lift"},
                    {"text": f"☀️ 有陽台: {balcony_status}", "callback_data": "toggle_balcony"}
                ],
                [
                    {"text": f"🚇 捷運 500m: {mrt_within_500_status}", "callback_data": "toggle_mrt_500"}
                ],
                [
                    {"text": "📍 地區設定", "callback_data": "menu_region"},
                    {"text": "💰 租金設定", "callback_data": "menu_price"}
                ],
                [
                    {"text": "🏠 類型設定", "callback_data": "menu_kind"},
                    {"text": "🔄 重新整理", "callback_data": "menu_main"}
                ]
            ]
        }
        return text, keyboard

def make_status_keyboard(criteria):
    """Generates inline keyboard markup for settings control."""
    _, keyboard = render_menu(criteria, "main")
    return keyboard

def make_status_text(criteria):
    """Generates standard status description text."""
    text, _ = render_menu(criteria, "main")
    return text


def process_telegram_commands(token, chat_id, criteria, state):
    """Fetches new Telegram messages & callback queries, updating configurations."""
    last_update_id = state.get("last_update_id", 0)
    base_url = f"https://api.telegram.org/bot{token}"
    get_updates_url = f"{base_url}/getUpdates"
    
    params = {"timeout": 3}
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
                
            # A. Process Callback Queries (Button Click Actions)
            callback_query = update.get("callback_query")
            if callback_query:
                sender_id = callback_query.get("from", {}).get("id")
                if str(sender_id) != str(chat_id):
                    continue
                    
                cq_id = callback_query.get("id")
                data = callback_query.get("data", "")
                msg = callback_query.get("message", {})
                msg_id = msg.get("message_id")
                
                alert_text = ""
                active_menu = "main"
                
                if data == "menu_main":
                    active_menu = "main"
                    alert_text = "已返回主選單"
                elif data == "menu_region":
                    active_menu = "region"
                    alert_text = "載入地區設定選單"
                elif data == "menu_price":
                    active_menu = "price"
                    alert_text = "載入租金設定選單"
                elif data == "menu_kind":
                    active_menu = "kind"
                    alert_text = "載入房屋類型選單"
                elif data == "toggle_not_cover":
                    current = criteria.get("not_cover", 0)
                    criteria["not_cover"] = 1 if current == 0 else 0
                    alert_text = "已排除頂加" if criteria["not_cover"] == 1 else "已取消排除頂加"
                    active_menu = "main"
                elif data == "toggle_lift":
                    current = criteria.get("lift", 0)
                    criteria["lift"] = 1 if current == 0 else 0
                    alert_text = "限制必須有電梯" if criteria["lift"] == 1 else "取消電梯限制"
                    active_menu = "main"
                elif data == "toggle_balcony":
                    current = criteria.get("balcony_1", 0)
                    criteria["balcony_1"] = 1 if current == 0 else 0
                    alert_text = "限制必須有陽台" if criteria["balcony_1"] == 1 else "取消陽台限制"
                    active_menu = "main"
                elif data == "toggle_floor_ratio":
                    current = criteria.get("floor_ratio_filter", 1)
                    criteria["floor_ratio_filter"] = 1 if current == 0 else 0
                    alert_text = "已開啟樓層限制(>一半)" if criteria["floor_ratio_filter"] == 1 else "已關閉樓層限制"
                    active_menu = "main"
                elif data == "toggle_mrt_500":
                    current = criteria.get("mrt_within_500", 1)
                    criteria["mrt_within_500"] = 1 if current == 0 else 0
                    alert_text = "限制捷運 500m 內" if criteria["mrt_within_500"] == 1 else "取消捷運距離限制"
                    active_menu = "main"
                elif data == "toggle_reg_1":
                    active_menu = "region"
                    current_kinds = criteria.get("kinds", [0])
                    current_kind = current_kinds[0] if current_kinds else 0
                    targets = criteria.get("targets", [])
                    t_taipei = [t for t in targets if t.get("region") == 1]
                    if t_taipei:
                        targets = [t for t in targets if t.get("region") != 1]
                        alert_text = "已停用台北市搜尋"
                    else:
                        targets.append({"region": 1, "kind": current_kind})
                        alert_text = "已啟用台北市搜尋"
                    criteria["targets"] = targets
                elif data.startswith("toggle_sec_"):
                    active_menu = "region"
                    sec_id = data.split("_")[-1]
                    current_kinds = criteria.get("kinds", [0])
                    current_kind = current_kinds[0] if current_kinds else 0
                    targets = criteria.get("targets", [])
                    t_npt = [t for t in targets if t.get("region") == 3]
                    district_names = {"26": "板橋區", "27": "汐止區", "37": "永和區", "43": "三重區"}
                    d_name = district_names.get(sec_id, sec_id)
                    
                    if t_npt:
                        target_npt = t_npt[0]
                        sections = [s for s in target_npt.get("section", "").split(",") if s]
                        if sec_id in sections:
                            sections.remove(sec_id)
                            alert_text = f"已停用 {d_name} 搜尋"
                        else:
                            sections.append(sec_id)
                            alert_text = f"已啟用 {d_name} 搜尋"
                        if sections:
                            target_npt["section"] = ",".join(sections)
                        else:
                            targets = [t for t in targets if t.get("region") != 3]
                    else:
                        targets.append({"region": 3, "section": sec_id, "kind": current_kind})
                        alert_text = f"已啟用 {d_name} 搜尋"
                    criteria["targets"] = targets
                elif data.startswith("adj_price_"):
                    active_menu = "price"
                    val = int(data.split("_")[-1])
                    current_max = criteria.get("rentprice_max", 30000)
                    new_max = max(0, current_max + val)
                    criteria["rentprice_max"] = new_max
                    alert_text = f"租金上限調整為：{new_max:,} 元"
                elif data.startswith("set_price_"):
                    active_menu = "price"
                    val = int(data.split("_")[-1])
                    criteria["rentprice_max"] = val
                    alert_text = f"租金上限設定為：{val:,} 元"
                elif data.startswith("set_kind_"):
                    active_menu = "kind"
                    kind_val = int(data.split("_")[-1])
                    current_kinds = list(criteria.get("kinds", [0]))
                    kind_names = {0: "全部房源", 1: "整層住家", 2: "獨立套房", 3: "分租套房", 4: "雅房"}
                    k_name = kind_names.get(kind_val, str(kind_val))
                    
                    if kind_val == 0:
                        criteria["kinds"] = [0]
                        alert_text = "已設定為：全部房源"
                    else:
                        if 0 in current_kinds:
                            current_kinds.remove(0)
                        
                        if kind_val in current_kinds:
                            current_kinds.remove(kind_val)
                            alert_text = f"已停用：{k_name}"
                        else:
                            current_kinds.append(kind_val)
                            alert_text = f"已啟用：{k_name}"
                            
                        if not current_kinds:
                            current_kinds = [0]
                            alert_text = "無選取項目，預設為：全部房源"
                            
                        criteria["kinds"] = current_kinds
                    
                # Answer callback immediately
                ans_url = f"{base_url}/answerCallbackQuery"
                requests.post(ans_url, json={
                    "callback_query_id": cq_id,
                    "text": alert_text,
                    "show_alert": False
                }, timeout=5)
                
                # Determine if criteria actually changed
                is_change = not data.startswith("menu_")
                if is_change:
                    criteria_changed = True
                    
                # Re-render status text and update inline keyboard layout
                status_text, status_keyboard = render_menu(criteria, active_menu)
                edit_url = f"{base_url}/editMessageText"
                payload = {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": status_text,
                    "parse_mode": "HTML",
                    "reply_markup": status_keyboard
                }
                requests.post(edit_url, json=payload, timeout=10)
                continue

            # B. Process Standard Text Commands
            message = update.get("message")
            if not message:
                continue
                
            sender_id = message.get("chat", {}).get("id")
            if str(sender_id) != str(chat_id):
                continue
                
            text = message.get("text", "").strip()
            if not text:
                continue
                
            reply_text = ""
            keyboard = None
            
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
                        reply_text = "❌ <b>找不到地區</b>\n支援的地區包含：台北、板橋、三重、永和、汐止。"
                except Exception as e:
                    reply_text = f"❌ <b>設定失敗</b>: {e}"
                    
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
                    new_kinds = []
                    for k_name, k_val in kind_map.items():
                        if k_name in kind_str:
                            if k_val not in new_kinds:
                                new_kinds.append(k_val)
                            
                    if new_kinds:
                        if 0 in new_kinds:
                            new_kinds = [0]
                        criteria["kinds"] = new_kinds
                        criteria_changed = True
                        
                        reverse_kind_map = {0: "全部", 1: "整層住家", 2: "獨立套房", 3: "分租套房", 4: "雅房"}
                        reply_text = f"⚙️ <b>設定成功</b>\n租屋類型已更新為：{', '.join(reverse_kind_map.get(k) for k in new_kinds)}"
                    else:
                        reply_text = "❌ <b>類型錯誤</b>\n支援的類型有：全部、整層、獨立套房、分租套房、雅房。"
                except Exception as e:
                    reply_text = f"❌ <b>設定失敗</b>: {e}"
                    
            # 4. /exclude or /排除
            elif text.startswith("/exclude") or text.startswith("/排除"):
                parts = text.split(maxsplit=1)
                exclude_list = criteria.setdefault("exclude_keywords", ["林森北路"])
                
                if len(parts) < 2:
                    exclude_desc = ", ".join(exclude_list) if exclude_list else "無"
                    reply_text = (
                        f"🚫 <b>目前排除字詞：</b> {exclude_desc}\n\n"
                        f"💡 輸入 `/排除 <關鍵字>` 可以新增或移除排除關鍵字（例如：`/排除 林森北路`）"
                    )
                else:
                    kw = parts[1].strip()
                    if not kw:
                        exclude_desc = ", ".join(exclude_list) if exclude_list else "無"
                        reply_text = (
                            f"🚫 <b>目前排除字詞：</b> {exclude_desc}\n\n"
                            f"💡 輸入 `/排除 <關鍵字>` 可以新增或移除排除關鍵字（例如：`/排除 林森北路`）"
                        )
                    else:
                        if kw in exclude_list:
                            exclude_list.remove(kw)
                            reply_text = f"⚙️ <b>設定成功</b>\n已移除排除字詞：{kw}"
                        else:
                            exclude_list.append(kw)
                            reply_text = f"⚙️ <b>設定成功</b>\n已新增排除字詞：{kw}"
                        criteria["exclude_keywords"] = exclude_list
                        criteria_changed = True
                        
            # 5. /area or /坪數
            elif text.startswith("/area ") or text.startswith("/坪數 "):
                try:
                    area_str = text.split(maxsplit=1)[1]
                    val = float(area_str)
                    criteria["min_area"] = val
                    criteria_changed = True
                    reply_text = f"⚙️ <b>設定成功</b>\n最小坪數限制已更新為：{val} 坪以上" if val > 0 else "⚙️ <b>設定成功</b>\n已取消最小坪數限制"
                except Exception:
                    reply_text = "❌ <b>格式錯誤</b>\n請輸入 `/坪數 <數字>` (例如：`/坪數 15`，輸入 0 代表不限制)"
                    
            # 6. /floor or /樓層
            elif text.startswith("/floor") or text.startswith("/樓層"):
                parts = text.split(maxsplit=1)
                current = criteria.get("floor_ratio_filter", 1)
                if len(parts) < 2:
                    # Toggle
                    new_val = 1 if current == 0 else 0
                    criteria["floor_ratio_filter"] = new_val
                    criteria_changed = True
                    reply_text = "⚙️ <b>設定成功</b>\n已開啟樓層限制 (房源樓層必須大於總樓層一半)" if new_val == 1 else "⚙️ <b>設定成功</b>\n已關閉樓層限制"
                else:
                    arg = parts[1].strip()
                    if arg in ("1", "on", "開", "啟用", "true"):
                        criteria["floor_ratio_filter"] = 1
                        criteria_changed = True
                        reply_text = "⚙️ <b>設定成功</b>\n已開啟樓層限制 (房源樓層必須大於總樓層一半)"
                    elif arg in ("0", "off", "關", "停用", "false"):
                        criteria["floor_ratio_filter"] = 0
                        criteria_changed = True
                        reply_text = "⚙️ <b>設定成功</b>\n已關閉樓層限制"
                    else:
                        reply_text = "❌ <b>格式錯誤</b>\n請輸入 `/樓層` (切換開關) 或 `/樓層 <開/關>`"
                        
            # 6.5 /mrt or /捷運
            elif text.startswith("/mrt") or text.startswith("/捷運"):
                parts = text.split(maxsplit=1)
                current = criteria.get("mrt_within_500", 1)
                if len(parts) < 2:
                    # Toggle
                    new_val = 1 if current == 0 else 0
                    criteria["mrt_within_500"] = new_val
                    criteria_changed = True
                    reply_text = "⚙️ <b>設定成功</b>\n已開啟捷運距離限制 (離捷運站500公尺內)" if new_val == 1 else "⚙️ <b>設定成功</b>\n已關閉捷運距離限制"
                else:
                    arg = parts[1].strip()
                    if arg in ("1", "on", "開", "啟用", "true"):
                        criteria["mrt_within_500"] = 1
                        criteria_changed = True
                        reply_text = "⚙️ <b>設定成功</b>\n已開啟捷運距離限制 (離捷運站500公尺內)"
                    elif arg in ("0", "off", "關", "停用", "false"):
                        criteria["mrt_within_500"] = 0
                        criteria_changed = True
                        reply_text = "⚙️ <b>設定成功</b>\n已關閉捷運距離限制"
                    else:
                        reply_text = "❌ <b>格式錯誤</b>\n請輸入 `/捷運` (切換開關) 或 `/捷運 <開/關>`"
                        
            # 7. /status or /狀態
            elif text == "/status" or text == "/狀態":
                reply_text, keyboard = render_menu(criteria, "main")
                
            if reply_text:
                send_msg_url = f"{base_url}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": reply_text,
                    "parse_mode": "HTML"
                }
                if keyboard:
                    payload["reply_markup"] = keyboard
                requests.post(send_msg_url, json=payload, timeout=10)
                
        state["last_update_id"] = latest_update_id
        
        if criteria_changed:
            try:
                filtered_criteria = {
                    "rentprice_min": criteria.get("rentprice_min", 0),
                    "rentprice_max": criteria.get("rentprice_max", 30000),
                    "targets": criteria.get("targets", []),
                    "kinds": criteria.get("kinds", [0]),
                    "not_cover": criteria.get("not_cover", 0),
                    "lift": criteria.get("lift", 0),
                    "balcony_1": criteria.get("balcony_1", 0),
                    "exclude_keywords": criteria.get("exclude_keywords", ["林森北路"]),
                    "min_area": criteria.get("min_area", 15),
                    "floor_ratio_filter": criteria.get("floor_ratio_filter", 1),
                    "mrt_within_500": criteria.get("mrt_within_500", 1),
                    "other_params": criteria.get("other_params", {})
                }
                with open(CRITERIA_PATH, 'w', encoding='utf-8') as f:
                    json.dump(filtered_criteria, f, indent=4, ensure_ascii=False)
                print("[OK] Search criteria updated and saved.")
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
    
    # Merge configurations
    config.update(criteria)
    
    if (config.get("telegram_bot_token") == "YOUR_TELEGRAM_BOT_TOKEN" or 
        config.get("telegram_chat_id") == "YOUR_TELEGRAM_CHAT_ID"):
        print("[!] Setup Required: Please fill in your Telegram Token and Chat ID.")
        return

    session = requests.Session()
    state = load_seen_listings()
    seen_listings = state["seen_ids"]
    print(f"[*] Loaded {len(seen_listings)} previously seen listings.")
    
    is_first_run = len(seen_listings) == 0
    
    token = config["telegram_bot_token"]
    chat_id = config["telegram_chat_id"]
    
    check_interval = config.get("check_interval_seconds", 86400)
    run_once = config.get("run_once", False) or ("--once" in sys.argv)
    
    # Daemon loop / Scheduling logic
    last_scrape_time = 0
    
    targets_desc = []
    current_kinds = config.get("kinds", [0])
    kind_names_desc = {0: "全部", 1: "整層", 2: "獨套", 3: "分套", 4: "雅房"}
    kind_desc = ", ".join(kind_names_desc.get(k, "未知") for k in current_kinds)
    
    for t in config.get("targets", []):
        if t["region"] == 1:
            targets_desc.append(f"台北市(全部)[{kind_desc}]")
        elif t["region"] == 3:
            district_map = {"26": "板橋", "27": "汐止", "37": "永和", "43": "三重"}
            sec_names = [district_map.get(sid, sid) for sid in t.get("section", "").split(",") if sid]
            targets_desc.append(f"新北市({', '.join(sec_names)})[{kind_desc}]")
            
    print(f"[*] Search Targets: {', '.join(targets_desc)} | Max Price: {config.get('rentprice_max')} TWD")
    if run_once:
        print("[*] Running in single-check mode (Run Once).")
    else:
        print(f"[*] Command checking active. Scraper interval: {check_interval} seconds.")
    print("-" * 60)

    while True:
        # 1. Check for incoming Telegram commands (runs every loop iteration - 2 seconds)
        criteria_changed = process_telegram_commands(token, chat_id, config, state)
        if criteria_changed:
            criteria = load_criteria()
            config.update(criteria)
            # Make sure we persist latest config state locally
            state["seen_ids"] = seen_listings
            save_seen_listings(state)
            last_scrape_time = 0  # Force immediate scrape on criteria change
            
            
        # 2. Check if it's time to query 591
        now = time.time()
        should_scrape = False
        
        if run_once:
            should_scrape = True
        elif now - last_scrape_time >= check_interval:
            should_scrape = True
            
        if should_scrape:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time}] Fetching listings from 591...")
            
            all_listings = []
            seen_post_ids = set()
            active_kinds = config.get("kinds", [0])
            
            for target in config.get("targets", []):
                for k in active_kinds:
                    k_name = {0: "全部", 1: "整層住家", 2: "獨立套房", 3: "分租套房", 4: "雅房"}.get(k, str(k))
                    print(f"[{current_time}] Fetching target: Region {target.get('region')} Section {target.get('section', 'All')} Kind {k_name}...")
                    
                    target_copy = target.copy()
                    target_copy["kind"] = k
                    
                    target_listings = get_591_listings(session, config, target_copy)
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
                        
                        # 1. Floor ratio filter
                        if config.get("floor_ratio_filter", 1) == 1:
                            floor_str = listing.get('floor_str') or listing.get('floor')
                            cur_fl, tot_fl = parse_floor(floor_str)
                            if cur_fl is not None and tot_fl is not None:
                                if not (cur_fl > (tot_fl / 2.0)):
                                    print(f"[!] Excluded listing {post_id} due to floor {floor_str} (Cur: {cur_fl} <= Half Tot: {tot_fl/2.0})")
                                    continue
                                    
                        # 1.5 MRT distance filter
                        if config.get("mrt_within_500", 1) == 1:
                            surrounding = listing.get("surrounding")
                            if not check_mrt_constraint(surrounding, max_dist=500):
                                print(f"[!] Excluded listing {post_id} due to MRT distance/absence: {surrounding}")
                                continue
                                    
                        # 2. Fetch correct area and real address once
                        raw_area = listing.get('area', '0')
                        raw_address = listing.get('address') or listing.get('location') or ""
                        region_id = listing.get('region', 1)
                        section_name = listing.get('section_name', '')
                        
                        detail_area, detail_address = get_detail_info(post_id, raw_area, raw_address, region_id, section_name)
                        listing['correct_area'] = detail_area
                        listing['correct_address'] = detail_address
                        
                        # 3. Check area size filter
                        min_area = config.get("min_area", 0)
                        if min_area > 0:
                            area_val = 0.0
                            try:
                                area_match = re.search(r'([\d\.]+)', detail_area)
                                if area_match:
                                    area_val = float(area_match.group(1))
                            except Exception:
                                pass
                            
                            if area_val < min_area:
                                print(f"[!] Excluded listing {post_id} due to area {area_val} < min_area {min_area}")
                                continue
                        
                        # 4. Check exclude keywords (using real detail_address)
                        exclude_list = config.get("exclude_keywords", [])
                        should_exclude = False
                        matched_kw = ""
                        check_text = (
                            f"{listing.get('title') or ''} "
                            f"{listing.get('name') or ''} "
                            f"{detail_address} "
                            f"{listing.get('location') or ''} "
                            f"{listing.get('section_name') or ''} "
                            f"{listing.get('street_name') or ''}"
                        )
                        for kw in exclude_list:
                            if kw and kw in check_text:
                                should_exclude = True
                                matched_kw = kw
                                break
                                
                        if should_exclude:
                            print(f"[!] Excluded listing {post_id} containing keyword: '{matched_kw}'")
                            continue
                            
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
                
            last_scrape_time = now
            
        if run_once:
            print("[*] Single check complete. Exiting.")
            break
            
        # Poll Telegram every 2 seconds
        time.sleep(2)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Bot stopped by user.")

import os
import re
import sys
import json
import time
import requests
from datetime import datetime

CONFIG_PATH = 'config.json'
SEEN_LISTINGS_PATH = 'seen_listings.json'

def escape_html(text):
    """Escapes HTML special characters for Telegram HTML parse mode."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def load_config():
    """Loads bot configuration. Supports environment variables with config.json fallback."""
    # Default base configurations with environment variables fallback
    config = {
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID"),
        "check_interval_seconds": int(os.environ.get("CHECK_INTERVAL_SECONDS", 86400)),
        "region": int(os.environ.get("REGION", 1)),
        "kind": int(os.environ.get("KIND", 0)),
        "rentprice_min": int(os.environ.get("RENTPRICE_MIN", 0)),
        "rentprice_max": int(os.environ.get("RENTPRICE_MAX", 30000)),
        "run_once": os.environ.get("RUN_ONCE", "False").lower() in ("true", "1", "yes"),
        "other_params": {}
    }

    # If config.json exists, read it to overwrite defaults
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                # Filter out values that are still placeholder defaults
                filtered_file_config = {
                    k: v for k, v in file_config.items() 
                    if v not in ("YOUR_TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_CHAT_ID")
                }
                config.update(filtered_file_config)
        except Exception as e:
            print(f"[ERROR] Failed to load config.json: {e}")
    else:
        # If neither config.json nor environment variables are configured, write a default template
        if config["telegram_bot_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
            try:
                default_config = {
                    "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
                    "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID",
                    "check_interval_seconds": 86400,
                    "region": 1,
                    "kind": 0,
                    "rentprice_min": 0,
                    "rentprice_max": 30000,
                    "other_params": {},
                    "run_once": False
                }
                with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                print(f"[!] Created default config file template: {CONFIG_PATH}")
            except Exception as e:
                print(f"[!] Warning: Could not create config template: {e}")

    return config

def load_seen_listings():
    """Loads previously seen house IDs to avoid duplicate notifications."""
    if os.path.exists(SEEN_LISTINGS_PATH):
        try:
            with open(SEEN_LISTINGS_PATH, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[!] Warning: Failed to parse seen listings database, starting fresh: {e}")
            return set()
    return set()

def save_seen_listings(seen_ids):
    """Saves the seen listing IDs to database file."""
    try:
        with open(SEEN_LISTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(list(seen_ids), f, indent=4, ensure_ascii=False)
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
    
    # Try different key names for location
    location = escape_html(
        house_info.get('address') or 
        house_info.get('location') or 
        f"{house_info.get('section_name', '')}{house_info.get('street_name', '')}" or 
        "無地址資訊"
    )
    
    # 591 Detail page link
    url = f"https://rent.591.com.tw/rent-detail-{post_id}.html"
    
    # Formulate message caption
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
    
    # Obtain cover photo URL if available
    photo_url = house_info.get('cover') or house_info.get('photo_list', [None])[0]
    
    # Default Telegram Bot API URL
    base_url = f"https://api.telegram.org/bot{token}"
    
    # Attempt to send as photo message first if a photo is available
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
                print(f"[✓] Sent photo notification for house ID: {post_id}")
                return True
            else:
                print(f"[!] sendPhoto failed with status code {res.status_code}, falling back to sendMessage. Response: {res.text}")
        except Exception as e:
            print(f"[!] Error sending photo: {e}, falling back to sendMessage.")

    # Fallback/Default: Send as plain HTML text message
    send_msg_url = f"{base_url}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(send_msg_url, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"[✓] Sent text notification for house ID: {post_id}")
            return True
        else:
            print(f"[ERROR] sendMessage failed: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")
        return False

def get_591_listings(session, config):
    """Fetches the latest rental listings from 591 rsList API."""
    region = config.get("region", 1)
    kind = config.get("kind", 0)
    
    # Headers needed to mimic a browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }

    # Step 1: Visit main site to obtain base session cookies and CSRF token
    try:
        main_url = 'https://rent.591.com.tw/'
        # Add region parameters to main page visit to match search state
        params = {'region': region}
        
        # Set urlJumpIp cookie directly to force chosen region state in 591 session
        session.cookies.set('urlJumpIp', str(region), domain='.591.com.tw')
        
        response = session.get(main_url, headers=headers, params=params, timeout=15)
        
        if response.status_code != 200:
            print(f"[ERROR] Failed to fetch 591 homepage: HTTP {response.status_code}")
            return []
            
        # Parse CSRF token using regex to avoid external dependency
        csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
        if not csrf_match:
            print("[ERROR] CSRF token not found on the page. 591 page structure might have changed.")
            return []
        
        csrf_token = csrf_match.group(1)
        
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

    # Query parameters for rsList API
    api_params = {
        'is_format_data': '1',
        'is_new_list': '1',
        'type': '1',
        'region': str(region),
        'kind': str(kind),
        'order': 'posttime',      # Sort by newest
        'orderType': 'desc',      # Descending order (latest first)
    }

    # Price range
    min_price = config.get("rentprice_min", 0)
    max_price = config.get("rentprice_max", 0)
    if max_price > 0:
        api_params['rentprice'] = f"{min_price},{max_price}"

    # Merge user custom configurations
    if config.get("other_params"):
        api_params.update(config.get("other_params"))

    # Step 3: Fetch listings
    api_url = 'https://rent.591.com.tw/home/search/rsList'
    try:
        # Add random timestamp parameter to avoid server-side or CDN caching
        api_params['_'] = int(time.time() * 1000)
        
        res = session.get(api_url, headers=api_headers, params=api_params, timeout=15)
        
        if res.status_code == 419:
            print("[ERROR] HTTP 419: Session or CSRF token expired.")
            return []
        elif res.status_code != 200:
            print(f"[ERROR] HTTP {res.status_code} requesting 591 API. Body: {res.text[:200]}")
            return []

        response_data = res.json()
        
        # Verify JSON structure
        if response_data.get('status') == 1 and 'data' in response_data:
            inner_data = response_data['data']
            if isinstance(inner_data, dict) and 'data' in inner_data:
                return inner_data['data']
            elif isinstance(inner_data, list):
                return inner_data
                
        print(f"[!] Warning: Unexpected JSON response structure from 591: {list(response_data.keys())}")
        return []
        
    except json.JSONDecodeError:
        print("[ERROR] Failed to parse 591 response as JSON.")
        return []
    except Exception as e:
        print(f"[ERROR] Exception occurred during API request: {e}")
        return []

def main():
    print("="*60)
    print("      591 Rental Site Telegram Alert Bot - Active      ")
    print("="*60)
    
    config = load_config()
    
    # Guard clause if default configs aren't set
    if (config.get("telegram_bot_token") == "YOUR_TELEGRAM_BOT_TOKEN" or 
        config.get("telegram_chat_id") == "YOUR_TELEGRAM_CHAT_ID"):
        print("[!] Setup Required: Please fill in your Telegram Token and Chat ID in 'config.json'.")
        return

    # Use a persistent requests.Session to maintain cookies across retries
    session = requests.Session()
    
    # Initialize seen database
    seen_listings = load_seen_listings()
    print(f"[*] Loaded {len(seen_listings)} previously seen listings.")
    
    is_first_run = len(seen_listings) == 0
    if is_first_run:
        print("[*] First run: Bot will index current listings and start notifying on subsequent checks.")
    check_interval = config.get("check_interval_seconds", 300)
    
    # Check if run once is requested via config or command line arguments
    run_once = config.get("run_once", False) or ("--once" in sys.argv)
    
    print(f"[*] Search Region: {config.get('region')} | Kind: {config.get('kind')} | Max Price: {config.get('rentprice_max')} TWD")
    if run_once:
        print("[*] Running in single-check mode (Run Once).")
    else:
        print(f"[*] Checking every {check_interval} seconds...")
    print("-" * 60)

    while True:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time}] Fetching listings from 591...")
        
        listings = get_591_listings(session, config)
        
        if listings:
            print(f"[{current_time}] Successfully fetched {len(listings)} listings.")
            new_listings_count = 0
            
            # Iterate listings in reverse order (oldest first) so that 
            # notifications arrive on Telegram in chronological order (newest last).
            for listing in reversed(listings):
                post_id = listing.get('post_id') or listing.get('id')
                if not post_id:
                    continue
                    
                post_id = str(post_id)
                
                if post_id not in seen_listings:
                    seen_listings.add(post_id)
                    new_listings_count += 1
                    
                    # If this is the very first execution, we just populate the "seen" list
                    # to prevent flooding the Telegram chat with old listings.
                    if not is_first_run:
                        send_telegram_notification(
                            token=config["telegram_bot_token"],
                            chat_id=config["telegram_chat_id"],
                            house_info=listing
                        )
                        # Add a minor delay between sending Telegram messages to prevent rate-limiting
                        time.sleep(1.5)
            
            # Save progress
            if new_listings_count > 0:
                save_seen_listings(seen_listings)
                if is_first_run:
                    print(f"[{current_time}] Initialized seen listings with {new_listings_count} houses.")
                    is_first_run = False
                else:
                    print(f"[{current_time}] Processed {new_listings_count} new listings.")
            else:
                print(f"[{current_time}] No new listings found.")
                
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

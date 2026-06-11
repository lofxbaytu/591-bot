import os
import sys
import time
import re
import requests

# Add current directory to path
bot_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(bot_dir)

import bot

# Configure console output to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

def main():
    print("==========================================================")
    print("   Starting Manual Push for Today's Rental Listings")
    print("==========================================================")
    
    config = bot.load_config()
    criteria = bot.load_criteria()
    config.update(criteria)
    
    token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")
    
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN" or not chat_id or chat_id == "YOUR_TELEGRAM_CHAT_ID":
        print("[ERROR] Credentials not found in config.json. Please configure them first.")
        return
        
    print(f"[*] Credentials Loaded - Token: {token[:10]}... | Chat ID: {chat_id}")
    
    session = requests.Session()
    
    # 1. Fetch homepage to get cookies and CSRF token
    headers_desktop = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    try:
        session.cookies.set('urlJumpIp', '1', domain='.591.com.tw')
        r_home = session.get("https://www.591.com.tw/", headers=headers_desktop, timeout=10)
        csrf_match = re.search(r'<meta name="csrf-token" content="([^"]+)">', r_home.text)
        if csrf_match:
            csrf_token = csrf_match.group(1)
            print("[*] Obtained CSRF Token.")
        else:
            print("[ERROR] CSRF Token not found. Exiting.")
            return
            
        new_session_val = None
        for cookie in session.cookies:
            if cookie.name == '591_new_session':
                new_session_val = cookie.value
                break
        if new_session_val:
            session.cookies.set('591_new_session', new_session_val, domain='.591.com.tw')
            
    except Exception as e:
        print("[ERROR] Exception initialization:", e)
        return

    # 2. Fetch listings
    all_listings = []
    seen_post_ids = set()
    active_kinds = config.get("kinds", [0])
    
    print("[*] Fetching listings from 591 API...")
    for target in config.get("targets", []):
        for k in active_kinds:
            k_name = {0: "全部", 1: "整層住家", 2: "獨立套房", 3: "分租套房", 4: "雅房"}.get(k, str(k))
            print(f"    - Fetching target: Region {target.get('region')} Section {target.get('section', 'All')} Kind {k_name}...")
            
            target_copy = target.copy()
            target_copy["kind"] = k
            
            target_listings = bot.get_591_listings(session, config, target_copy)
            for item in target_listings:
                post_id = item.get('post_id') or item.get('id')
                if post_id and post_id not in seen_post_ids:
                    seen_post_ids.add(post_id)
                    all_listings.append(item)
            time.sleep(1.5)

    print(f"[*] Fetched {len(all_listings)} total unique raw listings.")
    
    # 3. Filter and process
    matching_listings = []
    
    for listing in all_listings:
        post_id = str(listing.get('post_id') or listing.get('id'))
        
        # A. Floor ratio filter
        if config.get("floor_ratio_filter", 1) == 1:
            floor_str = listing.get('floor_str') or listing.get('floor')
            cur_fl, tot_fl = bot.parse_floor(floor_str)
            if cur_fl is not None and tot_fl is not None:
                if not (cur_fl > (tot_fl / 2.0)):
                    continue
                    
        # B. MRT distance filter
        if config.get("mrt_within_500", 1) == 1:
            surrounding = listing.get("surrounding")
            if not bot.check_mrt_constraint(surrounding, max_dist=500):
                continue
                
        # C. Fetch details for area and address verification
        raw_area = listing.get('area', '0')
        raw_address = listing.get('address') or listing.get('location') or ""
        region_id = listing.get('region', 1)
        section_name = listing.get('section_name', '')
        
        detail_area, detail_address = bot.get_detail_info(post_id, raw_area, raw_address, region_id, section_name)
        listing['correct_area'] = detail_area
        listing['correct_address'] = detail_address
        
        # D. Min area size filter
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
                continue
                
        # E. Exclude keywords filter
        exclude_list = config.get("exclude_keywords", [])
        should_exclude = False
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
                break
        if should_exclude:
            continue
            
        matching_listings.append(listing)
        
    print(f"[*] Found {len(matching_listings)} listings matching the search criteria.")
    
    # 4. Push matching listings (limit to top 5 to avoid spamming)
    limit = 5
    pushed_count = 0
    print(f"[*] Pushing top {limit} listings to Telegram...")
    
    for listing in matching_listings[:limit]:
        post_id = listing.get('post_id') or listing.get('id')
        title = listing.get('title') or listing.get('name')
        price = listing.get('price')
        
        print(f"    - Sending listing {post_id}: {title} (${price})")
        success = bot.send_telegram_notification(token, chat_id, listing)
        if success:
            pushed_count += 1
        time.sleep(2)
        
    print(f"==========================================================")
    print(f"   Done! Successfully pushed {pushed_count} listings.")
    print("==========================================================")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import sys
import time
import json
import urllib.request
import urllib.error
import http.cookiejar
import re

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# You can pass your Steam ID as a command-line argument.
# If omitted, the script will prompt you for it at runtime.
# Supports full URLs (e.g. https://steamcommunity.com/profiles/...) as well.

# Optional: Paste your Steam Cookie string here if your wishlist is private
# or if you get redirected/blocked by Steam's anti-scraping systems.
# To get this: Log in to Steam in browser, press F12, go to Network tab,
# click any request to store.steampowered.com, and copy the 'Cookie' header value.
COOKIE_STRING = ""

# Limit the number of games to check for quick testing. Set to None to check all.
LIMIT_GAMES = None

# Sleep delay between individual Steam API requests (seconds)
# Steam's API rate limits are aggressive. 1.5s is recommended.
STEAM_API_DELAY = 1.5

# ==============================================================================
# COLOR CONFIGURATION (ANSI escape sequences)
# ==============================================================================
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"

def supports_color():
    """Detects if the terminal supports ANSI color codes."""
    import os
    # Windows CMD needs enablement, but modern terminals (VSCode, Windows Terminal) support it.
    if os.name == 'nt':
        # Enable ANSI support on Windows 10+ console
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return "ANSICON" in os.environ or "WT_SESSION" in os.environ
    return True

# Disable colors if not supported
USE_COLORS = supports_color()

def c_str(text, *colors):
    if not USE_COLORS:
        return text
    prefix = "".join(colors)
    return f"{prefix}{text}{COLOR_RESET}"

# ==============================================================================
# HTTP REQUEST HELPER (Zero-dependency fallback with Cookie Support)
# ==============================================================================
cookie_jar = http.cookiejar.CookieJar()
cookie_processor = urllib.request.HTTPCookieProcessor(cookie_jar)
opener = urllib.request.build_opener(cookie_processor)

def fetch_json(url, headers=None):
    """Fetches JSON content from a URL using urllib opener. Handles cookies & errors."""
    if headers is None:
        headers = {}
    
    if "User-Agent" not in headers:
        headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
        
    if COOKIE_STRING:
        headers["Cookie"] = COOKIE_STRING
        
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=15) as response:
            if response.status == 200:
                data = response.read().decode('utf-8')
                return json.loads(data)
            else:
                raise Exception(f"HTTP Status {response.status}")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(c_str("\n[!] Steam API rate limit reached! Try increasing STEAM_API_DELAY.", COLOR_RED, COLOR_BOLD))
        raise e
    except Exception as e:
        raise e

def fetch_raw(url, headers=None):
    """Fetches raw content from a URL to establish session cookies."""
    if headers is None:
        headers = {}
    if "User-Agent" not in headers:
        headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
    if COOKIE_STRING:
        headers["Cookie"] = COOKIE_STRING
        
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=15) as response:
            return response.read()
    except Exception as e:
        raise e

# ==============================================================================
# API OPERATIONS
# ==============================================================================
def get_exchange_rates():
    """Queries NBP API for USD and EUR exchange rates to PLN."""
    print(c_str("Fetching exchange rates from Narodowy Bank Polski...", COLOR_CYAN))
    
    usd_url = "http://api.nbp.pl/api/exchangerates/rates/a/usd/?format=json"
    eur_url = "http://api.nbp.pl/api/exchangerates/rates/a/eur/?format=json"
    
    try:
        usd_data = fetch_json(usd_url)
        usd_rate = usd_data["rates"][0]["mid"]
        print(f"  USD to PLN Rate: {c_str(f'{usd_rate:.4f}', COLOR_GREEN)} PLN")
    except Exception as e:
        print(c_str(f"Error fetching USD rate: {e}", COLOR_RED))
        sys.exit(1)
        
    try:
        eur_data = fetch_json(eur_url)
        eur_rate = eur_data["rates"][0]["mid"]
        print(f"  EUR to PLN Rate: {c_str(f'{eur_rate:.4f}', COLOR_GREEN)} PLN")
    except Exception as e:
        print(c_str(f"Error fetching EUR rate: {e}", COLOR_RED))
        sys.exit(1)
        
    return usd_rate, eur_rate

def resolve_vanity_url(vanity_name):
    """Resolves a Steam vanity URL name to a 64-bit Steam ID using the public API."""
    url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?vanityurl={vanity_name}&key=DUMMY"
    # This endpoint doesn't actually require a valid API key for public profiles
    # But if it fails, we return None and let the caller handle it
    try:
        data = fetch_json(url)
        if data and data.get("response", {}).get("success") == 1:
            return data["response"]["steamid"]
    except Exception:
        pass
    return None

def get_wishlist(steam_id):
    """Fetches wishlist items using Steam's IWishlistService API (separate from the store)."""
    
    # If the user gave a vanity name instead of a numeric ID, try to resolve it
    is_numeric = bool(re.match(r"^\d+$", steam_id))
    if not is_numeric:
        print(c_str(f"Resolving vanity URL '{steam_id}' to Steam ID...", COLOR_CYAN))
        resolved = resolve_vanity_url(steam_id)
        if resolved:
            print(f"  Resolved to: {c_str(resolved, COLOR_GREEN)}")
            steam_id = resolved
        else:
            print(c_str(f"Could not resolve vanity URL. Trying as-is...", COLOR_YELLOW))
    
    # ---------------------------------------------------------------------------
    # METHOD 1: IWishlistService/GetWishlist (undocumented but works, separate server)
    # This hits api.steampowered.com which is NOT the store — no store rate limits.
    # ---------------------------------------------------------------------------
    print(c_str("Fetching wishlist via Steam Web API (IWishlistService)...", COLOR_CYAN))
    api_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={steam_id}"
    
    try:
        data = fetch_json(api_url)
        if data and "response" in data:
            items = data["response"].get("items", [])
            if items:
                wishlist_items = []
                for item in items:
                    app_id = str(item.get("appid", ""))
                    if app_id:
                        # Use placeholder name — real name will be fetched during price lookup
                        wishlist_items.append((app_id, None))
                
                print(c_str(f"  Found {len(wishlist_items)} apps on wishlist.", COLOR_GREEN))
                return wishlist_items
            else:
                print(c_str("Wishlist is empty or profile is private.", COLOR_YELLOW))
                return []
    except Exception as e:
        print(c_str(f"  IWishlistService failed: {e}", COLOR_YELLOW))
    
    # ---------------------------------------------------------------------------
    # METHOD 2: Fall back to a local wishlist.txt file
    # ---------------------------------------------------------------------------
    import os
    wishlist_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wishlist.txt")
    if os.path.exists(wishlist_file):
        print(c_str(f"Loading wishlist from {wishlist_file}...", COLOR_CYAN))
        wishlist_items = []
        with open(wishlist_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Support formats: "appid" or "appid,Game Name"
                if "," in line:
                    parts = line.split(",", 1)
                    wishlist_items.append((parts[0].strip(), parts[1].strip()))
                else:
                    wishlist_items.append((line, f"App {line}"))
        if wishlist_items:
            return wishlist_items
    
    # ---------------------------------------------------------------------------
    # METHOD 3: Legacy store endpoint (wishlistdata) — often broken/deprecated
    # ---------------------------------------------------------------------------
    print(c_str("Trying legacy store wishlistdata endpoint...", COLOR_CYAN))
    is_numeric = bool(re.match(r"^\d+$", steam_id))
    path_type = "profiles" if is_numeric else "id"
    
    wishlist_items = []
    page = 0
    while True:
        url = f"https://store.steampowered.com/wishlist/{path_type}/{steam_id}/wishlistdata/?p={page}"
        try:
            data = fetch_json(url)
            if not data or isinstance(data, list) or not isinstance(data, dict):
                break
            page_items = []
            for app_id, details in data.items():
                name = details.get("name", f"App {app_id}")
                page_items.append((app_id, name))
            wishlist_items.extend(page_items)
            if len(page_items) < 50:
                break
            page += 1
            time.sleep(0.5)
        except Exception as e:
            if page == 0:
                print(c_str(f"  Legacy endpoint also failed: {e}", COLOR_RED))
                print(c_str("  All methods exhausted. You can create a 'wishlist.txt' file", COLOR_YELLOW))
                print(c_str("  with one App ID per line (find IDs on store.steampowered.com/app/XXXX).", COLOR_YELLOW))
            break
    return wishlist_items



def get_regional_price(app_id, region_code):
    """Fetches price for a specific game and region from Steam appdetails API.
    Returns (price, game_name) tuple. game_name may be None if not available."""
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc={region_code}&filters=price_overview,basic"
    
    # Respect rate-limiting
    time.sleep(STEAM_API_DELAY)
    
    try:
        response = fetch_json(url)
        if not response or str(app_id) not in response:
            return None, None
            
        app_data = response[str(app_id)]
        if not app_data.get("success"):
            return None, None
            
        data = app_data.get("data")
        if not data or "price_overview" not in data:
            return None, data.get("name") if data else None
            
        game_name = data.get("name")
        price_overview = data["price_overview"]
        final_price_cents = price_overview.get("final")
        if final_price_cents is None:
            return None, game_name
            
        return final_price_cents / 100.0, game_name
    except Exception:
        # Ignore errors for specific games (e.g. invalid appid, removed from store)
        return None, None

# ==============================================================================
# MAIN EXECUTION FLOW
# ==============================================================================
def main():
    print(c_str("===============================================", COLOR_CYAN))
    print(c_str("      STEAM WISHLIST PRICE COMPARER (PLN)     ", COLOR_BOLD, COLOR_CYAN))
    print(c_str("===============================================", COLOR_CYAN))
    
    # 1. Fetch Exchange Rates
    usd_rate, eur_rate = get_exchange_rates()
    print()
    
    # 2. Get Steam ID
    if len(sys.argv) > 1:
        steam_id = sys.argv[1].strip()
    else:
        try:
            steam_id = input("Enter Steam ID (64-bit community ID or custom URL name): ").strip()
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)
            
    if not steam_id:
        print(c_str("Steam ID cannot be empty.", COLOR_RED))
        sys.exit(1)
        
    # Clean up Steam ID if they pasted a full URL or it contains trailing slashes
    if steam_id.endswith("/"):
        steam_id = steam_id[:-1]
    
    if "steamcommunity.com/profiles/" in steam_id:
        steam_id = steam_id.split("steamcommunity.com/profiles/")[-1]
    elif "steamcommunity.com/id/" in steam_id:
        steam_id = steam_id.split("steamcommunity.com/id/")[-1]
    elif "store.steampowered.com/wishlist/profiles/" in steam_id:
        steam_id = steam_id.split("store.steampowered.com/wishlist/profiles/")[-1]
    elif "store.steampowered.com/wishlist/id/" in steam_id:
        steam_id = steam_id.split("store.steampowered.com/wishlist/id/")[-1]
        
    # 3. Fetch Wishlist
    wishlist = get_wishlist(steam_id)
    if not wishlist:
        print(c_str("No games to process. Exiting.", COLOR_RED))
        sys.exit(0)
        
    total_games = len(wishlist)
    print(f"Found {c_str(str(total_games), COLOR_GREEN)} games on your wishlist.")
    
    # Apply limit if configured
    if LIMIT_GAMES is not None:
        wishlist = wishlist[:LIMIT_GAMES]
        print(c_str(f"Limiting analysis to the first {len(wishlist)} games (LIMIT_GAMES is set).", COLOR_YELLOW))
        total_games = len(wishlist)
        
    # Calculate estimated duration
    # 3 API calls per game * STEAM_API_DELAY
    est_seconds = total_games * 3 * STEAM_API_DELAY
    est_minutes = est_seconds / 60
    print(f"Estimated time to fetch prices: {c_str(f'{est_seconds:.1f} seconds', COLOR_YELLOW)} ({c_str(f'{est_minutes:.1f} minutes', COLOR_YELLOW)})")
    print(c_str("Please wait, querying Steam API...", COLOR_CYAN))
    print()
    
    fair_games = []
    expensive_games = []
    skipped_games = []
    
    # 4. Fetch Prices and Compare
    for idx, (app_id, name) in enumerate(wishlist, start=1):
        display_name = name or f"App {app_id}"
        print(f"[{idx}/{total_games}] {app_id}: ", end="", flush=True)
        
        # PLN price (first call — also grabs the real game name)
        price_pln, fetched_name = get_regional_price(app_id, "pl")
        if fetched_name:
            # Sanitize name for console encoding (strip chars like ™ that break CP1252)
            try:
                fetched_name.encode(sys.stdout.encoding or "utf-8")
            except (UnicodeEncodeError, LookupError):
                fetched_name = fetched_name.encode("ascii", errors="replace").decode("ascii")
            name = fetched_name
            display_name = name
        print(f"{c_str(display_name, COLOR_BOLD)} ", end="", flush=True)
        if price_pln is None:
            print(c_str("SKIPPED (No price/Free/Unreleased)", COLOR_YELLOW))
            skipped_games.append(display_name)
            continue
            
        # USD price
        price_usd, _ = get_regional_price(app_id, "us")
        if price_usd is None:
            print(c_str(" SKIPPED (USD price missing)", COLOR_YELLOW))
            skipped_games.append(display_name)
            continue
            
        # EUR price
        price_eur, _ = get_regional_price(app_id, "de")
        if price_eur is None:
            print(c_str(" SKIPPED (EUR price missing)", COLOR_YELLOW))
            skipped_games.append(display_name)
            continue
            
        # Convert prices
        converted_usd = price_usd * usd_rate
        converted_eur = price_eur * eur_rate
        
        # Calculate differences (negative means PLN is cheaper)
        diff_usd = price_pln - converted_usd
        diff_eur = price_pln - converted_eur
        
        game_data = {
            "name": display_name,
            "app_id": app_id,
            "pln": price_pln,
            "usd": price_usd,
            "usd_pln": converted_usd,
            "diff_usd": diff_usd,
            "eur": price_eur,
            "eur_pln": converted_eur,
            "diff_eur": diff_eur
        }
        
        # Comparison logic
        # Is PLN equal to or cheaper than BOTH USD and EUR?
        if price_pln <= converted_usd and price_pln <= converted_eur:
            print(c_str(" FAIR PRICE! [OK]", COLOR_GREEN, COLOR_BOLD))
            fair_games.append(game_data)
        else:
            print(c_str(" EXPENSIVE! [X]", COLOR_RED))
            expensive_games.append(game_data)
            
    print("\n" + c_str("===============================================", COLOR_CYAN))
    print(c_str("                    RESULTS                    ", COLOR_BOLD, COLOR_CYAN))
    print(c_str("===============================================", COLOR_CYAN))
    
    # Display Fair Price Games
    if fair_games:
        print(c_str(f"\n{COLOR_GREEN}[FAIR] FAIR PRICE GAMES (PLN is cheaper/equal in Poland):{COLOR_RESET}"))
        print(f"{'Game Name':<35} | {'PLN Price':<11} | {'USD (in PLN)':<14} | {'EUR (in PLN)':<14} | {'Savings':<10}")
        print("-" * 96)
        for g in fair_games:
            # Savings relative to the cheaper of USD or EUR
            cheaper_alt = min(g["usd_pln"], g["eur_pln"])
            savings = cheaper_alt - g["pln"]
            savings_str = f"{savings:.2f} PLN" if savings > 0.01 else "0.00 PLN"
            
            print(f"{g['name'][:34]:<35} | {g['pln']:8.2f} PLN | {g['usd_pln']:10.2f} PLN | {g['eur_pln']:10.2f} PLN | {c_str(savings_str, COLOR_GREEN)}")
    else:
        print(c_str("\nNo games on your wishlist have a cheaper/equal price in PLN compared to USD and EUR.", COLOR_YELLOW))
        
    # Display More Expensive Games
    if expensive_games:
        print(c_str(f"\n{COLOR_RED}[EXPENSIVE] EXPENSIVE GAMES (PLN is more expensive than USD or EUR):{COLOR_RESET}"))
        print(f"{'Game Name':<35} | {'PLN Price':<11} | {'USD (in PLN)':<14} | {'EUR (in PLN)':<14} | {'Loss/Overpay':<12}")
        print("-" * 98)
        for g in expensive_games:
            # Overpay relative to the cheaper of USD or EUR
            cheaper_alt = min(g["usd_pln"], g["eur_pln"])
            overpay = g["pln"] - cheaper_alt
            overpay_str = f"+{overpay:.2f} PLN"
            
            # Show which conversion is cheaper
            cheapest_curr = "USD" if g["usd_pln"] < g["eur_pln"] else "EUR"
            
            print(f"{g['name'][:34]:<35} | {g['pln']:8.2f} PLN | {g['usd_pln']:10.2f} PLN | {g['eur_pln']:10.2f} PLN | {c_str(f'{overpay_str} ({cheapest_curr})', COLOR_RED)}")
            
    # Summary Info
    print("\n" + c_str("===============================================", COLOR_CYAN))
    print(f"Total Wishlist Checked: {total_games}")
    print(f"Fair Games: {c_str(str(len(fair_games)), COLOR_GREEN)}")
    print(f"Expensive Games: {c_str(str(len(expensive_games)), COLOR_RED)}")
    print(f"Skipped/Free/Unreleased: {len(skipped_games)}")
    print(c_str("===============================================", COLOR_CYAN))

if __name__ == "__main__":
    # Ensure raw output isn't buffered (helps status updates display immediately)
    sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
    main()

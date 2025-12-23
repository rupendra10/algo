import datetime
from datetime import date, timedelta
import requests

# Static Calendar of Major Economic Events (RBI, Fed, Budget)
# These are harder to fetch programmatically from a single free API.
# We maintain them for 2025-2026.
MAJOR_ECONOMIC_EVENTS = {
    "2025-02-01": "Union Budget FY 2025-26 (EXTREME VOLATILITY)",
    "2025-04-09": "RBI MPC Policy Announcement",
    "2025-06-06": "RBI MPC Policy Announcement",
    "2025-08-06": "RBI MPC Policy Announcement",
    "2025-10-01": "RBI MPC Policy Announcement",
    "2025-12-05": "RBI MPC Policy Announcement",
    "2026-02-06": "RBI MPC Policy Announcement",
    
    "2025-01-29": "US FOMC (Fed) Rate Decision",
    "2025-03-19": "US FOMC (Fed) Rate Decision",
    "2025-05-07": "US FOMC (Fed) Rate Decision",
    "2025-06-18": "US FOMC (Fed) Rate Decision",
    "2025-07-30": "US FOMC (Fed) Rate Decision",
    "2025-09-17": "US FOMC (Fed) Rate Decision",
    "2025-10-29": "US FOMC (Fed) Rate Decision",
    "2025-12-10": "US FOMC (Fed) Rate Decision",
}

UPSTOX_HOLIDAY_URL = "https://api.upstox.com/v2/market/holidays"

def fetch_dynamic_holidays():
    """
    Fetches market holidays directly from Upstox API.
    Returns: List of date strings in 'YYYY-MM-DD'
    """
    try:
        response = requests.get(UPSTOX_HOLIDAY_URL, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                holidays = []
                for entry in data.get('data', []):
                    # entry['holiday_date'] is usually 'YYYY-MM-DD'
                    h_date = entry.get('holiday_date')
                    if h_date:
                        holidays.append(h_date)
                return holidays
    except Exception as e:
        pass
    return []

def get_upcoming_warnings(lookahead_days=5):
    """
    Checks for upcoming holidays (from API) and major economic events (static calendar).
    """
    today = date.today()
    warnings = []
    
    # 1. Dynamic Holidays (Upstox API)
    dynamic_holidays = fetch_dynamic_holidays()
    for h_str in dynamic_holidays:
        try:
            h_date = datetime.datetime.strptime(h_str, "%Y-%m-%d").date()
            if today <= h_date <= (today + timedelta(days=lookahead_days)):
                diff = (h_date - today).days
                day_text = "TODAY" if diff == 0 else f"in {diff} days"
                warnings.append(f"MARKET HOLIDAY: {h_str} is {day_text}. Markets will be CLOSED.")
        except:
            continue

    # 2. Economic Events (Curated Calendar)
    for e_str, desc in MAJOR_ECONOMIC_EVENTS.items():
        try:
            e_date = datetime.datetime.strptime(e_str, "%Y-%m-%d").date()
            if today <= e_date <= (today + timedelta(days=lookahead_days)):
                diff = (e_date - today).days
                day_text = "TODAY" if diff == 0 else f"in {diff} days"
                warnings.append(f"MAJOR EVENT: {desc} ({e_str}) is {day_text}. Expect Gaps or Volatility.")
        except:
            continue
            
    return warnings

def print_event_summary():
    """
    Prints a warning summary to console.
    """
    warnings = get_upcoming_warnings()
    if warnings:
        print("\n" + "!"*60)
        print("  STRATEGY ALERT: UPCOMING MARKET EVENTS/HOLIDAYS")
        print("!"*60)
        for w in warnings:
            print(f"  - {w}")
        print("!"*60 + "\n")
    else:
        print("\n[Event Monitor] No major events or holidays in the next 5 days.\n")

if __name__ == "__main__":
    print_event_summary()

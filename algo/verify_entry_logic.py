import sys
import os
from datetime import datetime, date, timedelta

# Add current dir to path for imports
sys.path.append(os.getcwd())

import config
from instrument_manager import InstrumentMaster
from strategy import NiftyStrategy

def test_entry_logic():
    print("=== Testing Strict Entry Timing and Selection ===")
    
    master = InstrumentMaster()
    # Mock some expiry dates for testing
    # Assuming today is Sep 26 (Thu, Monthly Expiry)
    # Expiries: 
    # Sep: 5, 12, 19, 26
    # Oct: 3, 10, 17, 24, 31
    # Nov: 7, 14, 21, 28
    # Dec: 5, 12, 19, 26
    mock_dates = [
        date(2024, 9, 26),
        date(2024, 10, 3), date(2024, 10, 31),
        date(2024, 11, 7), date(2024, 11, 28),
        date(2024, 12, 5), date(2024, 12, 26)
    ]
    
    # 1. Test Expiry Day Detection
    print("\n1. Testing Monthly Expiry Detection:")
    import pandas as pd
    master.df = pd.DataFrame([
        {'name': 'NIFTY', 'instrument_type': 'PE', 'expiry_dt': d} for d in mock_dates
    ])
    
    # Mocking date.today() is hard, but we can call the internal logic with a mock date
    def is_monthly_expiry_on_date(test_date):
        current_month_expiries = [d for d in mock_dates if d.year == test_date.year and d.month == test_date.month]
        last_of_month = current_month_expiries[-1]
        return test_date == last_of_month

    print(f"Is Sep 26 Monthly Expiry? {is_monthly_expiry_on_date(date(2024, 9, 26))}") # True
    print(f"Is Oct 3 Monthly Expiry? {is_monthly_expiry_on_date(date(2024, 10, 3))}") # False
    
    # 2. Test Special Expiry Selection
    print("\n2. Testing Special Contract Selection (Next-Weekly, Next-Next-Monthly):")
    # If today is Sep 26: 
    # Next Month = Oct. First Weekly = Oct 3.
    # Next-Next Month = Nov. Monthly = Nov 28.
    
    def get_special_expiries_mock(test_date):
        next_month = test_date.month + 1
        next_year = test_date.year
        if next_month > 12: next_month = 1; next_year += 1
        
        nn_month = next_month + 1
        nn_year = next_year
        if nn_month > 12: nn_month = 1; nn_year += 1
        
        next_month_expiries = [d for d in mock_dates if d.year == next_year and d.month == next_month]
        weekly_target = next_month_expiries[0]
        
        nn_month_expiries = [d for d in mock_dates if d.year == nn_year and d.month == nn_month]
        monthly_target = nn_month_expiries[-1]
        
        return weekly_target, monthly_target

    w, m = get_special_expiries_mock(date(2024, 9, 26))
    print(f"Entry Day: 2024-09-26")
    print(f"Target Weekly (Next Month 1st): {w}")   # Should be 2024-10-03
    print(f"Target Monthly (Next-Next Month): {m}") # Should be 2024-11-28

    # 3. Time Check Simulation
    print("\n3. Timing Logic Simulation:")
    config.STRICT_MONTHLY_EXPIRY_ENTRY = True
    config.ENTRY_TIME_HHMM = "15:15"
    
    def can_enter_simulation(is_expiry_today, current_time_str):
        if not is_expiry_today: return False, "Not Monthly Expiry"
        if current_time_str < config.ENTRY_TIME_HHMM: return False, f"Before {config.ENTRY_TIME_HHMM}"
        return True, "ENTER NOW"

    print(f"Sep 26, 14:00 -> {can_enter_simulation(True, '14:00')}")
    print(f"Sep 25, 15:30 -> {can_enter_simulation(False, '15:30')}")
    print(f"Sep 26, 15:20 -> {can_enter_simulation(True, '15:20')}")

if __name__ == "__main__":
    test_entry_logic()

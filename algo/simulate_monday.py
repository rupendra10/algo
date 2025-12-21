import sys
import os
from datetime import datetime, timedelta

# Add current dir to path for imports
sys.path.append(os.getcwd())

import config
from strategy import NiftyStrategy

def run_monday_simulation():
    print("=== MONDAY ROLLOVER SIMULATION ===")
    
    # 1. Force 'today' to be a Monday (e.g., 2025-12-22)
    fake_today = datetime(2025, 12, 22, 10, 0, 0)
    print(f"Simulating Date: {fake_today.strftime('%A, %Y-%m-%d %H:%M:%S')}")

    strategy = NiftyStrategy()
    
    # 2. Setup an existing Weekly Position expiring tomorrow (Tuesday)
    # Expiry in years: 1 day = 1/365 = 0.0027
    strategy.weekly_position = {
        'instrument_key': 'NSE_FO|NIFTY_EXP_TOMORROW',
        'strike': 24100,
        'expiry': 1/365.0, # Expiring tomorrow
        'delta': 0.5,
        'iv': 0.15
    }
    strategy.monthly_position = {
        'instrument_key': 'NSE_FO|NIFTY_MONTHLY_HEDGE',
        'strike': 24000,
        'expiry': 30/365.0,
        'delta': 0.5,
        'iv': 0.15
    }

    print(f"Existing Weekly Leg: {strategy.weekly_position['instrument_key']} (Expiry in {strategy.weekly_position['expiry']:.4f} years)")

    # 3. Define Callback to capture orders
    def mock_order_callback(key, qty, side, tag):
        print(f"--- [ORDER SENT] {side} {qty} {key} | Reason: {tag} ---")

    # 4. Trigger Rollover Check (This logic is usually in run_strategy.py)
    # We simulate the logic inside run_strategy.py:133-149
    print("\nChecking for Rollover...")
    if fake_today.weekday() == 0: # It is Monday
        if strategy.weekly_position:
            # Check if expiring soon (<= 1 day)
            current_pos_expiry_date = (fake_today + timedelta(days=strategy.weekly_position['expiry'] * 365)).date()
            if current_pos_expiry_date <= (fake_today + timedelta(days=1)).date():
                print(f"!!! MONDAY DETECTED: Weekly leg expires on {current_pos_expiry_date}. Rolling over...")
                
                # Close Current
                mock_order_callback(strategy.weekly_position['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'MONDAY_CLOSE')
                strategy.weekly_position = None
    
    # 5. Check Re-entry (Simulated Entry Logic)
    if not strategy.weekly_position:
        print("Weekly position is empty. Re-entering next weekly ATM...")
        # Mock fresh chain
        mock_weekly_chain = [{
            'strike': 24150, 
            'time_to_expiry': 8/365.0, # Fresh weekly (next Thu/Tue)
            'iv': 0.15, 
            'instrument_key': 'NSE_FO|NIFTY_NEW_WEEKLY', 
            'calculated_delta': 0.5
        }]
        strategy.adjust_weekly_leg(24150, mock_weekly_chain, mock_order_callback)

    print("\nSimulation Complete.")
    if strategy.weekly_position:
        print(f"Final Weekly Position: {strategy.weekly_position['strike']} (Key: {strategy.weekly_position['instrument_key']})")

if __name__ == "__main__":
    run_monday_simulation()

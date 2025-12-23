import sys
import os
from datetime import datetime, timedelta

# Add current dir to path for imports
sys.path.append(os.getcwd())

import config
from strategy import NiftyStrategy

def test_adjustments():
    print("Starting Strategy Logic Verification...")
    
    # Mock Config overrides for predictable testing
    config.WEEKLY_ADJ_TRIGGER_DELTA = 0.80
    config.WEEKLY_ADJ_TRIGGER_DELTA_LOW = 0.10
    config.MONTHLY_ADJ_TRIGGER_DELTA = 0.90
    config.MONTHLY_ADJ_TRIGGER_DELTA_LOW = 0.10
    config.ORDER_QUANTITY = 75

    strategy = NiftyStrategy(risk_free_rate=0.07)
    
    # Mock position
    strategy.weekly_position = {
        'instrument_key': 'NSE_FO|12345',
        'strike': 24000,
        'expiry': 0.01,
        'delta': 0.5,
        'iv': 0.15
    }
    strategy.monthly_position = {
        'instrument_key': 'NSE_FO|67890',
        'strike': 24000,
        'expiry': 0.08,
        'delta': 0.5,
        'iv': 0.15
    }

    def mock_order_callback(key, qty, side, tag):
        print(f"  [ORDER] {side} {qty} {key} | Tag: {tag}")

    # Case 1: Weekly Delta Rise (Market Fall)
    print("\nCase 1: Weekly Delta Rise (0.85)")
    strategy.weekly_position['delta'] = 0.85
    # Mock chains
    weekly_chain = [{'strike': 23500, 'time_to_expiry': 0.01, 'iv': 0.15, 'instrument_key': 'NEW_WEEKLY', 'calculated_delta': 0.5}]
    monthly_chain = [{'strike': 23500, 'time_to_expiry': 0.08, 'iv': 0.15, 'instrument_key': 'NEW_MONTHLY', 'calculated_delta': 0.5}]
    strategy.check_adjustments(23500, weekly_chain, monthly_chain, mock_order_callback)
    
    # Case 2: Weekly Delta Fall (Market Rise)
    print("\nCase 2: Weekly Delta Fall (0.05)")
    strategy.weekly_position = {'instrument_key': 'W1', 'delta': 0.05, 'strike': 24000, 'expiry': 0.01, 'iv': 0.15}
    strategy.check_adjustments(24500, weekly_chain, monthly_chain, mock_order_callback)

    # Case 3: Monthly Delta Rise (Deep ITM)
    print("\nCase 3: Monthly Delta Rise (0.95)")
    strategy.weekly_position = {'instrument_key': 'W1', 'delta': 0.5, 'strike': 24000, 'expiry': 0.01, 'iv': 0.15}
    strategy.monthly_position = {'instrument_key': 'M1', 'delta': 0.95, 'strike': 24000, 'expiry': 0.08, 'iv': 0.15}
    # Monthly fall target 0.5
    strategy.check_adjustments(23000, weekly_chain, monthly_chain, mock_order_callback)

    # Case 4: Monthly Delta Fall (Market Rise)
    print("\nCase 4: Monthly Delta Fall (0.05)")
    strategy.monthly_position = {'instrument_key': 'M2', 'delta': 0.05, 'strike': 24000, 'expiry': 0.08, 'iv': 0.15}
    # Monthly rise target 0.35
    monthly_chain_rise = [{'strike': 25000, 'time_to_expiry': 0.08, 'iv': 0.15, 'instrument_key': 'M_HEDGE', 'calculated_delta': 0.35}]
    strategy.check_adjustments(25000, weekly_chain, monthly_chain_rise, mock_order_callback)

if __name__ == "__main__":
    test_adjustments()

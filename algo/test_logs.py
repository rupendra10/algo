from strategy import NiftyStrategy
import config
from datetime import date

def test_logs():
    s = NiftyStrategy()
    
    # Mock data
    weekly_chain = [{
        'strike': 25950,
        'time_to_expiry': 0.05,
        'expiry_dt': date(2025, 12, 23),
        'iv': 0.15,
        'instrument_key': 'NSE_FO|57004'
    }]
    
    monthly_chain = [{
        'strike': 26150,
        'time_to_expiry': 0.1,
        'expiry_dt': date(2026, 1, 27),
        'iv': 0.15,
        'instrument_key': 'NSE_FO|58808'
    }]
    
    def mock_order(key, qty, side, tag):
        print(f"TRADING: {side} {qty} Qty | Key: {key} | Tag: {tag}")
        
    s.enter_strategy(25966.4, weekly_chain, monthly_chain, order_callback=mock_order)

if __name__ == "__main__":
    test_logs()

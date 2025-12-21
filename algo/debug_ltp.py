from upstox_wrapper import UpstoxWrapper
import config
import os

def debug_ltp():
    api = UpstoxWrapper()
    spot_key = config.SPOT_INSTRUMENT_KEY
    print(f"Fetching LTP for: {spot_key}")
    
    try:
        # Use the wrapper method which now handles the key mapping
        price = api.get_spot_price(spot_key)
        print(f"Wrapper returned Spot Price: {price}")
        
        if price:
            print("FIX CONFIRMED!")
        else:
            print("FAILED to get price through wrapper.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_ltp()

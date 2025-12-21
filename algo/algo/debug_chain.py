from upstox_wrapper import UpstoxWrapper
from instrument_manager import InstrumentMaster

def debug_keys():
    api = UpstoxWrapper()
    master = InstrumentMaster()
    master.load_master()
    
    weekly_expiry, _ = master.get_target_expiries('NIFTY')
    weekly_opts = master.get_option_symbols('NIFTY', weekly_expiry, 'PE')
    
    weekly_symbols = weekly_opts['instrument_key'].tolist()
    
    if weekly_symbols:
        sub_symbols = weekly_symbols[:5]
        print(f"Requested Keys (IDs): {sub_symbols}")
        
        quotes = api.get_option_chain_quotes(sub_symbols)
        print(f"Returned Keys in quotes dictionary: {list(quotes.keys())}")
        
        matches = 0
        for s in sub_symbols:
            if s in quotes:
                matches += 1
        
        print(f"MATCHES: {matches} / {len(sub_symbols)}")
        if matches == len(sub_symbols):
            print("FIX VERIFIED! Lookups will now work.")

if __name__ == "__main__":
    debug_keys()

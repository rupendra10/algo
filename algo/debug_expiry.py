import pandas as pd
import json
import os

json_path = './data/NSE_FO.json'
if os.path.exists(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    
    nifty_opts = df[(df['name'] == 'NIFTY') & (df['instrument_type'].isin(['CE', 'PE']))]
    print("NIFTY Options expiry values (raw):")
    print(nifty_opts['expiry'].dropna().unique()[:10])
    
    # Try parsing
    if 'expiry' in nifty_opts.columns:
        first_expiry = nifty_opts['expiry'].dropna().iloc[0] if not nifty_opts['expiry'].dropna().empty else None
        print(f"First expiry raw: {first_expiry} type: {type(first_expiry)}")
        
        try:
            if isinstance(first_expiry, str) and first_expiry.isdigit():
                 parsed = pd.to_datetime(int(first_expiry), unit='ms').date()
                 print(f"Parsed as ms: {parsed}")
            elif isinstance(first_expiry, (int, float)):
                 parsed = pd.to_datetime(first_expiry, unit='ms').date()
                 print(f"Parsed as ms: {parsed}")
            else:
                 parsed = pd.to_datetime(first_expiry).date()
                 print(f"Parsed as generic: {parsed}")
        except Exception as e:
            print(f"Parse error: {e}")

else:
    print(f"File {json_path} not found.")

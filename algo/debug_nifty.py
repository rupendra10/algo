import pandas as pd
import json
import os

json_path = './data/NSE_FO.json'
if os.path.exists(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    
    nifty_df = df[df['name'].str.contains('NIFTY', na=False)]
    print("Unique names containing NIFTY:", nifty_df['name'].unique())
    print("Unique instrument_types for NIFTY:", nifty_df['instrument_type'].unique())
    print("Sample NIFTY rows:")
    print(nifty_df.head())
    
    # Check for exact NIFTY
    exact_nifty = df[df['name'] == 'NIFTY']
    if not exact_nifty.empty:
        print("Found EXACT NIFTY. Instrument types:", exact_nifty['instrument_type'].unique())
    else:
        print("Exact 'NIFTY' not found in name column.")
else:
    print(f"File {json_path} not found.")

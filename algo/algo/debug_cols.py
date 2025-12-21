import pandas as pd
import json
import os

json_path = './data/NSE_FO.json'
if os.path.exists(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    
    nifty_opts = df[(df['name'] == 'NIFTY') & (df['instrument_type'].isin(['CE', 'PE']))]
    print("Columns available for NIFTY options:")
    print(nifty_opts.columns.tolist())
    print("\nSample row:")
    print(nifty_opts.iloc[0])
else:
    print(f"File {json_path} not found.")

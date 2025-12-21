import pandas as pd
import json
import os

json_path = './data/NSE_FO.json'
if os.path.exists(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    print("Columns:", df.columns.tolist())
    print("First 5 rows:")
    print(df.head())
    if 'name' in df.columns:
        print("Unique names:", df['name'].unique()[:20])
    if 'instrument_type' in df.columns:
        print("Unique instrument_types:", df['instrument_type'].unique())
else:
    print(f"File {json_path} not found.")

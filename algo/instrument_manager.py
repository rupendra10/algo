import pandas as pd
import gzip
import shutil
import requests
import os
import json
from datetime import datetime, date
import config

# NEW JSON URL for NSE FO
MASTER_URL = config.INSTRUMENT_MASTER_URL

class InstrumentMaster:
    def __init__(self, data_dir=config.DATA_DIR):
        self.data_dir = data_dir
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        self.json_path = os.path.join(data_dir, 'NSE_FO.json')
        self.df = None

    def download_master(self):
        """Downloads and extracts the NSE FO instrument master file."""
        print(f"Downloading Instrument Master from {MASTER_URL} ...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(MASTER_URL, stream=True, headers=headers)
            if response.status_code != 200:
                print(f"Error: Failed to download master. Status code: {response.status_code}")
                return

            gz_path = self.json_path + ".gz"
            with open(gz_path, 'wb') as f:
                f.write(response.content)
            
            with gzip.open(gz_path, 'rb') as f_in:
                with open(self.json_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            print("Download and extraction complete.")
        except Exception as e:
            print(f"Error downloading master: {e}")

    def load_master(self):
        if not os.path.exists(self.json_path):
            self.download_master()
        
        try:
            # Parse JSON
            with open(self.json_path, 'r') as f:
                data = json.load(f)
            
            self.df = pd.DataFrame(data)
            
            # Normalize Columns if needed
            # Upstox JSON usually has keys like 'instrument_key', 'expiry', etc.
            
            if 'expiry' in self.df.columns:
                 self.df['expiry_dt'] = pd.to_datetime(self.df['expiry'], unit='ms', errors='coerce').dt.date
                 
                 # If unit='ms' failed (all NaT), try generic parsing
                 if self.df['expiry_dt'].isnull().all():
                     self.df['expiry_dt'] = pd.to_datetime(self.df['expiry'], errors='coerce').dt.date
                     
        except Exception as e:
            print(f"Error loading master JSON: {e}")

    def get_expiry_dates(self, underlying_symbol='NIFTY'):
        if self.df is None:
            self.load_master()
            
        if self.df is None:
            print("Display Warning: Master Dataframe is None. Cannot find expiries.")
            return []
        
        # Filter Logic (JSON/DF structure might differ slightly, but assuming fields exist)
        # name might be 'name' or 'symbol'
        # instrument_type might be 'instrument_type'
        
        # Safe check for columns
        today = date.today()
        mask = (self.df['name'] == underlying_symbol) & \
               (self.df['instrument_type'].isin(['CE', 'PE']))
        
        subset = self.df[mask]
        if subset.empty:
            return []
            
        unique_expiries = sorted(subset['expiry_dt'].unique())
        future_expiries = [d for d in unique_expiries if d >= today]
        return future_expiries

    def get_target_expiries(self, underlying_symbol='NIFTY'):
        expiries = self.get_expiry_dates(underlying_symbol)
        
        if not expiries:
            return None, None
            
        weekly = expiries[0]
        
        target_month = weekly.month + 1
        target_year = weekly.year
        if target_month > 12:
            target_month = 1
            target_year += 1
            
        next_month_expiries = [d for d in expiries if d.year == target_year and d.month == target_month]
        
        if next_month_expiries:
            monthly = next_month_expiries[-1]
        else:
            monthly = expiries[-1]
            
        return weekly, monthly

    def get_option_symbols(self, underlying_symbol='NIFTY', expiry_date=None, option_type='PE'):
        if self.df is None:
            self.load_master()
        
        mask = (self.df['name'] == underlying_symbol) & \
               (self.df['instrument_type'].isin(['CE', 'PE']))
               
        if expiry_date:
            mask = mask & (self.df['expiry_dt'] == expiry_date)
            
        if option_type:
             mask = mask & (self.df['instrument_type'] == option_type)
             
        filtered = self.df[mask].copy()
        
        if 'strike' not in filtered.columns and 'strike_price' in filtered.columns:
            filtered['strike'] = filtered['strike_price']
            
        cols = ['instrument_key', 'trading_symbol', 'strike', 'expiry_dt']
        # Fallback for 'tradingsymbol' vs 'trading_symbol'
        if 'trading_symbol' not in filtered.columns and 'tradingsymbol' in filtered.columns:
            filtered['trading_symbol'] = filtered['tradingsymbol']
            
        return filtered[cols]

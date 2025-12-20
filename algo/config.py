import os

# ==========================================
# GLOABL TRADING CONFIGURATION
# ==========================================

# Select Mode: 'PAPER', 'LIVE', 'BACKTEST'
# 'PAPER': Executes in simulation mode (prints logs, no real money).
# 'LIVE': Executes REAL orders on Upstox.
# 'BACKTEST': Replays historical data from CSV files.
TRADING_MODE = 'PAPER' 

# ==========================================
# BACKTEST CONFIGURATION
# ==========================================
HISTORICAL_DATA_DIR = './historical_data'
BACKTEST_START_DATE = '2025-10-01'
BACKTEST_END_DATE = '2025-10-31'
# Expected CSV Filenames: 'nifty_spot.csv', 'nifty_options.csv'

# ==========================================
# API CREDENTIALS
# ==========================================
# By default, reads from Environment Variables.
# You can hardcode here if absolutely necessary/safe (Not Recommended).
UPSTOX_ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN', '')

# ==========================================
# STRATEGY PARAMETERS
# ==========================================
UNDERLYING_NAME = 'NIFTY'
SPOT_INSTRUMENT_KEY = 'NSE_INDEX|Nifty 50'
RISK_FREE_RATE = 0.07 # 7% used for Greeks

# ENTRY LOGIC
ENTRY_WEEKLY_DELTA_TARGET = 0.50  # Sell Weekly ATM
ENTRY_MONTHLY_DELTA_TARGET = 0.50 # Buy Monthly ATM (Hedge)

# ADJUSTMENT LOGIC - WEEKLY (SHORT LEG)
WEEKLY_ADJ_TRIGGER_DELTA = 0.80   # Roll if delta >= this (ITM)
WEEKLY_ROLL_TARGET_DELTA = 0.50   # Roll to this fresh Delta

# ADJUSTMENT LOGIC - MONTHLY (LONG LEG)
MONTHLY_ADJ_TRIGGER_DELTA = 0.90  # Roll if delta > this (Deep ITM)
MONTHLY_ROLL_TARGET_DELTA = 0.35  # Roll to this Delta (OTM Hedge)

# ==========================================
# EXECUTION SETTINGS
# ==========================================
POLL_INTERVAL_SECONDS = 5
ORDER_QUANTITY = 75 # 1 Lot for Nifty
ORDER_PRODUCT = 'D' # Delivery (D) or Intraday (I)
ORDER_VALIDITY = 'DAY'
ORDER_TAG_PREFIX = 'algo'

# ==========================================
# SYSTEM / PATHS
# ==========================================
DATA_DIR = './data'
INSTRUMENT_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

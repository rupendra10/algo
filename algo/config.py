import os
from dotenv import load_dotenv

# Load variables from .env file if it exists
load_dotenv()

# ==========================================
# GLOABL TRADING CONFIGURATION
# ==========================================

# Select Mode: 'PAPER', 'LIVE', 'BACKTEST'
# 'PAPER': Executes in simulation mode (prints logs, no real money).
# 'LIVE': Executes REAL orders on Upstox.
# 'BACKTEST': Replays historical data from CSV files.
TRADING_MODE = 'PAPER' 
ACTIVE_STRATEGIES = [  'WeeklyIronfly'] #CalendarPEWeekly, WeeklyIronfly

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
UPSTOX_API_KEY = os.getenv('UPSTOX_API_KEY', '')
UPSTOX_API_SECRET = os.getenv('UPSTOX_API_SECRET', '')
UPSTOX_REDIRECT_URI = os.getenv('UPSTOX_REDIRECT_URI', '') # Must match your Upstox App settings
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

# ENTRY TIMING
# If True, the algo will only enter new positions at 3:15 PM on Monthly Expiry Day.
STRICT_MONTHLY_EXPIRY_ENTRY = True
ENTRY_TIME_HHMM = "15:15"

# ADJUSTMENT LOGIC - WEEKLY (SHORT LEG)
WEEKLY_ADJ_TRIGGER_DELTA = 0.80       # Roll if delta >= this (ITM/Market Fall)
WEEKLY_ADJ_TRIGGER_DELTA_LOW = 0.10   # Roll if delta <= this (OTM/Market Rise)
WEEKLY_ROLL_TARGET_DELTA = 0.50       # Roll to this fresh Delta (ATM)

# ADJUSTMENT LOGIC - MONTHLY (LONG LEG)
MONTHLY_ADJ_TRIGGER_DELTA = 0.90      # Roll if delta >= this (Deep ITM/Market Fall)
MONTHLY_ADJ_TRIGGER_DELTA_LOW = 0.10  # Roll if delta <= this (OTM/Market Rise)
MONTHLY_ROLL_TARGET_DELTA_FALL = 0.50 # Roll to this Delta (ATM)
MONTHLY_ROLL_TARGET_DELTA_RISE = 0.35 # Roll to this Delta (OTM/Hedge)

# ==========================================
# WEEKLY IRONFLY (PUT BUTTERFLY) PARAMETERS
# ==========================================
IRONFLY_CAPITAL = 180000        # Potential total capital (used for SL/Target calc)
IRONFLY_SL_PERCENT = 0.01       # 1% adjustment/exit trigger
IRONFLY_TARGET_PERCENT = 0.03   # 3% target (can be adjusted to 5% for higher risk/reward)
IRONFLY_ENTRY_WEEKDAY = 1       # 1 = Tuesday
IRONFLY_ENTRY_TIME = "12:00"
IRONFLY_EXIT_TIME = "15:00"     # On Expiry Day

IRONFLY_LEG1_OFFSET = -50       # Buy Put strike relative to ATM
IRONFLY_LEG2_OFFSET = -250      # Sell 2 Puts strike relative to ATM
IRONFLY_LEG3_OFFSET = -450      # Buy Put strike (hedge) relative to ATM
IRONFLY_ADJ_INWARD_OFFSET = 100 # Internal offset from Leg 1 for Call Calendar

# ==========================================
# EXECUTION SETTINGS
# ==========================================
# --- RISK MANAGEMENT ---
MAX_LOSS_VALUE = 15000      # Exit all if loss exceeds this INR value. Set to 0 to DISABLE.
MAX_ALLOWED_VIX = 25.0     # Don't enter if VIX is above this (High Risk)
MIN_REQUIRED_CASH = 50000 # Minimum free cash buffer required to run
ROLLOVER_WEEKDAY = 0       # 0=Monday, 4=Friday (Friday is safer for gaps)
AUTO_EXIT_BEFORE_MONTHLY_EXPIRY_3PM = True # Exit everything at 3 PM ONE DAY BEFORE Monthly Expiry
POLL_INTERVAL_SECONDS = 30
ORDER_QUANTITY = 75 # 1 Lot for Nifty
ORDER_PRODUCT = 'D' # Delivery (D) or Intraday (I)
ORDER_VALIDITY = 'DAY'
ORDER_TAG_PREFIX = 'algo'

# ==========================================
# SYSTEM / PATHS
# ==========================================
DATA_DIR = './data'
INSTRUMENT_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

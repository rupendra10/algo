import os
import time
from datetime import datetime, date, timedelta
from upstox_wrapper import UpstoxWrapper
from instrument_manager import InstrumentMaster
from strategy import NiftyStrategy
import config
from greeks import calculate_delta
from utils import calculate_implied_volatility



def main():
    print("Starting Algo...")
    
    # 1. Setup
    api = UpstoxWrapper() # Reads token from Config/Env
    master = InstrumentMaster()
    master.load_master()
    
    strategy = NiftyStrategy(risk_free_rate=config.RISK_FREE_RATE)
    
    # 2. Identify Instruments
    # Auto-detect expiries using master
    print("Identifying Expiries...")
    weekly_expiry, monthly_expiry = master.get_target_expiries(config.UNDERLYING_NAME)
    
    if not weekly_expiry or not monthly_expiry:
        print("CRITICAL ERROR: Could not find valid expiries in Master.")
        return

    print(f"Target Expiries -> Weekly: {weekly_expiry} | Monthly: {monthly_expiry}")
    
    print(f"Fetching instruments...")
    
    weekly_opts = master.get_option_symbols(config.UNDERLYING_NAME, weekly_expiry, 'PE')
    monthly_opts = master.get_option_symbols(config.UNDERLYING_NAME, monthly_expiry, 'PE')
    
    print(f"Found {len(weekly_opts)} Weekly Puts and {len(monthly_opts)} Monthly Puts.")
    
    # 3. Main Loop (Simulation of 'tick' by polling)
    # In production, use WebSocket
    try:
        while True:
            # A. Get Spot Price
            # Need Nifty 50 Index Key. Usually 'NSE_INDEX|Nifty 50'
            spot_key = config.SPOT_INSTRUMENT_KEY
            spot_price = api.get_spot_price(spot_key)
            
            if not spot_price:
                print("Waiting for quote...")
                time.sleep(1)
                continue
            
            print(f"Spot: {spot_price}")
            
            # B. Build Option Chain Data for Logic
            # We need to fetch quotes for ALL strikes to calculate Delta effectively 
            # OR just fetch the ones around ATM. 
            # For robustness, we'll fetch a batch around ATM.
            
            # Utility to filter near ATM
            atm = round(spot_price / 50) * 50
            strikes_to_fetch = range(atm - 500, atm + 500, 50)
            
            # Filter our DF
            current_weekly_subset = weekly_opts[weekly_opts['strike'].isin(strikes_to_fetch)]
            current_monthly_subset = monthly_opts[monthly_opts['strike'].isin(strikes_to_fetch)]
            
            # Get Quotes
            # Collect keys
            keys = current_weekly_subset['instrument_key'].tolist() + current_monthly_subset['instrument_key'].tolist()
            quotes = api.get_option_chain_quotes(keys) # Returns dict key -> {last_price: ...}
            
            # Transform to format expected by Strategy: {'strike': K, 'iv': sigma, 'time_to_expiry': t}
            # Note: Upstox quotes might not have IV directly. We might need to calculating IV from Price?
            # Or assume simplified model where we just pass price and let strategy handle it?
            # Strategy expects 'iv'. 
            # CRITICAL: Real-time IV is hard. We will approximate or assume constant for MVP 
            # OR use py_vollib.black_scholes.implied_volatility to reverse engineer IV from Market Price (LTP).
            
            weekly_chain_data = []
            now = datetime.now()
            
            for _, row in current_weekly_subset.iterrows():
                key = row['instrument_key']
                if key in quotes:
                    ltp = quotes[key].last_price
                    # simple IV place holder or reverse calc
                    # For MVP logic, just use dummy IV 15% -> 0.15 
                    # In PROD: Calculate Implied Volatility from LTP using py_vollib.balck_scholes_implied_volatility
                    
                    # Time to expiry
                    # expiry_dt is date, we need years
                    # (expiry - now).days / 365
                    tte = (datetime.combine(row['expiry_dt'], datetime.min.time()) - now).days / 365.0
                    if tte <= 0: tte = 0.001 # avoid div zero
                    
                    weekly_chain_data.append({
                        'strike': row['strike'],
                        'iv': calculate_implied_volatility(ltp, spot_price, row['strike'], tte, config.RISK_FREE_RATE, 'p'),
                        'time_to_expiry': tte,
                        'instrument_key': key,
                        'ltp': ltp
                    })
            
            monthly_chain_data = []
            for _, row in current_monthly_subset.iterrows():
                key = row['instrument_key']
                if key in quotes:
                    ltp = quotes[key].last_price
                    tte = (datetime.combine(row['expiry_dt'], datetime.min.time()) - now).days / 365.0
                    if tte <= 0: tte = 0.001
                    
                    monthly_chain_data.append({
                        'strike': row['strike'],
                        'iv': calculate_implied_volatility(ltp, spot_price, row['strike'], tte, config.RISK_FREE_RATE, 'p'), 
                        'time_to_expiry': tte,
                        'instrument_key': key,
                        'ltp': ltp
                    })

            # C. Run Strategy Logic
            
            # Define Execution Callback for Strategy to use
            def place_trade_callback(instrument_key, qty, side, tag):
                if config.TRADING_MODE == 'PAPER':
                    print(f"[{datetime.now()}] [PAPER TRADE] {side} {qty} Qty | Key: {instrument_key} | Tag: {tag}")
                    return {'status': 'success', 'avg_price': 0.0} # Mock response
                else:
                    print(f"[{datetime.now()}] [LIVE EXECUTION] {side} {qty} Qty | Key: {instrument_key}")
                    # REAL ORDER
                    return api.place_order(instrument_key, qty, side, tag=tag)

            # Check Entry
            if not strategy.weekly_position and not strategy.monthly_position:
                 strategy.enter_strategy(spot_price, weekly_chain_data, monthly_chain_data, order_callback=place_trade_callback)

            # Monitor & Adjust
            strategy.update_deltas(spot_price, 
                                   current_time_to_expiry_weekly=weekly_chain_data[0]['time_to_expiry'] if weekly_chain_data else 0.01,
                                   current_time_to_expiry_monthly=monthly_chain_data[0]['time_to_expiry'] if monthly_chain_data else 0.01,
                                   weekly_iv=0.15, monthly_iv=0.15)
                                   
            strategy.check_adjustments(spot_price, weekly_chain_data, monthly_chain_data, order_callback=place_trade_callback)
            
            time.sleep(config.POLL_INTERVAL_SECONDS) # poll interval
            
    except KeyboardInterrupt:
        print("Stopping...")

if __name__ == "__main__":
    main()

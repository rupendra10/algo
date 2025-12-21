import os
import time
from datetime import datetime, date, timedelta
from upstox_wrapper import UpstoxWrapper
from instrument_manager import InstrumentMaster
from strategy import NiftyStrategy
import config
from greeks import calculate_delta
from utils import calculate_implied_volatility
from event_monitor import print_event_summary
from colorama import Fore, Style



def main():
    print("Starting Algo...")
    print_event_summary()
    
    # 1. Setup
    api = UpstoxWrapper() # Reads token from Config/Env
    master = InstrumentMaster()
    master.load_master()
    
    strategy = NiftyStrategy(risk_free_rate=config.RISK_FREE_RATE)
    
    # --- RECOVERY LOGIC ---
    # Try to load existing positions from last run
    has_existing_pos = strategy.load_previous_state()
    
    # 2. Identify Instruments
    # Auto-detect expiries using master
    print("Identifying Expiries...")
    is_expiry_today = master.is_monthly_expiry_today(config.UNDERLYING_NAME)
    
    # Calculate if Tomorrow is Monthly Expiry (T-1 Day)
    tomorrow = date.today() + timedelta(days=1)
    # Note: Need a simple helper or check if tomorrow exists in master's month-end list
    expiries = master.get_expiry_dates(config.UNDERLYING_NAME)
    current_month_expiries = [d for d in expiries if d.year == tomorrow.year and d.month == tomorrow.month]
    is_day_before_monthly_expiry = (tomorrow == current_month_expiries[-1]) if current_month_expiries else False
    
    # SEGREGATION LOGIC
    if config.TRADING_MODE == 'LIVE' and config.STRICT_MONTHLY_EXPIRY_ENTRY and is_expiry_today:
        print("Today is MONTHLY EXPIRY (LIVE). Targeting NEW cycle (Next-Weekly & Next-Next-Monthly).")
        weekly_expiry, monthly_expiry = master.get_special_entry_expiries(config.UNDERLYING_NAME)
    else:
        # In PAPER mode or non-expiry days, take the closest available contracts
        if config.TRADING_MODE == 'PAPER':
            print("PAPER MODE: Selecting immediate Weekly and next Monthly for simulation.")
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
                        'expiry_dt': row['expiry_dt'],
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
                        'expiry_dt': row['expiry_dt'],
                        'instrument_key': key,
                        'ltp': ltp
                    })

            # C. Run Strategy Logic
            
            # Define Execution Callback for Strategy to use
            def place_trade_callback(instrument_key, qty, side, tag):
                # Update expiry context inside loop if needed, but for now we rely on daily start
                
                side_colored = f"{Fore.GREEN}{side}{Style.RESET_ALL}" if side == 'BUY' else f"{Fore.RED}{side}{Style.RESET_ALL}"
                if config.TRADING_MODE == 'PAPER':
                    # Look up current LTP from quotes for a realistic simulation
                    ltp_obj = quotes.get(instrument_key)
                    price = getattr(ltp_obj, 'last_price', 0.0) if ltp_obj else 0.0
                    print(f"[{datetime.now()}] [{Fore.CYAN}PAPER TRADE{Style.RESET_ALL}] {side_colored} {qty} Qty | Price: {price} | Key: {instrument_key}")
                    return {'status': 'success', 'avg_price': price} # Use actual market price for mock
                else:
                    print(f"[{datetime.now()}] [{Fore.RED}LIVE EXECUTION{Style.RESET_ALL}] {side_colored} {qty} Qty | Key: {instrument_key}")
                    # REAL ORDER
                    return api.place_order(instrument_key, qty, side, tag=tag)

            # 1. Professional Safety Checks (VIX & Margin) - ONLY in LIVE
            if config.TRADING_MODE == 'LIVE':
                vix_quote = api.get_option_chain_quotes(['NSE_INDEX|India VIX'])
                vix_obj = vix_quote.get('NSE_INDEX|India VIX')
                vix_ltp = getattr(vix_obj, 'last_price', 0.0) if vix_obj else 0.0
                available_cash = api.get_funds()

                if vix_ltp > config.MAX_ALLOWED_VIX:
                    strategy.log(f"{Fore.RED}WARNING (LIVE): India VIX {vix_ltp} is > {config.MAX_ALLOWED_VIX}. Paused.{Style.RESET_ALL}")
                    time.sleep(60)
                    continue
                    
                if available_cash < config.MIN_REQUIRED_CASH:
                    strategy.log(f"{Fore.RED}WARNING (LIVE): Insufficient Margin Buffer ({available_cash:.0f}). Paused.{Style.RESET_ALL}")
                    time.sleep(60)
                    continue

            # --- ROLLOVER LOGIC ---
            # Use configured Rollover Day
            if now.weekday() == config.ROLLOVER_WEEKDAY: 
                if strategy.weekly_position:
                    # Check if it's already the 'next' weekly expiry or the current one.
                    # For simplicity, if it's Monday, we roll whatever weekly we have to the 'new' weekly.
                    # We need to refresh target expiries to get the 'new' weekly.
                    new_weekly_expiry, _ = master.get_target_expiries(config.UNDERLYING_NAME)
                    
                    # If current position expiry is not the 'new' weekly (it means it's the one expiring tomorrow)
                    # Note: master.get_target_expiries should return the closest coming Tuesday/Thursday.
                    # If today is Monday, 'weekly' is likely tomorrow (Tuesday) or Thursday.
                    # spec: "On Monday (the day before weekly expiry)" -> This implies Tuesday expiry.
                    
                    current_pos_expiry_date = (now + timedelta(days=strategy.weekly_position['expiry'] * 365)).date()
                    if current_pos_expiry_date <= (now + timedelta(days=1)).date():
                        print(f"[{now}] MONDAY ROLLOVER: Squaring off current weekly and rolling to {new_weekly_expiry}")
                        # Exit Weekly
                        place_trade_callback(strategy.weekly_position['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'MONDAY_CLOSE')
                        strategy.weekly_position = None
                        
                        # Re-identify expiries to ensure we get the next one if master was updated
                        # Or just rely on the fact that next call to enter_strategy will pick the new ones.
                        # However, we might want to force a refresh of instruments if needed.

            # Check Entry
            if not strategy.weekly_position and not strategy.monthly_position:
                # STRICT ENTRY LOGIC (Only for LIVE mode)
                can_enter = True
                if config.TRADING_MODE == 'LIVE' and config.STRICT_MONTHLY_EXPIRY_ENTRY:
                    is_expiry_today = master.is_monthly_expiry_today(config.UNDERLYING_NAME)
                    current_time_str = now.strftime("%H:%M")
                    
                    if not is_expiry_today:
                        print(f"[{now}] WAITING (LIVE): Today is not Monthly Expiry. Initial entry disallowed.")
                        can_enter = False
                    elif current_time_str < config.ENTRY_TIME_HHMM:
                        print(f"[{now}] WAITING (LIVE): Entry window opens at {config.ENTRY_TIME_HHMM}. Current: {current_time_str}")
                        can_enter = False
                
                if can_enter:
                    strategy.enter_strategy(spot_price, weekly_chain_data, monthly_chain_data, order_callback=place_trade_callback)
                    strategy.save_current_state()
            elif not strategy.weekly_position:
                # If only weekly is missing (e.g. after rollover), re-enter weekly ATM
                strategy.log("Re-entering Weekly Leg (Rollover or missing)")
                strategy.adjust_weekly_leg(spot_price, weekly_chain_data, place_trade_callback)
                strategy.save_current_state()

            # 1. Check Portfolio-Level Risk (MTM Stop Loss) - ONLY in LIVE
            if config.TRADING_MODE == 'LIVE':
                w_ltp = weekly_chain_data[0]['ltp'] if weekly_chain_data else 0.0
                m_ltp = monthly_chain_data[0]['ltp'] if monthly_chain_data else 0.0
                if strategy.check_portfolio_risk(w_ltp, m_ltp, place_trade_callback):
                    time.sleep(config.POLL_INTERVAL_SECONDS)
                    continue # Skip adjustments if just exited

            # 2. Monitor & Adjust Deltas
            strategy.update_deltas(spot_price, 
                                   current_time_to_expiry_weekly=weekly_chain_data[0]['time_to_expiry'] if weekly_chain_data else 0.01,
                                   current_time_to_expiry_monthly=monthly_chain_data[0]['time_to_expiry'] if monthly_chain_data else 0.01,
                                   weekly_iv=0.15, monthly_iv=0.15)
                                   
            adjustment_made = strategy.check_adjustments(spot_price, weekly_chain_data, monthly_chain_data, order_callback=place_trade_callback)
            if adjustment_made:
                strategy.save_current_state() # Save after any delta adjustment
            
            # 3. P&L Tracking & Summary
            # Need to get LTP for the SPECIFIC instruments we hold, not just index 0
            w_ltp = 0.0
            m_ltp = 0.0
            if strategy.weekly_position:
                obj = quotes.get(strategy.weekly_position['instrument_key'])
                w_ltp = getattr(obj, 'last_price', 0.0) if obj else 0.0
            if strategy.monthly_position:
                obj = quotes.get(strategy.monthly_position['instrument_key'])
                m_ltp = getattr(obj, 'last_price', 0.0) if obj else 0.0
            
            open_pnl = strategy.get_open_pnl(w_ltp, m_ltp)
            
            strategy_state = {
                'weekly': strategy.weekly_position,
                'monthly': strategy.monthly_position,
                'weekly_ltp': w_ltp,
                'monthly_ltp': m_ltp
            }
            strategy.journal.print_summary(open_pnl, strategy_state)

            # 4. Monthly Expiry Protection (Reminder & Auto-Exit) - ONE DAY BEFORE
            current_time_str = now.strftime("%H:%M")
            if is_day_before_monthly_expiry:
                # Reminder around 2:45 PM
                if "14:45" <= current_time_str < "14:55":
                    print(f"\n{Fore.YELLOW}!!! PRE-MONTHLY EXPIRY REMINDER (T-1) !!!{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}Tomorrow is Monthly Expiry. Algo will AUTO-EXIT everything at 3:00 PM today.{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}Check your MTM now if you want to exit manually before.{Style.RESET_ALL}\n")
                
                # Auto-Exit at 3:00 PM
                if current_time_str >= "15:00" and config.AUTO_EXIT_BEFORE_MONTHLY_EXPIRY_3PM:
                    if strategy.weekly_position or strategy.monthly_position:
                        strategy.exit_all_positions(place_trade_callback, reason="PRE_MONTHLY_EXPIRY_T1")
                        strategy.save_current_state() # Update state to empty
                        strategy.log("Strategy Stopped for the month (T-1). Restart manually for the new cycle.")
                        # After monthly exit, we might want to break or wait for next day
                        time.sleep(3600) 
                        continue

            time.sleep(config.POLL_INTERVAL_SECONDS) # poll interval
            
    except KeyboardInterrupt:
        print("Stopping...")

if __name__ == "__main__":
    main()

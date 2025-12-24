import os
import pandas as pd
import time
from datetime import datetime, date, timedelta
from upstox_wrapper import UpstoxWrapper
from instrument_manager import InstrumentMaster
from strategy import CalendarPEWeekly, WeeklyIronfly
import config
from greeks import calculate_delta
from utils import calculate_implied_volatility
from event_monitor import print_event_summary
from colorama import Fore, Style

# Strategy Mapping for dynamic selection
STRATEGY_CLASSES = {
    'CalendarPEWeekly': CalendarPEWeekly,
    'WeeklyIronfly': WeeklyIronfly
}

def main():
    print(f"{Fore.CYAN}Starting Multi-Strategy Algo...{Style.RESET_ALL}")
    print_event_summary()
    
    # 1. Setup API and Master Data
    api = UpstoxWrapper() # Reads token from Config/Env
    master = InstrumentMaster()
    master.load_master()
    
    # 2. Instantiate and Initialize Active Strategies
    active_strategies = []
    print(f"Loading Active Strategies: {config.ACTIVE_STRATEGIES}")
    for s_name in config.ACTIVE_STRATEGIES:
        if s_name in STRATEGY_CLASSES:
            strat_inst = STRATEGY_CLASSES[s_name]()
            strat_inst.load_previous_state()
            active_strategies.append(strat_inst)
        else:
            print(f"{Fore.RED}WARNING: Strategy '{s_name}' is not recognized.{Style.RESET_ALL}")

    if not active_strategies:
        print(f"{Fore.RED}CRITICAL: No valid strategies configured. Exiting.{Style.RESET_ALL}")
        return
    
    # Display Trading Mode Banner
    mode_color = Fore.RED if config.TRADING_MODE == 'LIVE' else Fore.CYAN
    print("\n" + "="*60)
    print(f"{mode_color}TRADING MODE: {config.TRADING_MODE}{Style.RESET_ALL}")
    print(f"Active Strategies: {', '.join([s.name for s in active_strategies])}")
    if config.TRADING_MODE == 'LIVE':
        print(f"{Fore.YELLOW}⚠️  LIVE MODE - Real money at risk!{Style.RESET_ALL}")
        if config.STRICT_MONTHLY_EXPIRY_ENTRY:
            print(f"CalendarPEWeekly: Entries on Monthly Expiry Day at {config.ENTRY_TIME_HHMM}")
        print(f"WeeklyIronfly: Entries on Current Weekly Expiry at {config.IRONFLY_ENTRY_TIME}")
    else:
        print(f"{Fore.GREEN}✓ PAPER MODE - Simulation only{Style.RESET_ALL}")
    print("="*60 + "\n")

    # 3. Identify Expiries Dynamically
    expiries = master.get_expiry_dates(config.UNDERLYING_NAME)
    if not expiries or len(expiries) < 2:
        print(f"{Fore.RED}CRITICAL ERROR: Could not find at least two future expiries.{Style.RESET_ALL}")
        return

    curr_weekly = expiries[0]
    next_weekly = expiries[1]
    
    # NEW: Skip today's expiry if executing freshly on an expiry day
    today = date.today()
    expiry_skipped = False
    if curr_weekly == today:
        print(f"{Fore.YELLOW}Today is expiry day ({today}). Shifting to future expiries as per requirement.{Style.RESET_ALL}")
        expiry_skipped = True
        curr_weekly = expiries[1]
        if len(expiries) > 2:
            next_weekly = expiries[2]
        else:
            print(f"{Fore.RED}WARNING: Not enough future expiries found after shifting.{Style.RESET_ALL}")
    
    # Identify Monthly only if needed
    needs_monthly = 'CalendarPEWeekly' in config.ACTIVE_STRATEGIES
    
    monthly_expiry = None
    m_expiries = [] 
    if needs_monthly:
        # Find the last expiry of the next month relative to our (possibly shifted) curr_weekly
        target_month = curr_weekly.month + 1
        target_year = curr_weekly.year
        if target_month > 12: target_month = 1; target_year += 1
        
        # We look through all expiries, skipping today if it was skipped for weekly
        search_expiries = expiries[1:] if expiries[0] == today else expiries
        
        m_expiries = [d for d in search_expiries if d.year == target_year and d.month == target_month]
        if not m_expiries:
            # Fallback: next month after target_month
            target_month += 1
            if target_month > 12: target_month = 1; target_year += 1
            m_expiries = [d for d in search_expiries if d.year == target_year and d.month == target_month]
            
        monthly_expiry = m_expiries[-1] if m_expiries else expiries[-1]

    print(f"{Fore.CYAN}Expiries Identified:{Style.RESET_ALL}")
    print(f" - [Main Weekly]:    {curr_weekly}")
    print(f" - [Next Weekly]:    {next_weekly} (Target for WeeklyIronfly Entry)")
    if monthly_expiry:
        print(f" - [Monthly Hedge]:  {monthly_expiry} (For CalendarPEWeekly)")
    elif 'WeeklyIronfly' in config.ACTIVE_STRATEGIES:
        print(f" - [Monthly]:        Not pre-fetched (WeeklyIronfly only needs for adjustments)")

    # Pre-fetch instrument lists for all relevant segments
    # Current Weekly
    cw_pe = master.get_option_symbols(config.UNDERLYING_NAME, curr_weekly, 'PE')
    cw_ce = master.get_option_symbols(config.UNDERLYING_NAME, curr_weekly, 'CE')
    # Next Weekly
    nw_pe = master.get_option_symbols(config.UNDERLYING_NAME, next_weekly, 'PE')
    nw_ce = master.get_option_symbols(config.UNDERLYING_NAME, next_weekly, 'CE')
    # Monthly
    m_pe = master.get_option_symbols(config.UNDERLYING_NAME, monthly_expiry, 'PE') if monthly_expiry else pd.DataFrame()
    m_ce = master.get_option_symbols(config.UNDERLYING_NAME, monthly_expiry, 'CE') if monthly_expiry else pd.DataFrame()

    is_expiry_today = master.is_monthly_expiry_today(config.UNDERLYING_NAME)
    tomorrow = date.today() + timedelta(days=1)
    is_day_before_monthly_expiry = (tomorrow == m_expiries[-1]) if needs_monthly and m_expiries else False
    
    # 4. Main Polling Loop
    last_adj_minute = -1
    try:
        while True:
            now = datetime.now()
            
            # Candle-Based Adjustment Logic (5-min intervals)
            adj_interval = 5
            can_adjust = False
            if now.minute % adj_interval == 0 and now.minute != last_adj_minute:
                can_adjust = True
                # We update last_adj_minute below ONLY IF we actually processed the strategies
                # But for now, let's mark it so we don't trigger multiple times in the same minute
                last_adj_minute = now.minute

            # A. Get Spot Price
            spot_price = api.get_spot_price(config.SPOT_INSTRUMENT_KEY)
            if not spot_price:
                print("Waiting for quote...")
                time.sleep(5)
                continue
            
            adj_status = f"{Fore.GREEN}ADJ WINDOW OPEN{Style.RESET_ALL}" if can_adjust else f"Next Adj: {adj_interval - (now.minute % adj_interval)}m"
            print(f"[{now.strftime('%H:%M:%S')}] Spot: {spot_price} | {adj_status}")
            
            # B. Build Market Data Context
            # Filter options around ATM (±500 pts)
            atm = round(spot_price / 50) * 50
            strikes = range(atm - 500, atm + 550, 50)
            
            # Combine all keys for quotes
            def get_near_df(pe_df, ce_df):
                p_near = pe_df[pe_df['strike'].isin(strikes)]
                c_near = ce_df[ce_df['strike'].isin(strikes)]
                return p_near, c_near

            cw_pe_near, cw_ce_near = get_near_df(cw_pe, cw_ce)
            nw_pe_near, nw_ce_near = get_near_df(nw_pe, nw_ce)
            m_pe_near, m_ce_near = get_near_df(m_pe, m_ce) if needs_monthly else (pd.DataFrame(columns=['instrument_key']), pd.DataFrame(columns=['instrument_key']))
            
            all_keys = list(set(cw_pe_near['instrument_key'].tolist() + cw_ce_near['instrument_key'].tolist() +
                                nw_pe_near['instrument_key'].tolist() + nw_ce_near['instrument_key'].tolist() +
                                m_pe_near['instrument_key'].tolist() + m_ce_near['instrument_key'].tolist()))
            
            # Ensure currently held positions are ALWAYS included, even if they drift away from ATM
            for strat in active_strategies:
                # CalendarPEWeekly style
                if hasattr(strat, 'weekly_position') and strat.weekly_position:
                    all_keys.append(strat.weekly_position['instrument_key'])
                if hasattr(strat, 'monthly_position') and strat.monthly_position:
                    all_keys.append(strat.monthly_position['instrument_key'])

                # WeeklyIronfly style
                if hasattr(strat, 'positions') and strat.positions:
                   for pos in strat.positions:
                       all_keys.append(pos['instrument_key'])
            
            all_keys = list(set(all_keys))

            # NEW: Perform metadata recovery for held positions using Master DF
            for strat in active_strategies:
                # CalendarPEWeekly style
                for pos_attr in ['weekly_position', 'monthly_position']:
                    pos = getattr(strat, pos_attr, None)
                    # We check if expiry_dt is missing OR is a float (the old 'expiry' field format)
                    if pos and (not pos.get('expiry_dt') or pos.get('expiry_dt') == 'N/A' or isinstance(pos.get('expiry_dt'), float)):
                        key = pos['instrument_key']
                        match = master.df[master.df['instrument_key'] == key]
                        if not match.empty:
                            row = match.iloc[0]
                            pos['expiry_dt'] = str(row['expiry_dt'])
                            if 'type' not in pos: pos['type'] = row['instrument_type'].lower()
                            if 'strike' not in pos: pos['strike'] = float(row['strike'])
                            strat.save_state()

                # WeeklyIronfly style
                if hasattr(strat, 'positions') and strat.positions:
                   changed = False
                   for pos in strat.positions:
                       if not pos.get('expiry_dt') or pos.get('expiry_dt') == 'N/A':
                            key = pos['instrument_key']
                            match = master.df[master.df['instrument_key'] == key]
                            if not match.empty:
                                row = match.iloc[0]
                                pos['expiry_dt'] = str(row['expiry_dt'])
                                if 'type' not in pos: pos['type'] = row['instrument_type']
                                if 'strike' not in pos: pos['strike'] = float(row['strike'])
                                changed = True
                   if changed:
                       strat.save_state()

            if len(all_keys) > 100:
                print(f"{Fore.YELLOW}WARNING: Requesting high number of symbols ({len(all_keys)}). Possible rate limit risk.{Style.RESET_ALL}")
            
            quotes = api.get_option_chain_quotes(all_keys)
            
            # Helper to package chain data
            def package_chain(pe_df, ce_df, q_dict, spot, t_now):
                chain = []
                # Use raw dataframes but only process what we have quotes for
                for df, opt_type in [(pe_df, 'p'), (ce_df, 'c')]:
                    # Optimization: only look at keys we actually fetched
                    df_relevant = df[df['instrument_key'].isin(q_dict.keys())]
                    for _, row in df_relevant.iterrows():
                        key = row['instrument_key']
                        ltp = q_dict[key].last_price
                        tte = (datetime.combine(row['expiry_dt'], datetime.min.time()) - t_now).total_seconds() / (365*24*3600)
                        if tte <= 0: tte = 0.0001
                        chain.append({
                            'strike': row['strike'],
                            'iv': calculate_implied_volatility(ltp, spot, row['strike'], tte, config.RISK_FREE_RATE if hasattr(config, 'RISK_FREE_RATE') else 0.05, opt_type),
                            'time_to_expiry': tte,
                            'expiry_dt': row['expiry_dt'].strftime('%Y-%m-%d'),
                            'instrument_key': key,
                            'ltp': ltp,
                            'type': opt_type
                        })
                return chain

            cw_chain_data = package_chain(cw_pe, cw_ce, quotes, spot_price, now)
            nw_chain_data = package_chain(nw_pe, nw_ce, quotes, spot_price, now)
            m_chain_data = package_chain(m_pe, m_ce, quotes, spot_price, now) if needs_monthly else []

            # Create Execution Callback
            def place_trade_callback(instrument_key, qty, side, tag, expiry='N/A'):
                side_colored = f"{Fore.GREEN}{side}{Style.RESET_ALL}" if side == 'BUY' else f"{Fore.RED}{side}{Style.RESET_ALL}"
                if config.TRADING_MODE == 'PAPER':
                    price = quotes[instrument_key].last_price if instrument_key in quotes else 0.0
                    print(f"[{datetime.now()}] [{Fore.CYAN}PAPER{Style.RESET_ALL}] {side_colored} {qty} | Key: {instrument_key} | Price: {price} | Expiry: {expiry}")
                    return {'status': 'success', 'avg_price': price}
                else:
                    print(f"[{datetime.now()}] [{Fore.RED}LIVE{Style.RESET_ALL}] {side_colored} {qty} | Key: {instrument_key} | Expiry: {expiry}")
                    return api.place_order(instrument_key, qty, side, tag=tag)

            # Check Global Entry Windows for LIVE
            can_enter_new_cycle = True
            current_time_str = now.strftime("%H:%M")
            if config.TRADING_MODE == 'LIVE' and config.STRICT_MONTHLY_EXPIRY_ENTRY:
                if not is_expiry_today:
                    can_enter_new_cycle = False
                elif current_time_str < config.ENTRY_TIME_HHMM:
                    can_enter_new_cycle = False

            # Compile Market Data
            market_data = {
                'spot_price': spot_price,
                'now': now,
                'cw_chain': cw_chain_data,
                'nw_chain': nw_chain_data,
                'm_chain': m_chain_data,
                'quotes': quotes,
                'is_day_before_monthly_expiry': is_day_before_monthly_expiry,
                'is_expiry_today': is_expiry_today,
                'can_enter_new_cycle': can_enter_new_cycle,
                'can_adjust': can_adjust,
                'expiry_skipped': expiry_skipped
            }

            # C. Update All Strategies
            for strat in active_strategies:
                try:
                    strat.update(market_data, place_trade_callback)
                except Exception as e:
                    print(f"{Fore.RED}Error in Strategy {strat.name}: {e}{Style.RESET_ALL}")
            
            time.sleep(config.POLL_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Algo stopping manually...{Style.RESET_ALL}")
        # Option to exit all on manual stop could be added here

if __name__ == "__main__":
    main()

import config
from datetime import datetime, timedelta
from greeks import calculate_delta, get_atm_strike
from colorama import init, Fore, Style
from trade_logger import TradeJournal
from base_strategy import BaseStrategy
import re

# Initialize colorama for Windows support
init(autoreset=True)

class CalendarPEWeekly(BaseStrategy):
    def __init__(self, risk_free_rate=config.RISK_FREE_RATE):
        super().__init__("CalendarPEWeekly")
        # State
        self.weekly_position = None  # {'type': 'sell', 'strike': K, 'expiry': T, 'entry_price': P, 'delta': D}
        self.monthly_position = None # {'type': 'buy',  'strike': K, 'expiry': T, 'entry_price': P, 'delta': D}
        self.last_rollover_date = None  # Track last Monday rollover to prevent duplicates
        
        self.risk_free_rate = risk_free_rate
        self.logs = []
        self.journal = TradeJournal(filename="trade_log_calendar.csv")

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Color specific keywords in message
        colored_message = message.replace("SOLD", f"{Fore.RED}SOLD{Style.RESET_ALL}")
        colored_message = colored_message.replace("BOUGHT", f"{Fore.GREEN}BOUGHT{Style.RESET_ALL}")
        colored_message = colored_message.replace("ENTRY", f"{Fore.YELLOW}ENTRY{Style.RESET_ALL}")
        colored_message = colored_message.replace("ADJUSTMENT", f"{Fore.MAGENTA}ADJUSTMENT{Style.RESET_ALL}")
        
        # Color Dates
        date_pattern = r"(\d{4}-\d{2}-\d{2})"
        colored_message = re.sub(date_pattern, rf"{Fore.CYAN}\1{Style.RESET_ALL}", colored_message)

        entry = f"[{timestamp}] [{self.name}] {colored_message}"
        print(entry)
        self.logs.append(entry)

    def update(self, market_data, order_callback):
        """
        Main logic loop for Calendar PE Weekly.
        market_data: {spot_price, weekly_chain, monthly_chain, quotes, now, master_flags...}
        """
        spot_price = market_data.get('spot_price')
        weekly_chain = market_data.get('weekly_chain', [])
        monthly_chain = market_data.get('monthly_chain', [])
        quotes = market_data.get('quotes', {})
        now = market_data.get('now', datetime.now())

        spot_price = market_data.get('spot_price')
        # Mapping generic runner keys to strategy-specific usage
        weekly_chain = market_data.get('cw_chain', [])  # Current Weekly
        monthly_chain = market_data.get('m_chain', [])  # Monthly Target
        quotes = market_data.get('quotes', {})
        now = market_data.get('now', datetime.now())

        if not spot_price:
            return

        # 1. Update Deltas for existing positions
        self.update_deltas(spot_price, 
                           current_time_to_expiry_weekly=weekly_chain[0]['time_to_expiry'] if weekly_chain else 0.01,
                           current_time_to_expiry_monthly=monthly_chain[0]['time_to_expiry'] if monthly_chain else 0.01,
                           weekly_iv=0.15, monthly_iv=0.15)

        # --- MONDAY ROLLOVER LOGIC ---
        if now.weekday() == config.ROLLOVER_WEEKDAY and self.weekly_position:
            # Check if we've already rolled over today
            today_str = now.strftime("%Y-%m-%d")
            if self.last_rollover_date != today_str:
                # Check if current position expiry is tomorrow or less (relative to now)
                # In paper/sim, we look at the time_to_expiry
                if self.weekly_position['expiry'] <= 1.5/365.0: # Close to expiry
                    self.log(f"MONDAY ROLLOVER: Squaring off current weekly and rolling.")
                    order_callback(self.weekly_position['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'MONDAY_CLOSE')
                    self.weekly_position = None
                    self.last_rollover_date = today_str  # Mark rollover as done for today
                    self.save_state()

        # --- MONTHLY EXPIRY PROTECTION ---
        if market_data.get('is_day_before_monthly_expiry'):
            current_time_str = now.strftime("%H:%M")
            if current_time_str >= "15:00" and config.AUTO_EXIT_BEFORE_MONTHLY_EXPIRY_3PM:
                if self.weekly_position or self.monthly_position:
                    self.exit_all_positions(order_callback, reason="PRE_MONTHLY_EXPIRY_T1")
                    self.save_state()
                    self.log("Strategy Stopped for the month (T-1).")
                    return

        # 2. Check Entry Logic
        if not self.weekly_position and not self.monthly_position:
            can_enter = market_data.get('can_enter_new_cycle', True)
            
            # In LIVE mode with strict entry, check if today is monthly expiry
            if config.TRADING_MODE == 'LIVE' and config.STRICT_MONTHLY_EXPIRY_ENTRY:
                # Get monthly expiry from market_data
                monthly_chain = market_data.get('m_chain', [])
                if monthly_chain:
                    # Extract expiry date from first option in monthly chain
                    monthly_expiry_str = monthly_chain[0].get('expiry_dt', '')
                    try:
                        monthly_expiry_date = datetime.strptime(monthly_expiry_str, '%Y-%m-%d').date()
                        is_monthly_expiry_today = (now.date() == monthly_expiry_date)
                        current_time_str = now.strftime("%H:%M")
                        
                        if is_monthly_expiry_today and current_time_str >= config.ENTRY_TIME_HHMM:
                            can_enter = True
                        else:
                            can_enter = False
                    except:
                        can_enter = False
            
            if can_enter:
                self.enter_strategy(spot_price, weekly_chain, monthly_chain, order_callback=order_callback)
                self.save_state()
            else:
                if now.second < 10 and now.minute % 5 == 0: # Log every 5 mins in the first 10s
                    if config.TRADING_MODE == 'LIVE' and config.STRICT_MONTHLY_EXPIRY_ENTRY:
                        monthly_chain = market_data.get('m_chain', [])
                        if monthly_chain:
                            monthly_expiry_str = monthly_chain[0].get('expiry_dt', 'N/A')
                            self.log(f"{Fore.YELLOW}[LIVE MODE] WAITING: Entry allowed only on Monthly Expiry ({monthly_expiry_str}) at {config.ENTRY_TIME_HHMM}. Today is {now.strftime('%Y-%m-%d %H:%M')}.{Style.RESET_ALL}")
                        else:
                            self.log(f"{Fore.YELLOW}[LIVE MODE] WAITING: Entry allowed only on Monthly Expiry Day at {config.ENTRY_TIME_HHMM}.{Style.RESET_ALL}")
                    else:
                        self.log("WAITING: Cycle entry conditions not yet met.")
        
        elif not self.weekly_position:
            # Re-entry after rollover or leg specific exit
            self.log("Re-entering Weekly Leg")
            self.adjust_weekly_leg(spot_price, weekly_chain, order_callback)
            self.save_state()

        # 3. Check Portfolio Risk
        w_ltp = 0.0
        m_ltp = 0.0
        if self.weekly_position:
            obj = quotes.get(self.weekly_position['instrument_key'])
            w_ltp = getattr(obj, 'last_price', 0.0) if obj else 0.0
        if self.monthly_position:
            obj = quotes.get(self.monthly_position['instrument_key'])
            m_ltp = getattr(obj, 'last_price', 0.0) if obj else 0.0

        if self.check_portfolio_risk(w_ltp, m_ltp, order_callback):
            self.save_state()
            return

        # 4. Check Adjustments (ONLY on candle marks)
        can_adjust = market_data.get('can_adjust', True)
        adjustment_made = False
        if can_adjust:
            adjustment_made = self.check_adjustments(spot_price, weekly_chain, monthly_chain, order_callback=order_callback)
        if adjustment_made:
            self.save_state()

        # 5. PnL Summary Logging
        open_pnl = self.get_open_pnl(w_ltp, m_ltp)
        strategy_state = {
            'weekly': self.weekly_position,
            'monthly': self.monthly_position,
            'weekly_ltp': w_ltp,
            'monthly_ltp': m_ltp
        }
        self.journal.print_summary(open_pnl, strategy_state)

    def select_strike_by_delta(self, spot, chain, target_delta, option_type='p', tolerance=0.1):
        """
        Finds a strike in the option chain closest to the target delta.
        chain: list of dicts {'strike': K, 'iv': sigma, 'expiry': t_years}
        """
        best_strike = None
        min_diff = float('inf')
        
        for opt in chain:
            # ONLY consider options of the requested type (p or c)
            if opt.get('type') != option_type:
                continue
                
            d = calculate_delta(option_type, spot, opt['strike'], opt['time_to_expiry'], self.risk_free_rate, opt['iv'])
            # Put delta is usually negative (-0.5). User spec says "0.45-0.55". 
            # We'll assume we look at absolute delta or the standard definition.
            # Standard Put Delta is negative. "Delta 0.5" usually means -0.5.
            # "Delta increases to 0.90" implies it becomes more negative (conceptually "higher" sensitivity).
            # But technically -0.9 is smaller than -0.5. 
            # Industry standard usage: "50 Delta Put" = -0.5. "90 Delta Put" = -0.9.
            # We will use abs(delta) for comparison to target.
            
            abs_d = abs(d)
            diff = abs(abs_d - target_delta)
            
            if diff < min_diff:
                min_diff = diff
                best_strike = opt.copy() # Avoid modifying shared chain data
                best_strike['calculated_delta'] = abs_d
        
        # Check if within reasonable tolerance if needed, or just take best
        return best_strike

    def enter_strategy(self, spot, weekly_chain, monthly_chain, order_callback=None):
        self.log(f"Attempting Atomic Entry at Spot: {spot}")
        
        # Reset any partial state
        self.weekly_position = None
        self.monthly_position = None

        # 1. Select Legs
        weekly_leg = self.select_strike_by_delta(spot, weekly_chain, config.ENTRY_WEEKLY_DELTA_TARGET)
        monthly_leg = self.select_strike_by_delta(spot, monthly_chain, config.ENTRY_MONTHLY_DELTA_TARGET)

        if not weekly_leg or not monthly_leg:
            self.log("ERROR: Could not find suitable strikes for both legs. Aborting entry.")
            return

        # 2. Execute Entry (SELL Weekly first, then BUY Monthly)
        if order_callback:
            # Sell Weekly
            resp_w = order_callback(weekly_leg['instrument_key'], config.ORDER_QUANTITY, 'SELL', 'WEEKLY_ENTRY', expiry=weekly_leg.get('expiry_dt'))
            if resp_w and (resp_w.get('status') == 'success'):
                # Capture execution price
                entry_price = resp_w.get('avg_price', weekly_leg.get('ltp', 0.0))
                self.weekly_position = {
                    'leg': 'weekly_sell',
                    'strike': weekly_leg['strike'],
                    'expiry': weekly_leg['time_to_expiry'],
                    'iv': weekly_leg['iv'],
                    'delta': weekly_leg['calculated_delta'],
                    'entry_spot': spot,
                    'instrument_key': weekly_leg['instrument_key'],
                    'entry_price': entry_price,
                    'type': weekly_leg.get('type', 'p'),
                    'expiry_dt': weekly_leg.get('expiry_dt')
                }
                self.journal.log_trade(weekly_leg['instrument_key'], 'SELL', config.ORDER_QUANTITY, entry_price, 'WEEKLY_ENTRY', expiry=weekly_leg.get('expiry_dt'))
                self.log(f"ENTRY: SOLD Weekly Put | Strike: {weekly_leg['strike']} | Price: {entry_price} | Expiry: {weekly_leg['expiry_dt']} | Delta: {weekly_leg['calculated_delta']:.2f}")
            else:
                self.log(f"CRITICAL ERROR: Weekly Sell Order FAILED.")
                return

            # Buy Monthly
            resp_m = order_callback(monthly_leg['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'MONTHLY_ENTRY', expiry=monthly_leg.get('expiry_dt'))
            if resp_m and (resp_m.get('status') == 'success'):
                # Capture execution price
                entry_price_m = resp_m.get('avg_price', monthly_leg.get('ltp', 0.0))
                self.monthly_position = {
                    'leg': 'monthly_buy',
                    'strike': monthly_leg['strike'],
                    'expiry': monthly_leg['time_to_expiry'],
                    'iv': monthly_leg['iv'],
                    'delta': monthly_leg['calculated_delta'],
                    'entry_spot': spot,
                    'instrument_key': monthly_leg['instrument_key'],
                    'entry_price': entry_price_m,
                    'type': monthly_leg.get('type', 'p'),
                    'expiry_dt': monthly_leg.get('expiry_dt')
                }
                self.journal.log_trade(monthly_leg['instrument_key'], 'BUY', config.ORDER_QUANTITY, entry_price_m, 'MONTHLY_ENTRY', expiry=monthly_leg.get('expiry_dt'))
                self.log(f"ENTRY: BOUGHT Monthly Put | Strike: {monthly_leg['strike']} | Price: {entry_price_m} | Expiry: {monthly_leg['expiry_dt']} | Delta: {monthly_leg['calculated_delta']:.2f}")
            else:
                self.log(f"CRITICAL ERROR: Monthly Buy Order FAILED.")
                # EMERGENCY: Weekly was sold, but Monthly failed. Must square off Weekly immediately!
                self.log("EMERGENCY: Squaring off Weekly leg.")
                resp_exit = order_callback(weekly_leg['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'EMERGENCY_EXIT', expiry=weekly_leg.get('expiry_dt'))
                exit_price = resp_exit.get('avg_price', 0.0)
                pnl = (self.weekly_position['entry_price'] - exit_price) * config.ORDER_QUANTITY
                self.journal.log_trade(weekly_leg['instrument_key'], 'BUY', config.ORDER_QUANTITY, exit_price, 'EMERGENCY_EXIT', expiry=weekly_leg.get('expiry_dt'), pnl=pnl)
                self.weekly_position = None
                return
        # else:
        #     self.log("DEV NOTE: No order_callback provided, entry skipped.")

    def update_deltas(self, spot, current_time_to_expiry_weekly, current_time_to_expiry_monthly, weekly_iv, monthly_iv):
        """
        Re-calculate deltas for existing positions based on new spot/time/iv
        """
        if self.weekly_position:
            p_type = self.weekly_position.get('type', 'p') # Default to Put for safety
            d = calculate_delta(p_type, spot, self.weekly_position['strike'], current_time_to_expiry_weekly, self.risk_free_rate, weekly_iv)
            self.weekly_position['delta'] = abs(d)
            # update expiry/iv references if provided dynamic
            self.weekly_position['expiry'] = current_time_to_expiry_weekly
        
        if self.monthly_position:
            p_type = self.monthly_position.get('type', 'p')
            d = calculate_delta(p_type, spot, self.monthly_position['strike'], current_time_to_expiry_monthly, self.risk_free_rate, monthly_iv)
            self.monthly_position['delta'] = abs(d)
            self.monthly_position['expiry'] = current_time_to_expiry_monthly

    def check_adjustments(self, spot, weekly_chain, monthly_chain, order_callback=None):
        """
        Logic 3: Adjustment
        """
        if not self.weekly_position or not self.monthly_position:
            return False

        adjustment_made = False

        # 1. Weekly Put (Sell Leg) Adjustments
        # On a Market Fall: If delta increases to 0.80
        if self.weekly_position['delta'] >= config.WEEKLY_ADJ_TRIGGER_DELTA:
            self.log(f"WEEKLY ADJ (FALL): Delta is {self.weekly_position['delta']:.2f} >= {config.WEEKLY_ADJ_TRIGGER_DELTA}")
            self.adjust_weekly_leg(spot, weekly_chain, order_callback)
            adjustment_made = True

        # On a Market Rise: If delta drops to 0.10 or below
        elif self.weekly_position['delta'] <= config.WEEKLY_ADJ_TRIGGER_DELTA_LOW:
            self.log(f"WEEKLY ADJ (RISE): Delta is {self.weekly_position['delta']:.2f} <= {config.WEEKLY_ADJ_TRIGGER_DELTA_LOW}")
            self.adjust_weekly_leg(spot, weekly_chain, order_callback)
            adjustment_made = True

        # 2. Next-Month Put (Buy Leg) Adjustments
        # On a Sharp Market Fall: If delta reaches 0.90
        if self.monthly_position['delta'] >= config.MONTHLY_ADJ_TRIGGER_DELTA:
            self.log(f"MONTHLY ADJ (FALL): Delta is {self.monthly_position['delta']:.2f} >= {config.MONTHLY_ADJ_TRIGGER_DELTA}")
            self.adjust_monthly_leg(spot, monthly_chain, config.MONTHLY_ROLL_TARGET_DELTA_FALL, order_callback)
            adjustment_made = True

        # On a Sharp Market Rise: If delta drops to 0.10
        elif self.monthly_position['delta'] <= config.MONTHLY_ADJ_TRIGGER_DELTA_LOW:
            self.log(f"MONTHLY ADJ (RISE): Delta is {self.monthly_position['delta']:.2f} <= {config.MONTHLY_ADJ_TRIGGER_DELTA_LOW}")
            self.adjust_monthly_leg(spot, monthly_chain, config.MONTHLY_ROLL_TARGET_DELTA_RISE, order_callback)
            adjustment_made = True
        
        return adjustment_made

    def adjust_weekly_leg(self, spot, chain, order_callback):
        # 1. Select New Leg first to ensure we have a target
        new_leg = self.select_strike_by_delta(spot, chain, config.WEEKLY_ROLL_TARGET_DELTA)
        if not new_leg:
            self.log("ERROR: Could not find suitable new Weekly strike for adjustment. Skipping.")
            return

        # 2. Exit Existing
        if order_callback and self.weekly_position:
            resp_exit = order_callback(self.weekly_position['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'WEEKLY_EXIT_ADJ', expiry=self.weekly_position.get('expiry_dt'))
            if (resp_exit and resp_exit.get('status') == 'success'):
                # PNL = (Entry - Exit) for Sell side
                exit_price = resp_exit.get('avg_price', 0.0)
                pnl = (self.weekly_position['entry_price'] - exit_price) * config.ORDER_QUANTITY
                self.journal.log_trade(self.weekly_position['instrument_key'], 'BUY', config.ORDER_QUANTITY, exit_price, 'WEEKLY_EXIT_ADJ', expiry=self.weekly_position.get('expiry_dt'), pnl=pnl)
            else:
                self.log(f"CRITICAL ERROR: Weekly Exit Order FAILED. Aborting adjustment to prevent double selling.")
                return
        
        self.weekly_position = None
        
        # 3. Enter New
        if order_callback:
            resp_entry = order_callback(new_leg['instrument_key'], config.ORDER_QUANTITY, 'SELL', 'WEEKLY_ROLL_ENTRY', expiry=new_leg.get('expiry_dt'))
            if resp_entry and (resp_entry.get('status') == 'success'):
                entry_price = resp_entry.get('avg_price', new_leg.get('ltp', 0.0))
                self.weekly_position = {
                    'leg': 'weekly_sell',
                    'strike': new_leg['strike'],
                    'expiry': new_leg['time_to_expiry'],
                    'iv': new_leg['iv'],
                    'delta': new_leg['calculated_delta'],
                    'entry_spot': spot,
                    'instrument_key': new_leg['instrument_key'],
                    'entry_price': entry_price,
                    'type': new_leg.get('type', 'p'),
                    'expiry_dt': new_leg.get('expiry_dt')
                }
                self.journal.log_trade(new_leg['instrument_key'], 'SELL', config.ORDER_QUANTITY, entry_price, 'WEEKLY_ROLL_ENTRY', expiry=new_leg.get('expiry_dt'))
                self.log(f"ADJUSTMENT ENTRY: SOLD Weekly ATM Put | Strike: {new_leg['strike']} | Price: {entry_price} | Delta: {new_leg['calculated_delta']:.2f}")
            else:
                self.log(f"CRITICAL ERROR: Weekly Roll Entry FAILED. Currently NAKED.")

    def adjust_monthly_leg(self, spot, chain, target_delta, order_callback):
        # 1. Select New Leg
        new_leg = self.select_strike_by_delta(spot, chain, target_delta)
        if not new_leg:
            self.log("ERROR: Could not find suitable new Monthly strike for adjustment. Skipping.")
            return

        # 2. Exit Existing
        if order_callback and self.monthly_position:
            resp_exit = order_callback(self.monthly_position['instrument_key'], config.ORDER_QUANTITY, 'SELL', 'MONTHLY_EXIT_ADJ', expiry=self.monthly_position.get('expiry_dt'))
            if (resp_exit and resp_exit.get('status') == 'success'):
                # PNL = (Exit - Entry) for Buy side
                exit_price = resp_exit.get('avg_price', 0.0)
                pnl = (exit_price - self.monthly_position['entry_price']) * config.ORDER_QUANTITY
                self.journal.log_trade(self.monthly_position['instrument_key'], 'SELL', config.ORDER_QUANTITY, exit_price, 'MONTHLY_EXIT_ADJ', expiry=self.monthly_position.get('expiry_dt'), pnl=pnl)
            else:
                self.log(f"CRITICAL ERROR: Monthly Exit Order FAILED. Aborting adjustment.")
                return
             
        self.monthly_position = None
        
        # 3. Enter New
        if order_callback:
            resp_entry = order_callback(new_leg['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'MONTHLY_ROLL_ENTRY', expiry=new_leg.get('expiry_dt'))
            if resp_entry and (resp_entry.get('status') == 'success'):
                entry_price = resp_entry.get('avg_price', new_leg.get('ltp', 0.0))
                self.monthly_position = {
                    'leg': 'monthly_buy',
                    'strike': new_leg['strike'],
                    'expiry': new_leg['time_to_expiry'],
                    'iv': new_leg['iv'],
                    'delta': new_leg['calculated_delta'],
                    'entry_spot': spot,
                    'instrument_key': new_leg['instrument_key'],
                    'entry_price': entry_price,
                    'type': new_leg.get('type', 'p'),
                    'expiry_dt': new_leg.get('expiry_dt')
                }
                self.journal.log_trade(new_leg['instrument_key'], 'BUY', config.ORDER_QUANTITY, entry_price, 'MONTHLY_ROLL_ENTRY', expiry=new_leg.get('expiry_dt'))
                self.log(f"ADJUSTMENT ENTRY: BOUGHT Monthly Put | Strike: {new_leg['strike']} | Price: {entry_price} | Delta: {new_leg['calculated_delta']:.2f}")
            else:
                self.log(f"CRITICAL ERROR: Monthly Roll Entry FAILED. Currently UNHEDGED.")

    def check_portfolio_risk(self, weekly_ltp, monthly_ltp, order_callback):
        """
        Calculates Net PNL and checks against Max Loss threshold.
        """
        # Skip if disabled
        if config.MAX_LOSS_VALUE <= 0:
            return False

        if not self.weekly_position or not self.monthly_position:
            return False

        # PNL = (Entry - Current) for Sell side
        weekly_pnl = (self.weekly_position['entry_price'] - weekly_ltp) * config.ORDER_QUANTITY
        # PNL = (Current - Entry) for Buy side
        monthly_pnl = (monthly_ltp - self.monthly_position['entry_price']) * config.ORDER_QUANTITY
        
        total_pnl = weekly_pnl + monthly_pnl
        
        if total_pnl <= -abs(config.MAX_LOSS_VALUE):
            self.log(f"{Fore.RED}CRITICAL: Max Loss Hit ({total_pnl:.2f}).{Style.RESET_ALL}")
            self.exit_all_positions(order_callback, reason="MAX_LOSS")
            return True
        return False

    def exit_all_positions(self, order_callback, reason="MANUAL"):
        """
        Forcefully squares off all open legs.
        """
        self.log(f"{Fore.MAGENTA}INITIATING TOTAL STRATEGY EXIT: {reason}{Style.RESET_ALL}")
        
        if self.weekly_position and order_callback:
            resp = order_callback(self.weekly_position['instrument_key'], config.ORDER_QUANTITY, 'BUY', f'EXIT_{reason}', expiry=self.weekly_position.get('expiry_dt'))
            if resp and resp.get('status') == 'success':
                exit_price = resp.get('avg_price', 0.0)
                pnl = (self.weekly_position['entry_price'] - exit_price) * config.ORDER_QUANTITY
                self.journal.log_trade(self.weekly_position['instrument_key'], 'BUY', config.ORDER_QUANTITY, exit_price, f'EXIT_{reason}', expiry=self.weekly_position.get('expiry_dt'), pnl=pnl)
                self.log(f"Exited Weekly: {self.weekly_position['strike']} Put | Price: {exit_price} | PnL: {pnl:.2f}")
            
        if self.monthly_position and order_callback:
            resp = order_callback(self.monthly_position['instrument_key'], config.ORDER_QUANTITY, 'SELL', f'EXIT_{reason}', expiry=self.monthly_position.get('expiry_dt'))
            if resp and resp.get('status') == 'success':
                exit_price = resp.get('avg_price', 0.0)
                pnl = (exit_price - self.monthly_position['entry_price']) * config.ORDER_QUANTITY
                self.journal.log_trade(self.monthly_position['instrument_key'], 'SELL', config.ORDER_QUANTITY, exit_price, f'EXIT_{reason}', expiry=self.monthly_position.get('expiry_dt'), pnl=pnl)
                self.log(f"Exited Monthly: {self.monthly_position['strike']} Put | Price: {exit_price} | PnL: {pnl:.2f}")
            
        self.weekly_position = None
        self.monthly_position = None

    def get_open_pnl(self, weekly_ltp, monthly_ltp):
        """Calculates current unrealized P&L."""
        w_pnl = 0.0
        m_pnl = 0.0
        if self.weekly_position:
            w_pnl = (self.weekly_position['entry_price'] - weekly_ltp) * config.ORDER_QUANTITY
        if self.monthly_position:
            m_pnl = (monthly_ltp - self.monthly_position['entry_price']) * config.ORDER_QUANTITY
        return w_pnl + m_pnl

    def save_state(self):
        """Saves current state to persistent storage."""
        state = {
            'weekly': self.weekly_position,
            'monthly': self.monthly_position,
            'last_rollover_date': self.last_rollover_date
        }
        super().save_current_state(state)

    def load_previous_state(self):
        """Loads state from persistent storage."""
        state = super().load_previous_state()
        
        if state:
            self.weekly_position = state.get('weekly')
            self.monthly_position = state.get('monthly')
            self.last_rollover_date = state.get('last_rollover_date')  # Load rollover tracking
            if self.weekly_position or self.monthly_position:
                log_msg = f"{Fore.CYAN}RECOVERY: Loaded existing positions:{Style.RESET_ALL}"
                if self.weekly_position:
                    log_msg += f"\n  - Weekly: {self.weekly_position['strike']} Put (Expiry: {self.weekly_position.get('expiry_dt','N/A')})"
                if self.monthly_position:
                    log_msg += f"\n  - Monthly: {self.monthly_position['strike']} Put (Expiry: {self.monthly_position.get('expiry_dt','N/A')})"
                self.log(log_msg)
                return True
        return False

class WeeklyIronfly(BaseStrategy):
    def __init__(self, risk_free_rate=config.RISK_FREE_RATE):
        super().__init__("WeeklyIronfly")
        self.positions = [] # List of {'instrument_key': ..., 'qty': ..., 'side': ..., 'entry_price': ...}
        self.is_adjusted = False
        self.risk_free_rate = risk_free_rate
        self.journal = TradeJournal(filename="trade_log_ironfly.csv")

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        colored_message = message.replace("SOLD", f"{Fore.RED}SOLD{Style.RESET_ALL}").replace("BOUGHT", f"{Fore.GREEN}BOUGHT{Style.RESET_ALL}")
        entry = f"[{timestamp}] [{self.name}] {colored_message}"
        print(entry)

    def update(self, market_data, order_callback):
        spot_price = market_data.get('spot_price')
        now = market_data.get('now', datetime.now())
        quotes = market_data.get('quotes', {})
        
        # Mapping generic runner keys
        cw_chain = market_data.get('cw_chain', []) # Current Weekly (this week)
        nw_chain = market_data.get('nw_chain', []) # Next Weekly (positioned week)
        m_chain = market_data.get('m_chain', [])   # Monthly

        if not spot_price: return

        # 1. Check Exit Timing (Only if we have positions and today is THAT position's expiry)
        if self.positions:
            is_pos_expiry_today = False
            # Check if Leg 2 (Main short) is expiring today
            leg2 = next((p for p in self.positions if 'IF_LEG2' in p.get('tag', '')), None)
            if leg2:
                 q = quotes.get(leg2['instrument_key'])
                 # In a real environment, we'd check expiry_dt from master, 
                 # but here we can check if tte is very low in cw_chain
                 # For simplicity, we assume market_data.is_expiry_today refers to Nifty standard expiries
                 if market_data.get('is_expiry_today'):
                     # If we are in nw_chain week, market_data.is_expiry_today is True
                     is_pos_expiry_today = True

            if is_pos_expiry_today and now.strftime("%H:%M") >= config.IRONFLY_EXIT_TIME:
                self.log("EXPIRY EXIT: Target week expiry reached. Squaring off all.")
                self.exit_all_positions(order_callback, reason="EXPIRY_TIME_EXIT")
                self.save_state()
                return

        # 2. Check Entry Timing (Current week's expiry at 12:00 PM for NEXT week's expiry)
        if not self.positions:
            is_paper = config.TRADING_MODE == 'PAPER'
            expiry_skipped = market_data.get('expiry_skipped', False)
            
            # In LIVE mode, check if today is current week's expiry (to enter for next week)
            is_entry_day = False
            current_weekly_expiry_str = 'N/A'
            next_weekly_expiry_str = 'N/A'
            
            if cw_chain:
                current_weekly_expiry_str = cw_chain[0].get('expiry_dt', 'N/A')
                try:
                    current_weekly_expiry = datetime.strptime(current_weekly_expiry_str, '%Y-%m-%d').date()
                    is_entry_day = (now.date() == current_weekly_expiry)
                except:
                    is_entry_day = (now.weekday() == config.IRONFLY_ENTRY_WEEKDAY)
            else:
                is_entry_day = (now.weekday() == config.IRONFLY_ENTRY_WEEKDAY)
            
            if nw_chain:
                next_weekly_expiry_str = nw_chain[0].get('expiry_dt', 'N/A')
            
            is_entry_time = now.strftime("%H:%M") >= config.IRONFLY_ENTRY_TIME
            
            # If we skipped today's expiry, the main weekly (cw_chain) is already the next contract.
            # We allow entry immediately as today IS technically an expiry day (just the skipped one).
            if is_paper or (is_entry_day and is_entry_time) or expiry_skipped:
                target_chain = cw_chain if expiry_skipped else nw_chain
                self.log(f"Ironfly Entry Triggered | Expiry Skipped: {expiry_skipped} | Targeting: {target_chain[0]['expiry_dt'] if target_chain else 'N/A'}")
                self.enter_strategy(spot_price, target_chain, order_callback)
                self.save_state()
            else:
                if now.second < 10 and now.minute % 5 == 0: # Log every 5 mins in the first 10s
                    if config.TRADING_MODE == 'LIVE':
                        self.log(f"{Fore.YELLOW}[LIVE MODE] WAITING: Entry allowed on current weekly expiry ({current_weekly_expiry_str}) at {config.IRONFLY_ENTRY_TIME} for next week ({next_weekly_expiry_str}). Today is {now.strftime('%Y-%m-%d %H:%M')}.{Style.RESET_ALL}")
                    else:
                        self.log(f"WAITING: Entry window opens at {config.IRONFLY_ENTRY_TIME}")

        # 3. Monitor PNL and Adjustments
        if self.positions:
            total_pnl = self.calculate_total_pnl(quotes)
            pnl_pct = total_pnl / config.IRONFLY_CAPITAL
            
            # PnL Summary Logging
            strategy_state = {
                'positions': []
            }
            for pos in self.positions:
                q = quotes.get(pos['instrument_key'])
                ltp = getattr(q, 'last_price', 'N/A') if q else 'N/A'
                strategy_state['positions'].append({**pos, 'ltp': ltp})
            
            self.journal.print_summary(total_pnl, strategy_state)

            # Target Hit
            if pnl_pct >= config.IRONFLY_TARGET_PERCENT:
                self.log(f"TARGET HIT: {pnl_pct*100:.2f}% profit. Exiting.")
                self.exit_all_positions(order_callback, reason="TARGET_HIT")
                self.save_state()
            
            # SL / Adjustment Trigger
            elif pnl_pct <= -config.IRONFLY_SL_PERCENT:
                if not self.is_adjusted:
                    if market_data.get('can_adjust', True):
                        self.log(f"ADJUSTMENT TRIGGER: {pnl_pct*100:.2f}% loss. Building Call Calendar.")
                    # Build Calendar: Sell CE at butterfly expiry (nw_chain), Buy CE at next expiry (cw_chain of following week)
                    # Note: We need to fetch the week AFTER nw_chain for the long Call
                    # For now, we'll use cw_chain as the next week relative to nw_chain
                    self.apply_adjustment(spot_price, nw_chain, cw_chain, order_callback)
                    self.save_state()
                else:
                    self.log(f"STOP LOSS HIT: {pnl_pct*100:.2f}% loss (post-adjustment). Exiting.")
                    self.exit_all_positions(order_callback, reason="POST_ADJ_SL_HIT")
                    self.save_state()

    def enter_strategy(self, spot, weekly_chain, order_callback):
        """
        Atomic entry for Put Butterfly:
        - Buy 1 Put at ATM-50
        - Sell 2 Puts at ATM-250  
        - Buy 1 Put at ATM-450
        """
        atm = round(spot / 50) * 50
        strikes = [
            atm + config.IRONFLY_LEG1_OFFSET,  # ATM-50
            atm + config.IRONFLY_LEG2_OFFSET,  # ATM-250
            atm + config.IRONFLY_LEG3_OFFSET   # ATM-450
        ]
        sides = ['BUY', 'SELL', 'BUY']
        qtys = [config.ORDER_QUANTITY, config.ORDER_QUANTITY * 2, config.ORDER_QUANTITY]
        tags = ['IF_LEG1', 'IF_LEG2', 'IF_LEG3']

        self.log(f"Constructing Put Butterfly @ Spot {spot:.2f} | ATM: {atm}")
        self.log(f"Target Strikes: Leg1={strikes[0]} (Buy 1), Leg2={strikes[1]} (Sell 2), Leg3={strikes[2]} (Buy 1)")
        
        # ATOMIC CHECK: Verify all legs exist in chain before placing any orders
        legs_data = []
        for i, strike in enumerate(strikes):
            opt = next((x for x in weekly_chain if x['strike'] == strike and x['type'] == 'p'), None)
            if not opt:
                self.log(f"ERROR: Cannot find Put option for Leg {i+1} at strike {strike}. Aborting entry.")
                return
            legs_data.append(opt)
        
        self.log("All legs validated. Executing orders...")
        
        # Execute all legs
        for i, (opt, side, qty, tag) in enumerate(zip(legs_data, sides, qtys, tags)):
            resp = order_callback(opt['instrument_key'], qty, side, tag, expiry=opt.get('expiry_dt'))
            if resp and resp.get('status') == 'success':
                price = resp.get('avg_price', opt.get('ltp', 0))
                self.positions.append({
                    'instrument_key': opt['instrument_key'],
                    'qty': qty,
                    'side': side,
                    'entry_price': price,
                    'strike': opt['strike'],
                    'type': 'PE',
                    'tag': tag,
                    'expiry_dt': opt.get('expiry_dt', 'N/A')  # Add expiry date
                })
                self.journal.log_trade(opt['instrument_key'], side, qty, price, tag, expiry=opt.get('expiry_dt'))
            else:
                self.log(f"CRITICAL ERROR: Leg {i+1} order failed. Strategy may be incomplete!")
        
        if len(self.positions) == 3:
            self.log(f"{Fore.GREEN}Put Butterfly construction COMPLETE.{Style.RESET_ALL}")
        else:
            self.log(f"{Fore.RED}WARNING: Only {len(self.positions)}/3 legs executed!{Style.RESET_ALL}")

    def apply_adjustment(self, spot, current_week_chain, next_week_chain, order_callback):
        """
        Apply Call Calendar adjustment when market moves against Put Butterfly.
        
        Strategy: Move 100 points inward from Leg 1, then:
        - Sell Call at adjustment strike (same expiry as butterfly)
        - Buy Call at adjustment strike (next week's expiry)
        
        Example: If Leg 1 = Buy PE 25900
                 Adjustment strike = 25900 + 100 = 26000
                 Sell 1 CE 26000 (this week)
                 Buy 1 CE 26000 (next week)
        """
        # Check if next week data is available
        if not next_week_chain or len(next_week_chain) == 0:
            self.log(f"{Fore.RED}ERROR: Next week option data not available for adjustment. Skipping.{Style.RESET_ALL}")
            return
        
        # Move 100 points inward (higher strike for Puts) from Leg 1
        leg1 = next((p for p in self.positions if 'IF_LEG1' in p.get('tag', '')), None)
        if not leg1: 
            # Fallback if tags missing
            leg1 = self.positions[0] if self.positions else None
        
        if not leg1: return

        adj_strike = leg1['strike'] + config.IRONFLY_ADJ_INWARD_OFFSET
        
        self.log(f"Adjustment: Leg 1 strike = {leg1['strike']}, Moving +100 inward → {adj_strike}")
        
        # Find Call options at adjustment strike
        # Sell: Same expiry as butterfly (current_week_chain)
        # Buy: Next week's expiry (next_week_chain)
        ce_this_week = next((x for x in current_week_chain if x['strike'] == adj_strike and x['type'] == 'c'), None)
        ce_next_week = next((x for x in next_week_chain if x['strike'] == adj_strike and x['type'] == 'c'), None)

        if ce_this_week and ce_next_week:
            self.log(f"Executing Call Calendar @ Strike {adj_strike}")
            self.log(f"  → Sell CE {adj_strike} (This Week)")
            self.log(f"  → Buy CE {adj_strike} (Next Week)")
            
            # Sell This Week CE
            resp_w = order_callback(ce_this_week['instrument_key'], config.ORDER_QUANTITY, 'SELL', 'IF_ADJ_CE_SHORT', expiry=ce_this_week.get('expiry_dt'))
            # Buy Next Week CE
            resp_n = order_callback(ce_next_week['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'IF_ADJ_CE_LONG', expiry=ce_next_week.get('expiry_dt'))
            
            if resp_w and resp_w.get('status') == 'success':
                price_w = resp_w.get('avg_price', ce_this_week.get('ltp', 0))
                self.positions.append({
                    'instrument_key': ce_this_week['instrument_key'],
                    'qty': config.ORDER_QUANTITY,
                    'side': 'SELL',
                    'entry_price': price_w,
                    'strike': adj_strike,
                    'type': 'CE',
                    'tag': 'IF_ADJ_CE_SHORT',
                    'expiry_dt': ce_this_week.get('expiry_dt', 'N/A')
                })
                self.journal.log_trade(ce_this_week['instrument_key'], 'SELL', config.ORDER_QUANTITY, price_w, 'IF_ADJ_CE_SHORT', expiry=ce_this_week.get('expiry_dt'))
            
            if resp_n and resp_n.get('status') == 'success':
                price_n = resp_n.get('avg_price', ce_next_week.get('ltp', 0))
                self.positions.append({
                    'instrument_key': ce_next_week['instrument_key'],
                    'qty': config.ORDER_QUANTITY,
                    'side': 'BUY',
                    'entry_price': price_n,
                    'strike': adj_strike,
                    'type': 'CE',
                    'tag': 'IF_ADJ_CE_LONG',
                    'expiry_dt': ce_next_week.get('expiry_dt', 'N/A')
                })
                self.journal.log_trade(ce_next_week['instrument_key'], 'BUY', config.ORDER_QUANTITY, price_n, 'IF_ADJ_CE_LONG', expiry=ce_next_week.get('expiry_dt'))
            
            self.is_adjusted = True
            self.log("Call Calendar Adjustment deployed.")
        else:
            self.log(f"ERROR: Could not find CE instruments for adjustment at strike {adj_strike}")
            if not ce_this_week:
                self.log(f"  Missing: CE {adj_strike} (This Week)")
            if not ce_next_week:
                self.log(f"  Missing: CE {adj_strike} (Next Week)")

    def calculate_total_pnl(self, quotes):
        pnl = 0
        for pos in self.positions:
            q = quotes.get(pos['instrument_key'])
            ltp = getattr(q, 'last_price', pos['entry_price']) if q else pos['entry_price']
            if pos['side'] == 'BUY':
                pnl += (ltp - pos['entry_price']) * pos['qty']
            else:
                pnl += (pos['entry_price'] - ltp) * pos['qty']
        return pnl

    def exit_all_positions(self, order_callback, reason):
        for pos in self.positions:
            exit_side = 'SELL' if pos['side'] == 'BUY' else 'BUY'
            order_callback(pos['instrument_key'], pos['qty'], exit_side, f"{reason}_EXIT", expiry=pos.get('expiry_dt'))
        self.positions = []
        self.is_adjusted = False

    def save_state(self):
        super().save_current_state({'positions': self.positions, 'is_adjusted': self.is_adjusted})

    def load_previous_state(self):
        state = super().load_previous_state()
        if state:
            self.positions = state.get('positions', [])
            self.is_adjusted = state.get('is_adjusted', False)
            if self.positions:
                self.log(f"{Fore.CYAN}RECOVERY: Loaded {len(self.positions)} existing positions.{Style.RESET_ALL}")
            return True
        return False

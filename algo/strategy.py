import config
from datetime import datetime
from greeks import calculate_delta, get_atm_strike
from colorama import init, Fore, Style
from trade_logger import TradeJournal

# Initialize colorama for Windows support
init(autoreset=True)

class NiftyStrategy:
    def __init__(self, risk_free_rate=config.RISK_FREE_RATE):
        # State
        self.weekly_position = None  # {'type': 'sell', 'strike': K, 'expiry': T, 'entry_price': P, 'delta': D}
        self.monthly_position = None # {'type': 'buy',  'strike': K, 'expiry': T, 'entry_price': P, 'delta': D}
        
        self.risk_free_rate = risk_free_rate
        self.logs = []
        self.journal = TradeJournal()

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Color specific keywords in message
        colored_message = message.replace("SOLD", f"{Fore.RED}SOLD{Style.RESET_ALL}")
        colored_message = colored_message.replace("BOUGHT", f"{Fore.GREEN}BOUGHT{Style.RESET_ALL}")
        colored_message = colored_message.replace("ENTRY", f"{Fore.YELLOW}ENTRY{Style.RESET_ALL}")
        colored_message = colored_message.replace("ADJUSTMENT", f"{Fore.MAGENTA}ADJUSTMENT{Style.RESET_ALL}")
        
        # Color Dates (Approximate Regex or keyword based)
        import re
        date_pattern = r"(\d{4}-\d{2}-\d{2})"
        colored_message = re.sub(date_pattern, rf"{Fore.CYAN}\1{Style.RESET_ALL}", colored_message)

        entry = f"[{timestamp}] {colored_message}"
        print(entry)
        self.logs.append(entry)

    def select_strike_by_delta(self, spot, chain, target_delta, option_type='p', tolerance=0.1):
        """
        Finds a strike in the option chain closest to the target delta.
        chain: list of dicts {'strike': K, 'iv': sigma, 'expiry': t_years}
        """
        best_strike = None
        min_diff = float('inf')
        
        for opt in chain:
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
                best_strike = opt
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
            resp_w = order_callback(weekly_leg['instrument_key'], config.ORDER_QUANTITY, 'SELL', 'WEEKLY_ENTRY')
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
                    'entry_price': entry_price
                }
                self.journal.log_trade(weekly_leg['instrument_key'], 'SELL', config.ORDER_QUANTITY, entry_price, 'WEEKLY_ENTRY')
                self.log(f"ENTRY: SOLD Weekly Put | Strike: {weekly_leg['strike']} | Price: {entry_price} | Expiry: {weekly_leg['expiry_dt']} | Delta: {weekly_leg['calculated_delta']:.2f}")
            else:
                self.log(f"CRITICAL ERROR: Weekly Sell Order FAILED. Reason: {resp_w.get('message') if isinstance(resp_w, dict) else 'Unknown'}")
                return

            # Buy Monthly
            resp_m = order_callback(monthly_leg['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'MONTHLY_ENTRY')
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
                    'entry_price': entry_price_m
                }
                self.journal.log_trade(monthly_leg['instrument_key'], 'BUY', config.ORDER_QUANTITY, entry_price_m, 'MONTHLY_ENTRY')
                self.log(f"ENTRY: BOUGHT Monthly Put | Strike: {monthly_leg['strike']} | Price: {entry_price_m} | Expiry: {monthly_leg['expiry_dt']} | Delta: {monthly_leg['calculated_delta']:.2f}")
            else:
                self.log(f"CRITICAL ERROR: Monthly Buy Order FAILED. Reason: {resp_m.get('message') if isinstance(resp_m, dict) else 'Unknown'}")
                # EMERGENCY: Weekly was sold, but Monthly failed. Must square off Weekly immediately!
                self.log("EMERGENCY: Squaring off Weekly leg to prevent naked position.")
                resp_exit = order_callback(weekly_leg['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'EMERGENCY_EXIT')
                exit_price = resp_exit.get('avg_price', 0.0)
                pnl = (self.weekly_position['entry_price'] - exit_price) * config.ORDER_QUANTITY
                self.journal.log_trade(weekly_leg['instrument_key'], 'BUY', config.ORDER_QUANTITY, exit_price, 'EMERGENCY_EXIT', pnl=pnl)
                self.weekly_position = None
                return
        else:
            self.log("DEV NOTE: No order_callback provided, entry skipped.")

    def update_deltas(self, spot, current_time_to_expiry_weekly, current_time_to_expiry_monthly, weekly_iv, monthly_iv):
        """
        Re-calculate deltas for existing positions based on new spot/time/iv
        """
        if self.weekly_position:
            d = calculate_delta('p', spot, self.weekly_position['strike'], current_time_to_expiry_weekly, self.risk_free_rate, weekly_iv)
            self.weekly_position['delta'] = abs(d)
            # update expiry/iv references if provided dynamic
            self.weekly_position['expiry'] = current_time_to_expiry_weekly
        
        if self.monthly_position:
            d = calculate_delta('p', spot, self.monthly_position['strike'], current_time_to_expiry_monthly, self.risk_free_rate, monthly_iv)
            self.monthly_position['delta'] = abs(d)
            self.monthly_position['expiry'] = current_time_to_expiry_monthly

    def check_adjustments(self, spot, weekly_chain, monthly_chain, order_callback=None):
        """
        Logic 3: Adjustment
        """
        if not self.weekly_position or not self.monthly_position:
            return

        # 1. Weekly Put (Sell Leg) Adjustments
        # On a Market Fall: If delta increases to 0.80
        if self.weekly_position['delta'] >= config.WEEKLY_ADJ_TRIGGER_DELTA:
            self.log(f"WEEKLY ADJ (FALL): Delta is {self.weekly_position['delta']:.2f} >= {config.WEEKLY_ADJ_TRIGGER_DELTA}")
            self.adjust_weekly_leg(spot, weekly_chain, order_callback)

        # On a Market Rise: If delta drops to 0.10 or below
        elif self.weekly_position['delta'] <= config.WEEKLY_ADJ_TRIGGER_DELTA_LOW:
            self.log(f"WEEKLY ADJ (RISE): Delta is {self.weekly_position['delta']:.2f} <= {config.WEEKLY_ADJ_TRIGGER_DELTA_LOW}")
            self.adjust_weekly_leg(spot, weekly_chain, order_callback)

        # 2. Next-Month Put (Buy Leg) Adjustments
        # On a Sharp Market Fall: If delta reaches 0.90
        if self.monthly_position['delta'] >= config.MONTHLY_ADJ_TRIGGER_DELTA:
            self.log(f"MONTHLY ADJ (FALL): Delta is {self.monthly_position['delta']:.2f} >= {config.MONTHLY_ADJ_TRIGGER_DELTA}")
            self.adjust_monthly_leg(spot, monthly_chain, config.MONTHLY_ROLL_TARGET_DELTA_FALL, order_callback)

        # On a Sharp Market Rise: If delta drops to 0.10
        elif self.monthly_position['delta'] <= config.MONTHLY_ADJ_TRIGGER_DELTA_LOW:
            self.log(f"MONTHLY ADJ (RISE): Delta is {self.monthly_position['delta']:.2f} <= {config.MONTHLY_ADJ_TRIGGER_DELTA_LOW}")
            self.adjust_monthly_leg(spot, monthly_chain, config.MONTHLY_ROLL_TARGET_DELTA_RISE, order_callback)

    def adjust_weekly_leg(self, spot, chain, order_callback):
        # 1. Select New Leg first to ensure we have a target
        new_leg = self.select_strike_by_delta(spot, chain, config.WEEKLY_ROLL_TARGET_DELTA)
        if not new_leg:
            self.log("ERROR: Could not find suitable new Weekly strike for adjustment. Skipping.")
            return

        # 2. Exit Existing
        if order_callback and self.weekly_position and 'instrument_key' in self.weekly_position:
            resp_exit = order_callback(self.weekly_position['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'WEEKLY_EXIT_ADJ')
            if (resp_exit and resp_exit.get('status') == 'success'):
                # PNL = (Entry - Exit) for Sell side
                exit_price = resp_exit.get('avg_price', 0.0)
                pnl = (self.weekly_position['entry_price'] - exit_price) * config.ORDER_QUANTITY
                self.journal.log_trade(self.weekly_position['instrument_key'], 'BUY', config.ORDER_QUANTITY, exit_price, 'WEEKLY_EXIT_ADJ', pnl=pnl)
            else:
                self.log(f"CRITICAL ERROR: Weekly Exit Order FAILED. Aborting adjustment to prevent double selling. Reason: {resp_exit.get('message') if isinstance(resp_exit, dict) else 'Unknown'}")
                return
        
        old_key = self.weekly_position['instrument_key'] if self.weekly_position else "None"
        self.weekly_position = None
        
        # 3. Enter New
        if order_callback:
            resp_entry = order_callback(new_leg['instrument_key'], config.ORDER_QUANTITY, 'SELL', 'WEEKLY_ROLL_ENTRY')
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
                    'entry_price': entry_price
                }
                self.journal.log_trade(new_leg['instrument_key'], 'SELL', config.ORDER_QUANTITY, entry_price, 'WEEKLY_ROLL_ENTRY')
                self.log(f"ADJUSTMENT ENTRY: SOLD Weekly ATM Put | Strike: {new_leg['strike']} | Price: {entry_price} | Expiry: {new_leg['expiry_dt']} | Delta: {new_leg['calculated_delta']:.2f}")
            else:
                self.log(f"CRITICAL ERROR: Weekly Roll Entry FAILED. Currently NAKED (Exited {old_key}). Reason: {resp_entry.get('message') if isinstance(resp_entry, dict) else 'Unknown'}")

    def adjust_monthly_leg(self, spot, chain, target_delta, order_callback):
        # 1. Select New Leg
        new_leg = self.select_strike_by_delta(spot, chain, target_delta)
        if not new_leg:
            self.log("ERROR: Could not find suitable new Monthly strike for adjustment. Skipping.")
            return

        # 2. Exit Existing
        if order_callback and self.monthly_position and 'instrument_key' in self.monthly_position:
            resp_exit = order_callback(self.monthly_position['instrument_key'], config.ORDER_QUANTITY, 'SELL', 'MONTHLY_EXIT_ADJ')
            if (resp_exit and resp_exit.get('status') == 'success'):
                # PNL = (Exit - Entry) for Buy side
                exit_price = resp_exit.get('avg_price', 0.0)
                pnl = (exit_price - self.monthly_position['entry_price']) * config.ORDER_QUANTITY
                self.journal.log_trade(self.monthly_position['instrument_key'], 'SELL', config.ORDER_QUANTITY, exit_price, 'MONTHLY_EXIT_ADJ', pnl=pnl)
            else:
                self.log(f"CRITICAL ERROR: Monthly Exit Order FAILED. Aborting adjustment. Reason: {resp_exit.get('message') if isinstance(resp_exit, dict) else 'Unknown'}")
                return
             
        old_key = self.monthly_position['instrument_key'] if self.monthly_position else "None"
        self.monthly_position = None
        
        # 3. Enter New
        if order_callback:
            resp_entry = order_callback(new_leg['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'MONTHLY_ROLL_ENTRY')
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
                    'entry_price': entry_price
                }
                self.journal.log_trade(new_leg['instrument_key'], 'BUY', config.ORDER_QUANTITY, entry_price, 'MONTHLY_ROLL_ENTRY')
                self.log(f"ADJUSTMENT ENTRY: BOUGHT Monthly Put | Strike: {new_leg['strike']} | Price: {entry_price} | Expiry: {new_leg['expiry_dt']} | Delta: {new_leg['calculated_delta']:.2f}")
            else:
                self.log(f"CRITICAL ERROR: Monthly Roll Entry FAILED. Currently UNHEDGED (Exited {old_key}). Reason: {resp_entry.get('message') if isinstance(resp_entry, dict) else 'Unknown'}")

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
        loss_limit = -abs(config.MAX_LOSS_VALUE)
        
        if total_pnl <= loss_limit:
            self.log(f"{Fore.RED}CRITICAL: Max Loss Hit ({total_pnl:.2f}). EXITING ALL POSITIONS.{Style.RESET_ALL}")
            if order_callback:
                # Square off Weekly (Buy back)
                order_callback(self.weekly_position['instrument_key'], config.ORDER_QUANTITY, 'BUY', 'MAX_LOSS_EXIT')
                # Square off Monthly (Sell)
                order_callback(self.monthly_position['instrument_key'], config.ORDER_QUANTITY, 'SELL', 'MAX_LOSS_EXIT')
                
            self.weekly_position = None
            self.monthly_position = None
            return True
        return False

    def exit_all_positions(self, order_callback, reason="MANUAL"):
        """
        Forcefully squares off all open legs.
        """
        self.log(f"{Fore.MAGENTA}INITIATING TOTAL STRATEGY EXIT: {reason}{Style.RESET_ALL}")
        
        if self.weekly_position and order_callback:
            resp = order_callback(self.weekly_position['instrument_key'], config.ORDER_QUANTITY, 'BUY', f'EXIT_{reason}')
            if resp and resp.get('status') == 'success':
                exit_price = resp.get('avg_price', 0.0)
                pnl = (self.weekly_position['entry_price'] - exit_price) * config.ORDER_QUANTITY
                self.journal.log_trade(self.weekly_position['instrument_key'], 'BUY', config.ORDER_QUANTITY, exit_price, f'EXIT_{reason}', pnl=pnl)
                self.log(f"Exited Weekly: {self.weekly_position['strike']} Put | Exit Price: {exit_price} | PnL: {pnl:.2f}")
            
        if self.monthly_position and order_callback:
            resp = order_callback(self.monthly_position['instrument_key'], config.ORDER_QUANTITY, 'SELL', f'EXIT_{reason}')
            if resp and resp.get('status') == 'success':
                exit_price = resp.get('avg_price', 0.0)
                pnl = (exit_price - self.monthly_position['entry_price']) * config.ORDER_QUANTITY
                self.journal.log_trade(self.monthly_position['instrument_key'], 'SELL', config.ORDER_QUANTITY, exit_price, f'EXIT_{reason}', pnl=pnl)
                self.log(f"Exited Monthly: {self.monthly_position['strike']} Put | Exit Price: {exit_price} | PnL: {pnl:.2f}")
            
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

    def save_current_state(self):
        """Saves current state to persistent storage."""
        self.journal.save_state(self.weekly_position, self.monthly_position)

    def load_previous_state(self):
        """Loads state from persistent storage."""
        state = self.journal.load_state()
        if state:
            self.weekly_position = state.get('weekly')
            self.monthly_position = state.get('monthly')
            if self.weekly_position or self.monthly_position:
                self.log(f"{Fore.CYAN}RECOVERY: Loaded existing positions from strategy_state.json{Style.RESET_ALL}")
                return True
        return False

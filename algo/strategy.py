import config
from greeks import calculate_delta, get_atm_strike

class NiftyStrategy:
    def __init__(self, risk_free_rate=config.RISK_FREE_RATE):
        # State
        self.weekly_position = None  # {'type': 'sell', 'strike': K, 'expiry': T, 'entry_price': P, 'delta': D}
        self.monthly_position = None # {'type': 'buy',  'strike': K, 'expiry': T, 'entry_price': P, 'delta': D}
        
        self.risk_free_rate = risk_free_rate
        self.logs = []

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}"
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
        self.log(f"Attempting Entry at Spot: {spot}")
        
        # 1. Sell Weekly ATM Put (Target Delta 0.5)
        # ATM Put is usually around 0.5 Delta. 
        atm_strike = get_atm_strike(spot)
        
        # Find specific option in chain matching ATM or Delta ~0.5
        # For simplicity, let's try to find the one closest to 0.5
        weekly_leg = self.select_strike_by_delta(spot, weekly_chain, config.ENTRY_WEEKLY_DELTA_TARGET)
        
        if weekly_leg:
            self.weekly_position = {
                'leg': 'weekly_sell',
                'strike': weekly_leg['strike'],
                'expiry': weekly_leg['time_to_expiry'], # years
                'iv': weekly_leg['iv'],
                'delta': weekly_leg['calculated_delta'],
                'entry_spot': spot,
                'instrument_key': weekly_leg['instrument_key']
            }
            self.log(f"ENTRY: SOLD Weekly Put | Strike: {weekly_leg['strike']} | Delta: {weekly_leg['calculated_delta']:.2f}")
            if order_callback:
                order_callback(weekly_leg['instrument_key'], 50, 'SELL', 'WEEKLY_ENTRY')
        else:
            self.log("ERROR: Could not find suitable Weekly strike")

        # 2. Buy Monthly ATM Put (Hedge, Target Delta ~0.5)
        monthly_leg = self.select_strike_by_delta(spot, monthly_chain, config.ENTRY_MONTHLY_DELTA_TARGET)
        
        if monthly_leg:
            self.monthly_position = {
                'leg': 'monthly_buy',
                'strike': monthly_leg['strike'],
                'expiry': monthly_leg['time_to_expiry'],
                'iv': monthly_leg['iv'],
                'delta': monthly_leg['calculated_delta'],
                'entry_spot': spot,
                'instrument_key': monthly_leg['instrument_key']
            }
            self.log(f"ENTRY: BOUGHT Monthly Put | Strike: {monthly_leg['strike']} | Delta: {monthly_leg['calculated_delta']:.2f}")
            if order_callback:
                order_callback(monthly_leg['instrument_key'], 50, 'BUY', 'MONTHLY_ENTRY')
        else:
            self.log("ERROR: Could not find suitable Monthly strike")

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

        # 3a. Weekly Adjustment: Delta > Trigger
        if self.weekly_position['delta'] >= config.WEEKLY_ADJ_TRIGGER_DELTA:
            self.log(f"ADJUSTMENT ALERT: Weekly Sell Put Delta is {self.weekly_position['delta']:.2f} (>= {config.WEEKLY_ADJ_TRIGGER_DELTA}). Strong downside.")
            # Action: Exit Existing, Sell Fresh ATM
            old_strike = self.weekly_position['strike']
            
            # Simulate Exit
            self.log(f"EXIT: Closed Weekly Sell Put {old_strike}")
            if order_callback and 'instrument_key' in self.weekly_position:
                 # Closing a SELL position -> BUY back
                 order_callback(self.weekly_position['instrument_key'], 50, 'BUY', 'WEEKLY_EXIT_ADJ')
            
            self.weekly_position = None # Cleared
            
            # Sell Fresh ATM
            # We need to find the new ATM strike from the passed chain
            # Since we need "Fresh ATM", we default to target delta 0.50 roughly or pure ATM
            new_leg = self.select_strike_by_delta(spot, weekly_chain, config.WEEKLY_ROLL_TARGET_DELTA)
            if new_leg:
                self.weekly_position = {
                    'leg': 'weekly_sell',
                    'strike': new_leg['strike'],
                    'expiry': new_leg['time_to_expiry'],
                    'iv': new_leg['iv'],
                    'delta': new_leg['calculated_delta'],
                    'entry_spot': spot,
                    'instrument_key': new_leg['instrument_key']
                }
                self.log(f"ADJUSTMENT ENTRY: SOLD FRESH Weekly ATM Put | Strike: {new_leg['strike']} | Delta: {new_leg['calculated_delta']:.2f}")
                if order_callback:
                    order_callback(new_leg['instrument_key'], 50, 'SELL', 'WEEKLY_ROLL_ENTRY')

        # 3b. Monthly Adjustment: Delta > Trigger
        if self.monthly_position['delta'] > config.MONTHLY_ADJ_TRIGGER_DELTA:
            self.log(f"ADJUSTMENT ALERT: Monthly Buy Put Delta is {self.monthly_position['delta']:.2f} (> {config.MONTHLY_ADJ_TRIGGER_DELTA}). Deep ITM.")
            # Action: Exit Monthly Put
            old_strike = self.monthly_position['strike']
            self.log(f"EXIT: Closed Monthly Buy Put {old_strike}")
            if order_callback and 'instrument_key' in self.monthly_position:
                 # Closing a BUY position -> SELL off
                 order_callback(self.monthly_position['instrument_key'], 50, 'SELL', 'MONTHLY_EXIT_ADJ')
                 
            self.monthly_position = None
            
            # Buy Put with Target Delta
            new_leg = self.select_strike_by_delta(spot, monthly_chain, config.MONTHLY_ROLL_TARGET_DELTA)
            
            if new_leg:
                self.monthly_position = {
                    'leg': 'monthly_buy',
                    'strike': new_leg['strike'],
                    'expiry': new_leg['time_to_expiry'],
                    'iv': new_leg['iv'],
                    'delta': new_leg['calculated_delta'],
                    'entry_spot': spot,
                    'instrument_key': new_leg['instrument_key']
                }
                self.log(f"ADJUSTMENT ENTRY: BOUGHT New Monthly Put (Delta ~0.35) | Strike: {new_leg['strike']} | Delta: {new_leg['calculated_delta']:.2f}")
                if order_callback:
                    order_callback(new_leg['instrument_key'], 50, 'BUY', 'MONTHLY_ROLL_ENTRY')


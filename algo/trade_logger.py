import csv
import os
import json
from datetime import datetime
from colorama import Fore, Style
import config

class TradeJournal:
    def __init__(self, filename="trade_log.csv"):
        # Add trading mode to filename
        mode = config.TRADING_MODE.lower()
        # Insert mode before .csv extension
        base_name = filename.replace('.csv', '')
        self.filename = f"{base_name}_{mode}.csv"
        self.headers = ['timestamp', 'instrument_key', 'side', 'qty', 'price', 'expiry', 'tag', 'pnl']
        self._initialize_file()
        self.closed_pnl = 0.0
        self._calculate_fixed_pnl()

    def _initialize_file(self):
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writeheader()

    def _calculate_fixed_pnl(self):
        """Pre-calculate P&L from historical closed trades if file exists."""
        # Simple implementation: sum of all 'pnl' columns that are numeric
        try:
            with open(self.filename, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['pnl'] and row['pnl'] != 'None':
                        self.closed_pnl += float(row['pnl'])
        except Exception:
            pass

    def log_trade(self, instrument_key, side, qty, price, tag, expiry='N/A', pnl=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.headers)
            writer.writerow({
                'timestamp': timestamp,
                'instrument_key': instrument_key,
                'side': side,
                'qty': qty,
                'price': price,
                'expiry': expiry,
                'tag': tag,
                'pnl': pnl
            })
        if pnl is not None:
            self.closed_pnl += pnl

    def print_summary(self, open_pnl, strategy_state):
        total_pnl = self.closed_pnl + open_pnl
        pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
        
        print("\n" + "="*50)
        print(f"{Fore.CYAN}TRADE SESSION SUMMARY{Style.RESET_ALL}")
        print("="*50)
        print(f"Closed P&L:    {Fore.WHITE}INR {self.closed_pnl:,.2f}{Style.RESET_ALL}")
        print(f"Open P&L:      {Fore.WHITE}INR {open_pnl:,.2f}{Style.RESET_ALL}")
        print(f"Total P&L:     {pnl_color}INR {total_pnl:,.2f}{Style.RESET_ALL}")
        print("-" * 50)
        
        if strategy_state.get('weekly'):
            w = strategy_state['weekly']
            inst_type = 'Call' if w.get('type') == 'c' else 'Put'
            # Robust expiry display
            expiry_val = w.get('expiry_dt') or w.get('expiry', 'N/A')
            if isinstance(expiry_val, float):
                expiry_str = f"T~{expiry_val:.4f}y"
            else:
                expiry_str = str(expiry_val)
                
            strike = w.get('strike', 'N/A')
            entry = w.get('entry_price', 'N/A')
            ltp_raw = strategy_state.get('weekly_ltp')
            ltp = f"{ltp_raw:,.2f}" if ltp_raw is not None else "N/A"
            print(f"OPEN Weekly:   {Fore.YELLOW}{strike} {inst_type}{Style.RESET_ALL} @ {entry} (Expiry: {expiry_str} | Current: {ltp})")
            
        if strategy_state.get('monthly'):
            m = strategy_state['monthly']
            inst_type = 'Call' if m.get('type') == 'c' else 'Put'
            # Robust expiry display
            expiry_val = m.get('expiry_dt') or m.get('expiry', 'N/A')
            if isinstance(expiry_val, float):
                expiry_str = f"T~{expiry_val:.4f}y"
            else:
                expiry_str = str(expiry_val)
                
            strike = m.get('strike', 'N/A')
            entry = m.get('entry_price', 'N/A')
            ltp_raw = strategy_state.get('monthly_ltp')
            ltp = f"{ltp_raw:,.2f}" if ltp_raw is not None else "N/A"
            print(f"OPEN Monthly:  {Fore.YELLOW}{strike} {inst_type}{Style.RESET_ALL} @ {entry} (Expiry: {expiry_str} | Current: {ltp})")
        
        # Generic Position Support
        if strategy_state.get('positions'):
            # Extract expiry date from first position for header
            first_pos = strategy_state['positions'][0] if strategy_state['positions'] else {}
            expiry_info = first_pos.get('expiry_dt', 'N/A')
            
            print("-" * 25 + f" Open Legs (Expiry: {expiry_info}) " + "-" * 25)
            for p in strategy_state['positions']:
                side_col = Fore.GREEN if p['side'] == 'BUY' else Fore.RED
                qty = p['qty']
                entry = p['entry_price']
                ltp_raw = p.get('ltp')
                ltp = f"{ltp_raw:,.2f}" if isinstance(ltp_raw, (int, float)) else "N/A"
                
                # Calculate "Points" (Normalized to standard lot for easy strategy review)
                # If QTY=150 and Lot=75, multiplier is 2. Multiplier * Price = Points.
                multiplier = qty / config.ORDER_QUANTITY
                net_points_entry = entry * multiplier
                net_points_ltp = ltp_raw * multiplier if isinstance(ltp_raw, (int, float)) else 0.0
                
                print(f"{side_col}{p['side']} {qty} {p.get('type','')} {p.get('strike','')} @ {entry}{Style.RESET_ALL} "
                      f"(LTP: {ltp} | Net Points: {net_points_ltp:.2f})")
        
        print("="*50 + "\n")

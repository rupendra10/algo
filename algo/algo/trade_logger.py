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
        self.state_file = "strategy_state.json"
        self.headers = ['timestamp', 'instrument_key', 'side', 'qty', 'price', 'tag', 'pnl']
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

    def log_trade(self, instrument_key, side, qty, price, tag, pnl=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.headers)
            writer.writerow({
                'timestamp': timestamp,
                'instrument_key': instrument_key,
                'side': side,
                'qty': qty,
                'price': price,
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
            print(f"OPEN Weekly:   {Fore.YELLOW}{w['strike']} Put{Style.RESET_ALL} @ {w['entry_price']} (Current: {strategy_state.get('weekly_ltp', 'N/A')})")
        if strategy_state.get('monthly'):
            m = strategy_state['monthly']
            print(f"OPEN Monthly:  {Fore.YELLOW}{m['strike']} Put{Style.RESET_ALL} @ {m['entry_price']} (Current: {strategy_state.get('monthly_ltp', 'N/A')})")
        
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
                ltp = p.get('ltp', 0.0)
                
                # Calculate "Points" (Normalized to standard lot for easy strategy review)
                # If QTY=150 and Lot=75, multiplier is 2. Multiplier * Price = Points.
                multiplier = qty / config.ORDER_QUANTITY
                net_points_entry = entry * multiplier
                net_points_ltp = ltp * multiplier if isinstance(ltp, (int, float)) else 0.0
                
                print(f"{side_col}{p['side']} {qty} {p.get('type','')} {p.get('strike','')} @ {entry}{Style.RESET_ALL} "
                      f"(LTP: {ltp} | Net Points: {net_points_ltp:.2f})")
        
        print("="*50 + "\n")

    def save_state(self, weekly_pos, monthly_pos):
        """Saves current positions to a JSON file."""
        state = {
            'weekly': weekly_pos,
            'monthly': monthly_pos,
            'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=4)

    def load_state(self):
        """Loads positions from the JSON file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading state: {e}")
        return None

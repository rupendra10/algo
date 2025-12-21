import csv
import os
import json
from datetime import datetime
from colorama import Fore, Style

class TradeJournal:
    def __init__(self, filename="trade_log.csv"):
        self.filename = filename
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
        print(f"💰 {Fore.CYAN}TRADE SESSION SUMMARY{Style.RESET_ALL} 💰")
        print("="*50)
        print(f"Closed P&L:    {Fore.WHITE}₹{self.closed_pnl:,.2f}{Style.RESET_ALL}")
        print(f"Open P&L:      {Fore.WHITE}₹{open_pnl:,.2f}{Style.RESET_ALL}")
        print(f"Total P&L:     {pnl_color}₹{total_pnl:,.2f}{Style.RESET_ALL}")
        print("-" * 50)
        
        if strategy_state['weekly']:
            w = strategy_state['weekly']
            print(f"OPEN Weekly:   {Fore.YELLOW}{w['strike']} Put{Style.RESET_ALL} @ {w['entry_price']} (Current: {strategy_state['weekly_ltp']})")
        if strategy_state['monthly']:
            m = strategy_state['monthly']
            print(f"OPEN Monthly:  {Fore.YELLOW}{m['strike']} Put{Style.RESET_ALL} @ {m['entry_price']} (Current: {strategy_state['monthly_ltp']})")
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

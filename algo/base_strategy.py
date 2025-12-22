from abc import ABC, abstractmethod
import json
import os

class BaseStrategy(ABC):
    def __init__(self, name):
        self.name = name
        # Import here to avoid circular dependency
        import config
        mode = config.TRADING_MODE.lower()
        self.state_file = f"{name}_{mode}_state.json"

    @abstractmethod
    def update(self, market_data, order_callback):
        """
        Main logic loop for the strategy.
        market_data: dict containing spot_price, weekly_chain, monthly_chain, etc.
        order_callback: function to place trades.
        """
        pass

    @abstractmethod
    def exit_all_positions(self, order_callback, reason="MANUAL"):
        """
        Forcefully square off all positions.
        """
        pass

    def save_current_state(self, state_dict):
        """
        Saves current state to persistent storage.
        """
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state_dict, f, indent=4)
        except Exception as e:
            print(f"Error saving state for {self.name}: {e}")

    def load_previous_state(self):
        """
        Loads state from persistent storage.
        """
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading state for {self.name}: {e}")
        return None

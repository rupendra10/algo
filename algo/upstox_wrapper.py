import os
import time
import random
import upstox_client
from upstox_client.rest import ApiException
import config
import threading

class UpstoxWrapper:
    def __init__(self, access_token=None):
        """
        Initialize Upstox Client.
        For MVP/Auto-trading, we assume we have a valid access_token.
        In a full app, we'd handle the OAuth Code -> Token flow.
        """
        # Priority: Constructor Arg > Config File > Env Var
        self.access_token = access_token or config.UPSTOX_ACCESS_TOKEN or os.getenv('UPSTOX_ACCESS_TOKEN')
        if not self.access_token:
            print("WARNING: No Upstox Access Token provided. Set UPSTOX_ACCESS_TOKEN env var.")
            self.access_token = "" # Avoid NoneType error in client lib
        
        self.configuration = upstox_client.Configuration()
        self.configuration.access_token = self.access_token
        
        # API Instances
        self.api_client = upstox_client.ApiClient(self.configuration)
        self.history_api = upstox_client.HistoryApi(self.api_client)
        self.order_api = upstox_client.OrderApi(self.api_client)
        self.user_api = upstox_client.UserApi(self.api_client)
        self.market_quote_api = upstox_client.MarketQuoteApi(self.api_client)
        
        # Rate limiting state
        self._last_call_time = 0
        self._rate_limit_lock = threading.Lock()
        self._mandatory_delay = 1.0 # 1 second between any two API calls

    def _wait_for_rate_limit(self):
        """Ensures at least _mandatory_delay seconds have passed since the last API call."""
        with self._rate_limit_lock:
            now = time.time()
            elapsed = now - self._last_call_time
            if elapsed < self._mandatory_delay:
                wait_to_sleep = self._mandatory_delay - elapsed
                time.sleep(wait_to_sleep)
            self._last_call_time = time.time()

    def _safe_ltp_call(self, symbol, max_retries=5):
        """
        Helper to call the ltp API with aggressive retry logic for 429 (Too Many Requests).
        Uses exponential backoff with jitter and mandatory inter-call delay.
        """
        retries = 0
        while retries <= max_retries:
            self._wait_for_rate_limit()
            try:
                return self.market_quote_api.ltp(symbol=symbol, api_version='2.0')
            except ApiException as e:
                if e.status == 429:
                    retries += 1
                    if retries > max_retries:
                        print(f"ERROR: Max retries ({max_retries}) reached for 429 error on {symbol}.")
                        raise e
                    
                    # More aggressive backoff: 5, 10, 20, 40, 80...
                    wait_time = (5 * (2 ** (retries - 1))) + (random.randint(0, 2000) / 1000)
                    print(f"CRITICAL WARNING: 429 Too Many Requests. Burst detected. Retrying in {wait_time:.2f}s (Attempt {retries}/{max_retries})...")
                    time.sleep(wait_time)
                elif e.status == 401:
                    print("CRITICAL: Unauthorized. Check your UPSTOX_ACCESS_TOKEN.")
                    os._exit(1)
                else:
                    raise e
        return None

    def get_spot_price(self, instrument_key):
        """
        Get latest Last Traded Price (LTP) for an instrument.
        Example instrument_key: 'NSE_INDEX|Nifty 50'
        """
        try:
            # Full market quote
            api_response = self._safe_ltp_call(symbol=instrument_key)
            if api_response and api_response.status == 'success':
                # The API sometimes returns keys with : instead of | in the dictionary
                res_key = instrument_key.replace('|', ':')
                if instrument_key in api_response.data:
                    return api_response.data[instrument_key].last_price
                elif res_key in api_response.data:
                    return api_response.data[res_key].last_price
                
                # Fallback: if data has items, return first one's price
                if api_response.data:
                    first_key = list(api_response.data.keys())[0]
                    return api_response.data[first_key].last_price
                    
            return None
        except Exception as e:
            print(f"Exception when fetching spot price: {e}")
            return None

    def get_option_chain_quotes(self, instrument_keys):
        """
        Get quotes for a list of option keys to build a chain.
        """
        if not instrument_keys:
            return {}
            
        try:
            # quotes for multiple symbols
            symbols_str = ",".join(instrument_keys)
            api_response = self._safe_ltp_call(symbol=symbols_str)
            if api_response and api_response.status == 'success':
                # Normalize keys in response back to | (pipe) to match our internal keys
                normalized_data = {}
                for key, val in api_response.data.items():
                    token = getattr(val, 'instrument_token', None)
                    if token:
                        norm_token = token.replace(':', '|')
                        normalized_data[norm_token] = val
                    
                    norm_key = key.replace(':', '|')
                    normalized_data[norm_key] = val
                    
                return normalized_data
            return {}
        except Exception as e:
            print(f"Error getting quotes: {e}")
            return {}

    def search_instruments(self, query):
        """
        Search for instruments to find keys.
        NOTE: This is just a placeholder. In production, downloading the full instrument master CSV is preferred for speed.
        """
        pass
    
    def place_order(self, instrument_key, quantity, transaction_type, order_type='MARKET', product='D'):
        """
        Place a buy/sell order.
        transaction_type: 'BUY' or 'SELL'
        product: 'D' (Delivery) or 'I' (Intraday)
        """
        body = upstox_client.PlaceOrderRequest(
            quantity=quantity,
            product=config.ORDER_PRODUCT,
            validity=config.ORDER_VALIDITY,
            price=0.0,
            tag=config.ORDER_TAG_PREFIX,
            instrument_token=instrument_key,
            order_type=order_type,
            transaction_type=transaction_type,
            disclosed_quantity=0,
            trigger_price=0.0,
            is_amo=False
        )
        try:
            api_response = self.order_api.place_order(body, api_version='2.0')
            if api_response.status == 'success':
                return {'status': 'success', 'data': api_response.data}
            else:
                return {'status': 'error', 'message': getattr(api_response, 'message', 'Unknown API Error')}
        except ApiException as e:
            # Handle specific Upstox error messages
            import json
            error_msg = str(e)
            try:
                err_data = json.loads(e.body)
                error_msg = err_data.get('errors', [{}])[0].get('message', str(e))
            except:
                pass
            print(f"CRITICAL ERROR: Order placement failed - {error_msg}")
            return {'status': 'error', 'message': error_msg}
        except Exception as e:
            print(f"CRITICAL UNKNOWN ERROR: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_funds(self):
        """
        Get available margin/funds for the user.
        """
        try:
            self._wait_for_rate_limit()
            api_response = self.user_api.get_user_fund_margin(api_version='2.0')
            if api_response.status == 'success':
                # Upstox SDK returns objects. 
                # Structure is usually data.equity.available_margin
                data = getattr(api_response, 'data', None)
                if data:
                    equity = getattr(data, 'equity', None)
                    if equity:
                        return getattr(equity, 'available_margin', 0.0)
        except Exception as e:
            print(f"Error fetching funds: {e}")
        return 0.0

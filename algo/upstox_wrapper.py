import os
import upstox_client
from upstox_client.rest import ApiException
import config

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
        self.market_quote_api = upstox_client.MarketQuoteApi(self.api_client)

    def get_spot_price(self, instrument_key):
        """
        Get latest Last Traded Price (LTP) for an instrument.
        Example instrument_key: 'NSE_INDEX|Nifty 50'
        """
        try:
            # Full market quote
            api_response = self.market_quote_api.ltp(symbol=instrument_key, api_version='2.0')
            # Response structure: {status: 'success', data: {'NSE_INDEX|Nifty 50': {last_price: 21500.0, ...}}}
            if api_response.status == 'success':
                return api_response.data[instrument_key].last_price
            return None
        except ApiException as e:
            if e.status == 401:
                print("CRITICAL: Unauthorized. Check your UPSTOX_ACCESS_TOKEN.")
                os._exit(1) # Force exit to stop loop
            print(f"Exception when calling MarketQuoteApi->ltp: {e}")
            return None

    def get_option_chain_quotes(self, instrument_keys):
        """
        Get quotes for a list of option keys to build a chain.
        Upstox doesn't have a single "Get Option Chain" endpoint that returns Greeks nicely in one shot for all strikes.
        Usually we must construct the list of keys we want (e.g., Nifty 21000 CE, 21000 PE) and ask for quotes.
        
        For this simplified algo, we might need a way to map "Strike" -> "Instrument Key".
        This typically involves downloading the master contract list.
        """
        try:
            # quotes for multiple symbols
            # symbol argument is comma separated string
            symbols_str = ",".join(instrument_keys)
            api_response = self.market_quote_api.ltp(symbol=symbols_str, api_version='2.0')
            if api_response.status == 'success':
                return api_response.data
            return {}
        except ApiException as e:
            if e.status == 401:
                print("CRITICAL: Unauthorized. Check your UPSTOX_ACCESS_TOKEN.")
                os._exit(1)
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
            return api_response
        except ApiException as e:
            print(f"Exception when calling OrderApi->place_order: {e}")
            return None

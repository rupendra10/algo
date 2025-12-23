import sys
import unittest
from unittest.mock import MagicMock, patch
import os
import time

# Mock the upstox_client and ApiException before importing UpstoxWrapper
mock_upstox = MagicMock()
class MockApiException(Exception):
    def __init__(self, status=None, body=None):
        self.status = status
        self.body = body
        super().__init__(f"Status: {status}")

mock_upstox.rest.ApiException = MockApiException
sys.modules['upstox_client'] = mock_upstox
sys.modules['upstox_client.rest'] = mock_upstox.rest

# Now import UpstoxWrapper
from upstox_wrapper import UpstoxWrapper

class TestUpstoxWrapperAggressiveRetry(unittest.TestCase):
    def setUp(self):
        # Setup mock configuration
        with patch('config.UPSTOX_ACCESS_TOKEN', 'fake_token'):
            self.wrapper = UpstoxWrapper()
        
        # Ensure market_quote_api is a mock
        self.wrapper.market_quote_api = MagicMock()

    @patch('time.sleep', return_value=None) # Don't actually sleep
    @patch('random.randint', return_value=0) # No jitter for predictable tests
    def test_aggressive_retry_timing(self, mock_jitter, mock_sleep):
        # 1. Test Aggressive Backoff Sequence: 5, 10, 20...
        mock_429_error = MockApiException(status=429)
        mock_success_res = MagicMock()
        mock_success_res.status = 'success'
        mock_success_res.data = {'NSE_INDEX:Nifty 50': MagicMock(last_price=21000.0)}

        # Fail 3 times, then succeed
        self.wrapper.market_quote_api.ltp = MagicMock(side_effect=[mock_429_error, mock_429_error, mock_429_error, mock_success_res])

        price = self.wrapper.get_spot_price('NSE_INDEX|Nifty 50')
        
        # Assertions
        self.assertEqual(price, 21000.0)
        # Total sleep calls = 3 backoffs + 4 inter-call delays (one before each ltp call)
        # However, inter-call delay might not sleep on the VERY FIRST call because _last_call_time = 0.
        # Let's count properly.
        # call 1: _last_call_time=0, time.time()=X. elapsed=X. if X < 1.0, sleep.
        # Actually in setup _last_call_time = 0. So if time.time() > 1.0, no sleep.
        
        # In this test, mock_sleep is patched. 
        # The backoff calls are 5, 10, 20. 
        self.assertIn(unittest.mock.call(5.0), mock_sleep.call_args_list)
        self.assertIn(unittest.mock.call(10.0), mock_sleep.call_args_list)
        self.assertIn(unittest.mock.call(20.0), mock_sleep.call_args_list)
        print("Test passed: Aggressive backoff timing verified.")

    @patch('time.time')
    @patch('time.sleep')
    def test_inter_call_delay(self, mock_sleep, mock_time):
        # Mock time to simulate calls exactly 0.1s apart
        # now will be 100.1, last_call_time was 100.0
        mock_time.side_effect = [100.1, 101.1] 
        
        self.wrapper._last_call_time = 100.0
        
        # First call to _wait_for_rate_limit: now=100.1. elapsed=0.1. wait=0.9.
        self.wrapper._wait_for_rate_limit()
        
        # Use assertAlmostEqual for floating point precision
        mock_sleep.assert_called_once()
        self.assertAlmostEqual(mock_sleep.call_args[0][0], 0.9, places=7)
        print("Test passed: Inter-call delay enforced.")

if __name__ == '__main__':
    unittest.main()

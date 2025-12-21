import numpy as np
from scipy.stats import norm

def calculate_delta(flag, S, K, t, r, sigma):
    """
    Calculate the Delta of an option using Black-Scholes formula.
    
    Parameters:
    flag (str): 'c' for Call, 'p' for Put.
    S (float): Spot price of the underlying.
    K (float): Strike price.
    t (float): Time to expiration in years.
    r (float): Risk-free interest rate (annualized).
    sigma (float): Annualized volatility (Implied Volatility).
    
    Returns:
    float: The delta of the option.
    """
    try:
        if t <= 0:
            # At expiration, delta is 0 or 1/-1 depending on ITM/OTM
            if flag.lower() == 'c':
                 return 1.0 if S > K else 0.0
            else:
                 return -1.0 if S < K else 0.0

        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
        
        if flag.lower() == 'c':
            delta = norm.cdf(d1)
        elif flag.lower() == 'p':
            delta = norm.cdf(d1) - 1
        else:
            delta = 0.0
            
        return delta
    except Exception as e:
        print(f"Error calculating delta: {e}")
        return 0.0

def get_atm_strike(spot_price, strike_gap=50):
    """
    Get the At-The-Money strike price.
    Usually Nifty strikes are in multiples of 50.
    """
    return round(spot_price / strike_gap) * strike_gap

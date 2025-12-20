import numpy as np
from scipy.stats import norm

def black_scholes_price(flag, S, K, t, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    
    if flag == 'c':
        price = S * norm.cdf(d1) - K * np.exp(-r * t) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * t) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    return price

def _vega(S, K, t, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    return S * norm.pdf(d1) * np.sqrt(t)

def calculate_implied_volatility(price, S, K, t, r, flag='p'):
    """
    Calculate Implied Volatility (IV) using Newton-Raphson method.
    """
    if t <= 0:
        return 0.001
    
    # Intrinsic check
    intrinsic = 0
    if flag == 'p':
        intrinsic = max(K - S, 0)
    else:
        intrinsic = max(S - K, 0)
        
    if price < intrinsic:
        return 0.001
        
    # Initial Guess
    sigma = 0.5
    
    # Newton-Raphson
    for i in range(100):
        bs_price = black_scholes_price(flag, S, K, t, r, sigma)
        diff = price - bs_price
        
        if abs(diff) < 1e-5:
            return sigma
            
        v = _vega(S, K, t, r, sigma)
        
        if v == 0:
            break
            
        sigma = sigma + diff / v
        
    return sigma

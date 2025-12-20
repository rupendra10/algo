from utils import calculate_implied_volatility, black_scholes_price

def test_iv_calc():
    # Known Scenario
    # Spot = 21000
    # Strike = 21000
    # Time = 0.05 years (~18 days)
    # Risk Free = 0.07
    # IV Target = 0.15 (15%)
    
    S = 21000
    K = 21000
    t = 0.05
    r = 0.07
    sigma = 0.15
    
    # Calculate Theoretical Price using our own function
    price = black_scholes_price('p', S, K, t, r, sigma)
    print(f"Theoretical Put Price with IV 15%: {price:.2f}")
    
    # Now Reverse
    calculated_iv = calculate_implied_volatility(price, S, K, t, r, 'p')
    print(f"Calculated IV: {calculated_iv:.4f}")
    
    assert abs(calculated_iv - 0.15) < 0.01, f"IV Calculation failed accuracy test. Got {calculated_iv}"
    
    # Test Intrinsic lower bound
    bad_price = 900
    iv_bad = calculate_implied_volatility(bad_price, S, 22000, t, r, 'p')
    print(f"IV for ITM Price < Intrinsic: {iv_bad}")
    
test_iv_calc()

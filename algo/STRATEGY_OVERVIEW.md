# Trading Strategies Overview

Complete guide to CalendarPEWeekly and WeeklyIronfly strategies including entry, adjustment, and exit rules.

---

## 📊 Strategy 1: CalendarPEWeekly

### Strategy Description
A calendar spread strategy that sells weekly ATM puts and buys monthly ATM puts as a hedge. Profits from time decay while maintaining downside protection.

### Entry Rules

**Timing:**
- **LIVE Mode**: Only on Monthly Expiry Day at **3:15 PM** (when `STRICT_MONTHLY_EXPIRY_ENTRY = True`)
- **PAPER Mode**: Immediate entry

**Construction:**
1. **Sell**: Weekly Put at ATM (Delta ~0.50)
2. **Buy**: Monthly Put at ATM (Delta ~0.50)

**Entry Conditions:**
- No existing positions
- Monthly expiry day (dynamically detected from option chain)
- Current time >= 3:15 PM

**Example Entry:**
```
Spot: 25,966
Sell: 1 Weekly PE 25,950 @ ₹95 (Expiry: 2025-12-23)
Buy:  1 Monthly PE 26,150 @ ₹287 (Expiry: 2026-01-27)
Net Debit: ₹192 per lot
```

### Adjustment Rules

**Weekly Leg Adjustments:**

**Trigger 1 - Market Fall:**
- Weekly Put Delta >= 0.80
- **Action**: Roll to new ATM strike (Delta ~0.50)
- Exit current weekly, enter new weekly

**Trigger 2 - Market Rise:**
- Weekly Put Delta <= 0.10
- **Action**: Roll to new ATM strike (Delta ~0.50)
- Exit current weekly, enter new weekly

**Monthly Leg Adjustments:**

**Trigger 1 - Sharp Market Fall:**
- Monthly Put Delta >= 0.90
- **Action**: Roll to lower delta (0.30)
- Exit current monthly, enter new monthly

**Trigger 2 - Sharp Market Rise:**
- Monthly Put Delta <= 0.10
- **Action**: Roll to higher delta (0.70)
- Exit current monthly, enter new monthly

### Exit Rules

**1. Monday Rollover:**
- Day: Monday (weekday = 0)
- Condition: Weekly position expiry <= 1.5 days
- Action: Square off weekly, keep monthly

**2. Max Loss Hit:**
- Trigger: Total P&L <= -₹10,000 (configurable)
- Action: Exit all positions immediately

**3. Pre-Monthly Expiry Exit:**
- Day: Day before monthly expiry
- Time: After 3:00 PM
- Action: Exit all positions (if `AUTO_EXIT_BEFORE_MONTHLY_EXPIRY_3PM = True`)

### Configuration Parameters
```python
# Entry
ENTRY_WEEKLY_DELTA_TARGET = 0.50
ENTRY_MONTHLY_DELTA_TARGET = 0.50
STRICT_MONTHLY_EXPIRY_ENTRY = True
ENTRY_TIME_HHMM = "15:15"

# Adjustments
WEEKLY_ADJ_TRIGGER_DELTA = 0.80      # Fall trigger
WEEKLY_ADJ_TRIGGER_DELTA_LOW = 0.10  # Rise trigger
WEEKLY_ROLL_TARGET_DELTA = 0.50      # Target after roll

MONTHLY_ADJ_TRIGGER_DELTA = 0.90     # Fall trigger
MONTHLY_ADJ_TRIGGER_DELTA_LOW = 0.10 # Rise trigger
MONTHLY_ROLL_TARGET_DELTA_FALL = 0.30
MONTHLY_ROLL_TARGET_DELTA_RISE = 0.70

# Risk Management
MAX_LOSS_VALUE = 10000
ROLLOVER_WEEKDAY = 0  # Monday
AUTO_EXIT_BEFORE_MONTHLY_EXPIRY_3PM = True

# Position Sizing
ORDER_QUANTITY = 75  # Lot size
```

---

## 🦋 Strategy 2: WeeklyIronfly (Put Butterfly)

### Strategy Description
A limited-risk, limited-reward strategy using a Put Butterfly spread. Profits when the market stays within a range.

### Entry Rules

**Timing:**
- **LIVE Mode**: On Current Weekly Expiry Day at **12:00 PM**
- **PAPER Mode**: Immediate entry
- Positions are for **next week's expiry**

**Construction:**
Based on current spot and ATM strike:

1. **Leg 1**: Buy 1 Put at ATM-50 (slightly OTM)
2. **Leg 2**: Sell 2 Puts at ATM-250 (further OTM)
3. **Leg 3**: Buy 1 Put at ATM-450 (hedge)

**Entry Conditions:**
- No existing positions
- Today = Current weekly expiry day
- Current time >= 12:00 PM

**Example Entry:**
```
Spot: 25,966
ATM: 25,950

Leg 1: Buy  75 PE 25,900 @ ₹85.0   (ATM-50)
Leg 2: Sell 150 PE 25,700 @ ₹40.0  (ATM-250)
Leg 3: Buy  75 PE 25,500 @ ₹19.55  (ATM-450)

Net Credit: ₹3,337.50
Max Profit: ₹3,337.50 (if expires at 25,700)
Max Loss: ₹11,662.50 (if expires below 25,500 or above 25,900)
```

### Adjustment Rules

**Trigger:**
- P&L <= -1% of capital (₹1,800 loss on ₹180,000 capital)
- Only adjusts once (`is_adjusted = False`)

**The Adjustment - Call Calendar Spread:**

**Purpose**: Extends break-even range by ~500 points on upside

**Construction:**
1. Calculate adjustment strike: Leg 1 strike + 100 points
2. **Sell**: 1 Call at adjustment strike (current week's expiry)
3. **Buy**: 1 Call at adjustment strike (next week's expiry)

**Example Adjustment:**
```
Original Leg 1: Buy PE 25,900
Adjustment Strike: 25,900 + 100 = 26,000

Sell: 1 CE 26,000 (This Week)
Buy:  1 CE 26,000 (Next Week)

Effect: Extends upside break-even to ~26,450
```

**Post-Adjustment Behavior:**
- If P&L recovers to +3%, exits at target
- If loss continues beyond 1%, exits completely

### Exit Rules

**1. Target Hit:**
- Trigger: P&L >= 3% of capital (₹5,400 profit)
- Action: Exit all positions

**2. Stop Loss (Pre-Adjustment):**
- Trigger: P&L <= -1% of capital (₹1,800 loss)
- Action: Apply Call Calendar adjustment

**3. Stop Loss (Post-Adjustment):**
- Trigger: P&L <= -1% of capital after adjustment
- Action: Exit all positions

**4. Expiry Exit:**
- Day: Position's expiry day
- Time: 3:00 PM
- Action: Exit all positions

### Configuration Parameters
```python
# Capital & Risk
IRONFLY_CAPITAL = 180000
IRONFLY_SL_PERCENT = 0.01       # 1% SL
IRONFLY_TARGET_PERCENT = 0.03   # 3% target (adjustable to 0.05 for 5%)

# Entry Timing
IRONFLY_ENTRY_WEEKDAY = 1       # Tuesday (fallback)
IRONFLY_ENTRY_TIME = "12:00"
IRONFLY_EXIT_TIME = "15:00"

# Strike Offsets (relative to ATM)
IRONFLY_LEG1_OFFSET = -50       # Buy Put
IRONFLY_LEG2_OFFSET = -250      # Sell 2 Puts
IRONFLY_LEG3_OFFSET = -450      # Buy Put (hedge)

# Adjustment
IRONFLY_ADJ_INWARD_OFFSET = 100 # Move 100 points inward for Call Calendar

# Position Sizing
ORDER_QUANTITY = 75  # Lot size
```

---

## 📁 File Structure

### State Files (Mode-Specific)
```
CalendarPEWeekly_paper_state.json    # PAPER mode state
CalendarPEWeekly_live_state.json     # LIVE mode state
WeeklyIronfly_paper_state.json       # PAPER mode state
WeeklyIronfly_live_state.json        # LIVE mode state
```

### Trade Logs (Mode-Specific)
```
trade_log_calendar_paper.csv         # PAPER mode trades
trade_log_calendar_live.csv          # LIVE mode trades
trade_log_ironfly_paper.csv          # PAPER mode trades
trade_log_ironfly_live.csv           # LIVE mode trades
```

---

## 🎯 Quick Reference

### CalendarPEWeekly
- **Entry**: Monthly expiry at 3:15 PM
- **Adjustments**: Delta-based (0.80/0.10 for weekly, 0.90/0.10 for monthly)
- **Exits**: Max loss, Monday rollover, pre-monthly expiry

### WeeklyIronfly
- **Entry**: Current weekly expiry at 12:00 PM for next week
- **Adjustments**: 1% loss triggers Call Calendar (once only)
- **Exits**: 3% target, 1% SL (post-adj), expiry at 3:00 PM

---

## 🔧 Running the Strategies

### PAPER Mode (Testing)
```python
TRADING_MODE = 'PAPER'
ACTIVE_STRATEGIES = ['CalendarPEWeekly', 'WeeklyIronfly']
```
- Immediate entry for both strategies
- No real money at risk
- Separate state/log files

### LIVE Mode (Real Trading)
```python
TRADING_MODE = 'LIVE'
ACTIVE_STRATEGIES = ['CalendarPEWeekly', 'WeeklyIronfly']
```
- CalendarPEWeekly: Waits for monthly expiry
- WeeklyIronfly: Waits for weekly expiry
- Real money at risk
- Separate state/log files

### Command
```bash
python run_strategy.py
```

---

## ⚠️ Important Notes

1. **Expiry Detection**: Both strategies use dynamic expiry detection from the instrument master, automatically accounting for market holidays

2. **Rate Limiting**: 1-second mandatory delay between all API calls + exponential backoff on 429 errors

3. **State Recovery**: Strategies automatically load previous positions on restart

4. **Mode Separation**: PAPER and LIVE modes use completely separate state and log files

5. **Greeks Calculation**: Delta values are recalculated on every update using Black-Scholes model

6. **Position Monitoring**: Strategies update every 30 seconds (configurable via `POLL_INTERVAL_SECONDS`)

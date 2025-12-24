# Nifty Options Algo: Master Setup & Operation Guide

This document provides a consolidated overview of how to configure, run, and remotely monitor your automated Nifty options strategy.

---

## 🚀 1. Initial Setup

### 🪟 Windows Setup
1. **Dependencies:**
   ```bash
   pip install upstox-client colorama python-dotenv pandas numpy scipy requests
   ```

### 🐧 Ubuntu/Linux Setup
Modern Ubuntu (23.04+) requires a virtual environment to prevent system package conflicts.
1. **Install venv:** `sudo apt update && sudo apt install python3-venv`
2. **Create Env:** `python3 -m venv venv`
3. **Activate:** `source venv/bin/activate`
4. **Install Dependencies:**
   ```bash
   pip install upstox-client colorama python-dotenv pandas numpy scipy requests
   ```
   *(Note: You must activate the environment every time you open a new terminal.)*

### ⚙️ Configuration
2.  **Environment Variables (`.env`):** Create a `.env` file in the root directory:
    ```env
    UPSTOX_API_KEY=your_api_key
    UPSTOX_API_SECRET=your_api_secret
    UPSTOX_REDIRECT_URI=your_redirect_uri
    UPSTOX_ACCESS_TOKEN=your_temp_token
    ```

---

## 🔑 2. Authentication Flow
Every day, you need a fresh `UPSTOX_ACCESS_TOKEN`.
1.  Run `python authorize_upstox.py`.
2.  Follow the link provided, login to Upstox, and copy the `code` from the URL after the redirect.
3.  The script will automatically update your `.env` file with the new token.

---

## 📈 3. Trading Strategy & Rules
### Core Logic
- **Weekly Leg (SELL):** Targets 0.45 Delta Put.
- **Monthly Leg (BUY):** Targets 0.50 Delta Put (Hedge).

### Adjustment Rules
| Scenario | Leg | Logic |
| :--- | :--- | :--- |
| **Market Fall** | Weekly (Sell) | If Delta >= 0.80 -> Roll to ATM. |
| **Market Rise** | Weekly (Sell) | If Delta <= 0.10 -> Roll to ATM. |
| **Market Fall** | Monthly (Buy) | If Delta >= 0.90 -> Roll to ATM (Profit Lock). |
| **Market Rise** | Monthly (Buy) | If Delta <= 0.10 -> Roll to 0.35 Delta strike. |

### Special Days
- **Monday Rollover:** Automatically squares off the Weekly leg 1 day before expiry and rolls to the *Next Weekly*.
- **T-1 Monthly Expiry:** Automatically exits ALL positions at 3:00 PM one day before monthly expiry to avoid margin spikes.

---

## 🛡️ 4. Risk Management
- **Max Loss Stop (INR):** Configurable in `config.py` via `MAX_LOSS_VALUE`.
- **VIX Filter:** Pauses at VIX > 25.0 to protect against extreme volatility.
- **Margin Check:** Verifies minimum cash balance before entry.
- **Atomic Entry:** Ensures you never sell the weekly without successfully buying the monthly hedge.

---

## 🔁 6. Restart & Persistence
The algo is **Restart-Proof**.
- **State File:** Active positions are saved in `strategy_state.json`.
- **Resume:** On restart, the bot detects existing trades and resumes monitoring instead of re-trading.
- **Journal:** Detailed history is kept in `trade_log.csv`.

---

## 🚦 7. How to Start
Choose your mode in [config.py](file:///c:/Users/RupendraSagar/scratch/algo/config.py):
- `TRADING_MODE = 'PAPER'` (Simulation)
- `TRADING_MODE = 'LIVE'` (Real Trading)

**Run command:**
```bash
python run_strategy.py
```

> [!IMPORTANT]
> Always verify your `UPSTOX_ACCESS_TOKEN` is fresh before the market opens at 9:15 AM!

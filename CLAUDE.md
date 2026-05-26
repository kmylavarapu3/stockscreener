# Stock Screener

Streamlit-based stock screener for **NSE Nifty 500** (India) and **NYSE-listed** (US) stocks.

## What it does

Filters a universe of tickers by three criteria:
- **P/E ratio** below a configurable threshold (default 20)
- **Volume spike**: today's volume vs. 20-day average above a configurable multiplier (default 2x)
- **RSI(14)** above a configurable threshold (default 50)

Results are shown in a ranked, sortable table that auto-refreshes every 60 seconds.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501.

## Project layout

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — sidebar controls, auto-refresh, results table. Entrypoint. |
| `screener.py` | Pure functions for loading universe, fetching prices/fundamentals, computing metrics, applying filters. |
| `indicators.py` | Technical indicators (RSI, Wilder's smoothing). |
| `data/nifty500.csv` | NSE Nifty 500 tickers with `.NS` suffix (yfinance format). |
| `data/nyse.csv` | Curated NYSE large-cap tickers. |
| `requirements.txt` | Pinned Python dependencies. |

`screener.py` is intentionally separated from `app.py` so the data/filter logic can be tested independently of the UI.

## Data source

All market data comes from **yfinance**. Notes:
- Nifty/NSE tickers must carry the `.NS` suffix (e.g. `RELIANCE.NS`).
- `trailingPE` is pulled per-ticker via `Ticker.info` — slower and occasionally missing. Tickers without a P/E are excluded from P/E-filtered results.
- Price/volume bars are batched via `yf.download(period='30d', interval='1d')` — far faster than per-ticker loops.

## Caching

`screener.run_screener(...)` is wrapped with `@st.cache_data(ttl=55)` so the 60s auto-refresh effectively pulls one fresh dataset per cycle and shares it across slider changes that happen within the window.

## Editing the universe

Replace `data/nifty500.csv` or `data/nyse.csv` with any list of tickers (`ticker,name` header). No code changes needed.

## Out of scope

- Intraday/minute bars (refresh re-pulls daily bars).
- Persisting historical runs, alerts, multi-user auth.

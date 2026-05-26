# Stock Screener

A simple web dashboard that scans **NSE Nifty 500** (India) and **US (NYSE/NASDAQ)** stocks for ones that look interesting *right now* — cheap (low P/E), unusually heavy trading volume, and rising momentum (RSI). The dashboard refreshes every 60 seconds and you can tune the filters with sliders.

**Live demo:** _add your Streamlit Cloud URL here after deploy_

> No install needed for end users — just open the link. To run locally, see the Quick Start below.

Near real-time stock screener. Filters by **P/E ratio**, **volume spike**, and **RSI(14)** with adjustable thresholds, in a Streamlit dashboard that auto-refreshes every 60 seconds.

## Quick start

```bash
cd /Users/kmylavarapu/Documents/Personal/stockscreener
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

## Filters (defaults match the spec)

| Filter | Default | Adjust in sidebar |
|---|---|---|
| Max P/E | 20 | Slider 1–100 |
| Min Volume Ratio (today / 20d avg) | 2.0x | Slider 1–10 |
| Min RSI(14) | 50 | Slider 0–100 |
| Top N results | 25 | Number input 5–200 |

Results are ranked by volume ratio (highest spike first). You can also click any column header in the table to re-sort.

## How it works

1. Loads the chosen ticker universe from `data/nifty500.csv` or `data/nyse.csv`.
2. Batched `yf.download` pulls 60 days of daily OHLCV bars for the entire universe in one call.
3. For each ticker: computes today's close (current price), `today_vol / mean(last 20 days vol)`, and 14-period Wilder's RSI on the close series.
4. Per-ticker `trailingPE` is pulled in parallel via `yf.Ticker(...).info` (10 threads).
5. Applies the three filters and returns the Top-N.

The full screener is wrapped in `@st.cache_data(ttl=55)` so slider tweaks within a 60s window don't trigger refetches.

## Project layout

```
app.py              Streamlit UI
screener.py         load/fetch/compute/filter
indicators.py       RSI
data/
  nifty500.csv      Nifty 500 tickers (yfinance format with .NS suffix)
  nyse.csv          US large-cap tickers
requirements.txt
CLAUDE.md
```

## Updating the universe

Replace either CSV with a list of tickers — header `ticker,name`. For NSE, append `.NS` to tickers. No code change required.

## Notes & caveats

- "Current price" = latest daily close from yfinance (the dashboard refreshes daily bars every 60s; intraday quotes are not used).
- Some tickers have no `trailingPE` (loss-making, ADRs, etc.) and are excluded from P/E-filtered results.
- yfinance can throttle on very large universes. The bundled lists are ~250 tickers each, well within limits.

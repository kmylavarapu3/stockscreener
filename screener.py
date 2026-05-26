"""Core screener: load universe, fetch market data, compute metrics, filter."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from indicators import rsi

DATA_DIR = Path(__file__).parent / "data"
FUNDAMENTALS_CACHE = DATA_DIR / "fundamentals_cache.csv"
# P/E ratios change slowly; refetch only if a ticker hasn't been updated in this
# many hours. yfinance's .info endpoint is heavily rate-limited so we cannot
# refresh every cycle.
FUNDAMENTALS_TTL_HOURS = 24

MARKETS = {
    "NSE (Nifty 500)": "nifty500.csv",
    "NYSE": "nyse.csv",
}


def load_universe(market: str) -> pd.DataFrame:
    """Load tickers for a market. Returns DataFrame with columns: ticker, name."""
    fname = MARKETS[market]
    path = DATA_DIR / fname
    df = pd.read_csv(path)
    df["ticker"] = df["ticker"].str.strip().str.upper()
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    return df


def fetch_prices(tickers: list[str], period: str = "60d") -> pd.DataFrame:
    """Batched daily OHLCV download.

    Returns a long-form DataFrame indexed by (ticker, date) with columns
    Open, High, Low, Close, Volume. Tickers that yfinance couldn't fetch
    are silently dropped.
    """
    if not tickers:
        return pd.DataFrame()

    raw = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=False,
    )

    frames = []
    if isinstance(raw.columns, pd.MultiIndex):
        for t in tickers:
            if t not in raw.columns.get_level_values(0):
                continue
            sub = raw[t].dropna(how="all").copy()
            if sub.empty:
                continue
            sub["ticker"] = t
            frames.append(sub)
    else:
        # Single ticker case — yfinance returns a flat frame.
        sub = raw.dropna(how="all").copy()
        if not sub.empty:
            sub["ticker"] = tickers[0]
            frames.append(sub)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames)
    out.index.name = "date"
    out = out.reset_index().set_index(["ticker", "date"]).sort_index()
    return out


def _fetch_one_pe(ticker: str) -> tuple[str, float | None, str | None]:
    """Returns (ticker, pe_or_None, error_or_None)."""
    try:
        info = yf.Ticker(ticker).info
        pe = info.get("trailingPE")
        return ticker, (float(pe) if pe is not None else None), None
    except Exception as exc:  # noqa: BLE001
        return ticker, None, str(exc)


def _load_fundamentals_cache() -> pd.DataFrame:
    if not FUNDAMENTALS_CACHE.exists():
        return pd.DataFrame(columns=["ticker", "pe", "fetched_at"])
    df = pd.read_csv(FUNDAMENTALS_CACHE)
    # Force UTC-aware so comparisons with `cutoff` (also UTC-aware) succeed.
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], errors="coerce", utc=True)
    return df


def _save_fundamentals_cache(df: pd.DataFrame) -> None:
    FUNDAMENTALS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(FUNDAMENTALS_CACHE, index=False)


def fetch_fundamentals(
    tickers: list[str],
    max_workers: int = 4,
    throttle_seconds: float = 0.1,
) -> pd.DataFrame:
    """Fetch trailingPE per ticker with a persistent disk cache.

    - Returns immediately for tickers whose cached value is fresh (< TTL hours).
    - Fetches stale/missing tickers in parallel (bounded). Throttles between
      submissions to avoid hammering yfinance.
    - On `Too Many Requests` errors, stops issuing new requests and reuses the
      existing cache values for the remainder. The cache is updated for any
      tickers that did succeed so subsequent runs make progress.
    """
    cache = _load_fundamentals_cache().set_index("ticker")
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(hours=FUNDAMENTALS_TTL_HOURS)

    stale: list[str] = []
    for t in tickers:
        if t not in cache.index:
            stale.append(t)
            continue
        ts = cache.loc[t, "fetched_at"]
        if pd.isna(ts) or ts < cutoff:
            stale.append(t)

    rate_limited = False
    if stale:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {}
            for t in stale:
                if rate_limited:
                    break
                futures[ex.submit(_fetch_one_pe, t)] = t
                time.sleep(throttle_seconds)
            for fut in as_completed(futures):
                t, pe, err = fut.result()
                if err and "Too Many Requests" in err:
                    rate_limited = True
                    continue
                cache.loc[t, "pe"] = pe
                cache.loc[t, "fetched_at"] = pd.Timestamp.utcnow()

    cache = cache.reset_index()
    _save_fundamentals_cache(cache)

    out = cache[cache["ticker"].isin(tickers)][["ticker", "pe"]].copy()
    return out


def compute_metrics(
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
) -> pd.DataFrame:
    """Compute current_price, vol_ratio (today / 20d avg), and rsi_14 per ticker."""
    if prices.empty:
        return pd.DataFrame(
            columns=["ticker", "current_price", "pe", "vol_ratio", "rsi_14"]
        )

    rows = []
    for ticker, df in prices.groupby(level=0):
        df = df.droplevel(0).sort_index()
        if len(df) < 22:
            continue

        close = df["Close"]
        volume = df["Volume"]

        # current_price: latest available bar (may be intraday).
        today_close = float(close.iloc[-1])

        # Volume ratio: compare the most recent *completed* trading day to the
        # 20 days before it. We skip iloc[-1] because during market hours that
        # bar reflects only volume accumulated so far today, which makes the
        # ratio meaningless. Using the prior completed bar gives a stable
        # signal regardless of when the screener is run.
        ref_vol = float(volume.iloc[-2])
        avg20_vol = float(volume.iloc[-22:-2].mean())
        vol_ratio = ref_vol / avg20_vol if avg20_vol > 0 else np.nan

        rsi_series = rsi(close, period=14)
        rsi_14 = float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

        rows.append(
            {
                "ticker": ticker,
                "current_price": today_close,
                "vol_ratio": vol_ratio,
                "rsi_14": rsi_14,
            }
        )

    metrics = pd.DataFrame(rows)
    if metrics.empty:
        metrics["pe"] = []
        return metrics

    return metrics.merge(fundamentals, on="ticker", how="left")


def screen(
    metrics: pd.DataFrame,
    max_pe: float = 20.0,
    min_vol_ratio: float = 2.0,
    min_rsi: float = 50.0,
    top_n: int = 25,
    allow_missing_pe: bool = False,
) -> pd.DataFrame:
    """Apply screen filters and return Top-N ranked by volume ratio (desc).

    When `allow_missing_pe` is True, tickers with no P/E data still pass the P/E
    filter — useful when yfinance has rate-limited the fundamentals fetch.
    """
    if metrics.empty:
        return metrics

    pe_pass = (metrics["pe"].notna() & (metrics["pe"] > 0) & (metrics["pe"] < max_pe))
    if allow_missing_pe:
        pe_pass = pe_pass | metrics["pe"].isna()

    mask = (
        pe_pass
        & metrics["vol_ratio"].notna()
        & (metrics["vol_ratio"] > min_vol_ratio)
        & metrics["rsi_14"].notna()
        & (metrics["rsi_14"] > min_rsi)
    )
    filtered = metrics[mask].copy()
    filtered = filtered.sort_values("vol_ratio", ascending=False).head(top_n)
    return filtered.reset_index(drop=True)


def run_screener(
    market: str,
    max_pe: float = 20.0,
    min_vol_ratio: float = 2.0,
    min_rsi: float = 50.0,
    top_n: int = 25,
    allow_missing_pe: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
    """End-to-end.

    Returns (filtered, all_metrics, universe_size, pe_coverage). `all_metrics`
    is the unfiltered per-ticker table; `pe_coverage` is how many tickers have a
    valid P/E value (useful to surface fundamentals-fetch health in the UI).
    """
    universe = load_universe(market)
    tickers = universe["ticker"].tolist()
    prices = fetch_prices(tickers)
    available = sorted({lvl for lvl in prices.index.get_level_values(0).unique()}) if not prices.empty else []
    fundamentals = fetch_fundamentals(available)
    metrics = compute_metrics(prices, fundamentals)
    metrics = metrics.merge(universe[["ticker", "name"]], on="ticker", how="left")
    cols = ["ticker", "name", "current_price", "pe", "vol_ratio", "rsi_14"]
    all_metrics = metrics[[c for c in cols if c in metrics.columns]].copy()
    pe_coverage = int(all_metrics["pe"].notna().sum()) if "pe" in all_metrics else 0
    result = screen(metrics, max_pe, min_vol_ratio, min_rsi, top_n, allow_missing_pe)
    result = result[[c for c in cols if c in result.columns]]
    return result, all_metrics, len(tickers), pe_coverage

"""Streamlit UI for the stock screener."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from screener import MARKETS, run_screener

st.set_page_config(page_title="Stock Screener", layout="wide")

REFRESH_MS = 60_000


@st.cache_data(ttl=55, show_spinner=False)
def _cached_run(
    market: str,
    max_pe: float,
    min_vol_ratio: float,
    min_rsi: float,
    top_n: int,
    allow_missing_pe: bool,
):
    return run_screener(
        market=market,
        max_pe=max_pe,
        min_vol_ratio=min_vol_ratio,
        min_rsi=min_rsi,
        top_n=top_n,
        allow_missing_pe=allow_missing_pe,
    )


def main() -> None:
    st.title("Stock Screener")
    st.caption("Filters by P/E, volume spike, and RSI. Auto-refreshes every 60 seconds.")

    with st.sidebar:
        st.header("Settings")
        market = st.selectbox("Market", list(MARKETS.keys()), index=0)
        st.divider()
        st.subheader("Filters")
        max_pe = st.slider("Max P/E", 1.0, 100.0, 20.0, 0.5)
        min_vol_ratio = st.slider("Min Volume Ratio (today / 20d avg)", 1.0, 10.0, 2.0, 0.1)
        min_rsi = st.slider("Min RSI(14)", 0.0, 99.0, 50.0, 1.0)
        top_n = st.number_input("Top N results", min_value=5, max_value=200, value=25, step=5)
        allow_missing_pe = st.checkbox(
            "Include stocks with no P/E data",
            value=False,
            help="Useful when yfinance is rate-limiting the fundamentals fetch.",
        )
        st.divider()
        show_diag = st.checkbox("Show diagnostics (all stocks, no filters)", value=False)
        manual = st.button("Refresh now", use_container_width=True)
        if manual:
            _cached_run.clear()

    st_autorefresh(interval=REFRESH_MS, key="auto_refresh")

    with st.spinner(f"Screening {market}..."):
        try:
            results, all_metrics, universe_size, pe_coverage = _cached_run(
                market,
                float(max_pe),
                float(min_vol_ratio),
                float(min_rsi),
                int(top_n),
                bool(allow_missing_pe),
            )
            error = None
        except Exception as exc:  # noqa: BLE001
            results = pd.DataFrame()
            all_metrics = pd.DataFrame()
            universe_size = 0
            pe_coverage = 0
            error = str(exc)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Market", market)
    col2.metric("Universe size", f"{universe_size:,}")
    col3.metric("P/E coverage", f"{pe_coverage:,}")
    col4.metric("Matches", f"{len(results):,}")
    st.caption(f"Last updated: {now}  —  next refresh in 60s")

    if error:
        st.error(f"Screener failed: {error}")
        return

    if show_diag and not all_metrics.empty:
        st.subheader("Diagnostics — all stocks (no filters applied)")
        st.caption(
            "Sorted by volume ratio (descending). Use this to see what the universe "
            "actually looks like and tune the filters accordingly."
        )
        diag = all_metrics.sort_values("vol_ratio", ascending=False, na_position="last")
        diag = diag.rename(
            columns={
                "ticker": "Ticker",
                "name": "Name",
                "current_price": "Price",
                "pe": "P/E",
                "vol_ratio": "Vol Ratio",
                "rsi_14": "RSI(14)",
            }
        )
        st.dataframe(
            diag,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Price": st.column_config.NumberColumn(format="%.2f"),
                "P/E": st.column_config.NumberColumn(format="%.2f"),
                "Vol Ratio": st.column_config.NumberColumn(format="%.2fx"),
                "RSI(14)": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        st.divider()

    if results.empty:
        st.info(
            "No tickers matched the current filters. "
            "Tip: enable **Show diagnostics** in the sidebar to see all stocks and their computed metrics, "
            "then adjust the sliders accordingly."
        )
        return

    display = results.rename(
        columns={
            "ticker": "Ticker",
            "name": "Name",
            "current_price": "Price",
            "pe": "P/E",
            "vol_ratio": "Vol Ratio",
            "rsi_14": "RSI(14)",
        }
    )

    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Price": st.column_config.NumberColumn(format="%.2f"),
            "P/E": st.column_config.NumberColumn(format="%.2f"),
            "Vol Ratio": st.column_config.NumberColumn(format="%.2fx"),
            "RSI(14)": st.column_config.NumberColumn(format="%.1f"),
        },
    )


if __name__ == "__main__":
    main()

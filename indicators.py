"""Technical indicators."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index.

    Returns a Series aligned to `close` with NaNs for the first `period` rows.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing == EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    # When avg_loss is zero and avg_gain > 0, RSI is 100 by definition.
    out = out.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    return out

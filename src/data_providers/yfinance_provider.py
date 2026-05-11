from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SOURCE = "yfinance"


def get_latest_price(symbol: str) -> dict:
    generated_at = _utc_now()

    try:
        import yfinance as yf
    except ImportError as exc:
        return _latest_price_error(
            symbol=symbol,
            error=f"yfinance import failed: {exc}",
            timestamp=generated_at,
        )

    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="5d", interval="1d", timeout=10)
        if history is None or history.empty:
            return _latest_price_error(
                symbol=symbol,
                error="No historical price data returned by yfinance",
                timestamp=generated_at,
            )

        if "Close" not in history.columns:
            return _latest_price_error(
                symbol=symbol,
                error="yfinance response is missing Close column",
                timestamp=generated_at,
            )

        close_series = history["Close"].dropna()
        if close_series.empty:
            return _latest_price_error(
                symbol=symbol,
                error="No non-empty close price found in yfinance response",
                timestamp=generated_at,
            )

        latest_date = close_series.index[-1]
        latest_close = float(close_series.iloc[-1])

        return {
            "symbol": symbol,
            "value": latest_close,
            "currency": None,
            "timestamp": _format_market_timestamp(latest_date) or generated_at,
            "source": SOURCE,
            "status": "ok",
            "error": None,
        }
    except Exception as exc:
        return _latest_price_error(
            symbol=symbol,
            error=str(exc),
            timestamp=generated_at,
        )


def get_history(symbol: str, period: str = "3mo", interval: str = "1d") -> dict:
    generated_at = _utc_now()

    try:
        import yfinance as yf
    except ImportError as exc:
        return _history_error(
            symbol=symbol,
            period=period,
            interval=interval,
            error=f"yfinance import failed: {exc}",
            timestamp=generated_at,
        )

    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period, interval=interval, timeout=10)
        if history is None or history.empty:
            return _history_error(
                symbol=symbol,
                period=period,
                interval=interval,
                error="No historical price data returned by yfinance",
                timestamp=generated_at,
            )

        if "Close" not in history.columns:
            return _history_error(
                symbol=symbol,
                period=period,
                interval=interval,
                error="yfinance response is missing Close column",
                timestamp=generated_at,
            )

        data = []
        for index, close in history["Close"].dropna().items():
            data.append(
                {
                    "date": _format_market_timestamp(index),
                    "close": float(close),
                }
            )

        if not data:
            return _history_error(
                symbol=symbol,
                period=period,
                interval=interval,
                error="No non-empty close prices found in yfinance response",
                timestamp=generated_at,
            )

        return {
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "data": data,
            "source": SOURCE,
            "timestamp": generated_at,
            "status": "ok",
            "error": None,
        }
    except Exception as exc:
        return _history_error(
            symbol=symbol,
            period=period,
            interval=interval,
            error=str(exc),
            timestamp=generated_at,
        )


def _latest_price_error(symbol: str, error: str, timestamp: str) -> dict:
    return {
        "symbol": symbol,
        "value": None,
        "currency": None,
        "timestamp": timestamp,
        "source": SOURCE,
        "status": "error",
        "error": error,
    }


def _history_error(
    symbol: str,
    period: str,
    interval: str,
    error: str,
    timestamp: str,
) -> dict:
    return {
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "data": [],
        "source": SOURCE,
        "timestamp": timestamp,
        "status": "error",
        "error": error,
    }


def _format_market_timestamp(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value.hour == 0 and value.minute == 0 and value.second == 0:
            return value.date().isoformat()
        return value.isoformat()

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

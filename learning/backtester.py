"""Backtester: historical replay with no look-ahead bias."""

import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

from utils.console import header, separator, ok, fail
from utils.helpers import format_pct

logger = logging.getLogger("stock_model.learning.backtester")


class Backtester:
    """Replays analysis on historical data to evaluate strategy performance."""

    def __init__(self):
        self.results = []

    def run(self, tickers: list[str], start_date: str, end_date: str = None):
        """Run backtest for given tickers and date range."""
        print(header(f"BACKTEST: {', '.join(tickers)}"))
        print(f"  Period: {start_date} to {end_date or 'present'}")

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

        all_trades = []

        for ticker in tickers:
            print(f"\n  Backtesting {ticker}...")
            trades = self._backtest_ticker(ticker, start, end)
            all_trades.extend(trades)
            self._print_ticker_results(ticker, trades)

        if all_trades:
            self._print_summary(all_trades)

    def _backtest_ticker(self, ticker: str, start: datetime, end: datetime) -> list[dict]:
        """Run backtest for a single ticker using rolling technical signals."""
        try:
            # Get full history with buffer for indicator calculation
            buffer_start = start - timedelta(days=250)
            data = yf.Ticker(ticker).history(
                start=buffer_start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )
            if data.empty or len(data) < 200:
                print(f"    Insufficient data for {ticker}")
                return []
        except Exception as e:
            print(f"    Failed to get data for {ticker}: {e}")
            return []

        close = data["Close"]
        trades = []

        # Simple strategy: SMA crossover + RSI
        from ta.trend import SMAIndicator
        from ta.momentum import RSIIndicator

        sma_50 = SMAIndicator(close, window=50).sma_indicator()
        sma_200 = SMAIndicator(close, window=200).sma_indicator()
        rsi = RSIIndicator(close, window=14).rsi()

        # Walk forward from start date
        in_position = False
        entry_price = 0
        entry_date = None

        # Resample to weekly to simulate weekly review
        dates = [d for d in data.index if d >= pd.Timestamp(start)]

        for i, date in enumerate(dates):
            if date not in sma_50.index or date not in sma_200.index:
                continue

            s50 = sma_50.loc[date]
            s200 = sma_200.loc[date]
            r = rsi.loc[date]
            price = close.loc[date]

            if pd.isna(s50) or pd.isna(s200) or pd.isna(r):
                continue

            # Generate signal (no look-ahead: only using data up to current date)
            bullish = s50 > s200 and r < 70
            bearish = s50 < s200 or r > 80

            if not in_position and bullish:
                in_position = True
                entry_price = price
                entry_date = date
            elif in_position and bearish:
                ret = ((price - entry_price) / entry_price) * 100
                trades.append({
                    "ticker": ticker,
                    "entry_date": entry_date.strftime("%Y-%m-%d"),
                    "exit_date": date.strftime("%Y-%m-%d"),
                    "entry_price": round(float(entry_price), 2),
                    "exit_price": round(float(price), 2),
                    "return_pct": round(float(ret), 2),
                    "holding_days": (date - entry_date).days,
                })
                in_position = False

        # Close any open position at end
        if in_position and len(dates) > 0:
            last_date = dates[-1]
            last_price = close.loc[last_date]
            ret = ((last_price - entry_price) / entry_price) * 100
            trades.append({
                "ticker": ticker,
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "exit_date": last_date.strftime("%Y-%m-%d"),
                "entry_price": round(float(entry_price), 2),
                "exit_price": round(float(last_price), 2),
                "return_pct": round(float(ret), 2),
                "holding_days": (last_date - entry_date).days,
                "still_open": True,
            })

        return trades

    def _print_ticker_results(self, ticker: str, trades: list[dict]):
        """Print results for a single ticker."""
        if not trades:
            print(f"    No trades generated for {ticker}")
            return

        returns = [t["return_pct"] for t in trades]
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r <= 0]

        print(f"    Trades: {len(trades)}")
        print(f"    Win Rate: {len(winners)}/{len(trades)} ({len(winners)/len(trades)*100:.0f}%)")
        print(f"    Avg Return: {format_pct(np.mean(returns))}")
        print(f"    Best Trade: {format_pct(max(returns))}")
        print(f"    Worst Trade: {format_pct(min(returns))}")
        print(f"    Total Return: {format_pct(sum(returns))}")

    def _print_summary(self, all_trades: list[dict]):
        """Print aggregate backtest summary."""
        print(f"\n{separator()}")
        print("  BACKTEST SUMMARY:")

        returns = [t["return_pct"] for t in all_trades]
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r <= 0]

        total_return = sum(returns)
        win_rate = len(winners) / len(returns) * 100 if returns else 0
        avg_win = np.mean(winners) if winners else 0
        avg_loss = np.mean(losers) if losers else 0
        profit_factor = abs(sum(winners) / sum(losers)) if losers and sum(losers) != 0 else float("inf")

        fn = ok if total_return > 0 else fail
        print(f"    Total Trades:  {len(all_trades)}")
        print(f"    Win Rate:      {win_rate:.0f}%")
        print(f"    Avg Win:       {format_pct(avg_win)}")
        print(f"    Avg Loss:      {format_pct(avg_loss)}")
        print(f"    Profit Factor: {profit_factor:.2f}")
        print(f"    Total Return:  {fn(format_pct(total_return))}")

        # Holding period stats
        holding_days = [t["holding_days"] for t in all_trades]
        print(f"    Avg Holding:   {np.mean(holding_days):.0f} days")

        print(f"\n  Note: Backtest uses SMA crossover + RSI strategy.")
        print(f"  Past performance does not guarantee future results.")
        print()

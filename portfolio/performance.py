"""Portfolio performance: returns, Sharpe, Sortino, drawdown, alpha/beta."""

import logging
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

from database.models import PortfolioDAO
from database.connection import get_connection
from utils.console import header, separator, ok, fail, neutral
from utils.helpers import format_pct

logger = logging.getLogger("stock_model.portfolio.performance")

PERIOD_DAYS = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "YTD": None}


class PerformanceTracker:
    """Tracks and reports portfolio performance metrics."""

    def __init__(self):
        self.portfolio_dao = PortfolioDAO()
        self.db = get_connection()

    def calculate_metrics(self, period: str = "3M", benchmark: str = "SPY") -> dict:
        """Calculate performance metrics for a given period."""
        days = PERIOD_DAYS.get(period, 90)
        if days is None:  # YTD
            now = datetime.now()
            days = (now - datetime(now.year, 1, 1)).days

        # Get portfolio snapshots
        snapshots = self.db.execute(
            """SELECT * FROM portfolio_snapshots
               WHERE snapshot_date >= datetime('now', ?)
               ORDER BY snapshot_date ASC""",
            (f"-{days} days",),
        )

        if not snapshots or len(snapshots) < 2:
            return {"error": "Insufficient portfolio snapshot data", "period": period}

        snapshots = list(snapshots)
        equities = [s["total_equity"] for s in snapshots if s["total_equity"]]

        if len(equities) < 2:
            return {"error": "Insufficient equity data", "period": period}

        # Portfolio returns
        total_return = ((equities[-1] - equities[0]) / equities[0]) * 100
        daily_returns = np.diff(equities) / equities[:-1]
        annualized_return = ((equities[-1] / equities[0]) ** (252 / len(daily_returns)) - 1) * 100 if len(daily_returns) > 0 else 0

        # Sharpe Ratio (assuming 5% risk-free rate)
        risk_free_daily = 0.05 / 252
        excess_returns = daily_returns - risk_free_daily
        sharpe = (np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)) if np.std(excess_returns) > 0 else 0

        # Sortino Ratio (downside deviation only)
        downside = daily_returns[daily_returns < 0]
        downside_std = np.std(downside) if len(downside) > 0 else 0.001
        sortino = (np.mean(excess_returns) / downside_std * np.sqrt(252)) if downside_std > 0 else 0

        # Max Drawdown
        cumulative = np.cumprod(1 + daily_returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_drawdown = np.min(drawdowns) * 100 if len(drawdowns) > 0 else 0

        # Benchmark comparison
        benchmark_metrics = self._get_benchmark_metrics(benchmark, days)

        # Alpha and Beta
        alpha = 0
        beta = 0
        if benchmark_metrics and "daily_returns" in benchmark_metrics:
            bm_returns = benchmark_metrics["daily_returns"]
            min_len = min(len(daily_returns), len(bm_returns))
            if min_len > 10:
                port_r = daily_returns[:min_len]
                bm_r = bm_returns[:min_len]
                cov = np.cov(port_r, bm_r)
                beta = cov[0, 1] / cov[1, 1] if cov[1, 1] != 0 else 1
                alpha = (annualized_return - (0.05 + beta * (benchmark_metrics.get("annualized_return", 0) - 5)))

        result = {
            "period": period,
            "benchmark": benchmark,
            "total_return": round(total_return, 2),
            "annualized_return": round(annualized_return, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "max_drawdown": round(max_drawdown, 2),
            "alpha": round(alpha, 2),
            "beta": round(beta, 3),
            "volatility": round(np.std(daily_returns) * np.sqrt(252) * 100, 2),
            "benchmark_return": benchmark_metrics.get("total_return", 0) if benchmark_metrics else 0,
            "num_snapshots": len(snapshots),
        }

        # Store metrics
        self.db.execute_insert(
            """INSERT INTO performance_metrics
               (period, total_return, annualized_return, sharpe_ratio,
                sortino_ratio, max_drawdown, alpha, beta, benchmark)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (period, result["total_return"], result["annualized_return"],
             result["sharpe_ratio"], result["sortino_ratio"],
             result["max_drawdown"], result["alpha"], result["beta"], benchmark),
        )

        return result

    def _get_benchmark_metrics(self, ticker: str, days: int) -> dict | None:
        """Get benchmark returns for comparison."""
        try:
            end = datetime.now()
            start = end - timedelta(days=days + 5)
            data = yf.Ticker(ticker).history(start=start.strftime("%Y-%m-%d"))
            if data.empty or len(data) < 5:
                return None

            close = data["Close"].values
            daily_returns = np.diff(close) / close[:-1]
            total_return = ((close[-1] - close[0]) / close[0]) * 100
            annualized = ((close[-1] / close[0]) ** (252 / len(daily_returns)) - 1) * 100

            return {
                "total_return": round(total_return, 2),
                "annualized_return": round(annualized, 2),
                "daily_returns": daily_returns,
            }
        except Exception as e:
            logger.warning("Benchmark %s fetch failed: %s", ticker, e)
            return None

    def print_report(self, period: str = "3M"):
        """Print a formatted performance report."""
        metrics = self.calculate_metrics(period)

        print(header(f"PERFORMANCE REPORT ({period})"))

        if "error" in metrics:
            print(f"\n  {metrics['error']}")
            print("  Import your portfolio and wait for snapshots to accumulate.")
            return

        benchmark = metrics.get("benchmark", "SPY")

        # Returns
        print(f"\n  RETURNS:")
        total_ret = metrics["total_return"]
        fn = ok if total_ret > 0 else fail
        print(f"    Total Return:      {fn(format_pct(total_ret))}")
        print(f"    Annualized Return: {format_pct(metrics['annualized_return'])}")
        print(f"    Benchmark ({benchmark}):  {format_pct(metrics['benchmark_return'])}")

        outperformance = total_ret - metrics["benchmark_return"]
        fn = ok if outperformance > 0 else fail
        print(f"    Outperformance:    {fn(format_pct(outperformance))}")

        # Risk metrics
        print(f"\n  RISK METRICS:")
        print(f"    Volatility:        {format_pct(metrics['volatility'])}")
        print(f"    Max Drawdown:      {format_pct(metrics['max_drawdown'])}")
        print(f"    Beta:              {metrics['beta']:.3f}")

        # Risk-adjusted
        print(f"\n  RISK-ADJUSTED:")
        sharpe = metrics["sharpe_ratio"]
        fn = ok if sharpe > 1 else neutral if sharpe > 0.5 else fail
        print(f"    Sharpe Ratio:      {fn(f'{sharpe:.3f}')}")

        sortino = metrics["sortino_ratio"]
        fn = ok if sortino > 1.5 else neutral if sortino > 0.5 else fail
        print(f"    Sortino Ratio:     {fn(f'{sortino:.3f}')}")

        alpha = metrics["alpha"]
        fn = ok if alpha > 0 else fail
        print(f"    Alpha:             {fn(format_pct(alpha))}")

        print()

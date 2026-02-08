"""Outcome tracker: measure actual returns at 1W, 1M, 3M, 6M after decisions."""

import logging
from datetime import datetime, timedelta
import yfinance as yf

from database.connection import get_connection
from database.models import DecisionDAO

logger = logging.getLogger("stock_model.learning.outcome_tracker")

# Time windows to track (label, days)
OUTCOME_WINDOWS = [
    ("1w", 7),
    ("1m", 30),
    ("3m", 90),
    ("6m", 180),
]


class OutcomeTracker:
    """Tracks actual price outcomes after each decision."""

    def __init__(self):
        self.db = get_connection()
        self.decision_dao = DecisionDAO()

    def update_all(self):
        """Update outcomes for all decisions that have matured."""
        decisions = self.decision_dao.get_pending_outcomes()
        if not decisions:
            print("No decisions with pending outcomes.")
            return

        decisions = list(decisions)
        updated = 0
        now = datetime.now()

        for decision in decisions:
            decision_id = decision["id"]
            ticker = decision["ticker"]
            decided_at = decision["decided_at"]

            # Parse decision date
            try:
                if isinstance(decided_at, str):
                    dt = datetime.fromisoformat(decided_at)
                else:
                    dt = decided_at
            except (ValueError, TypeError):
                continue

            # Check which windows have matured
            for label, days in OUTCOME_WINDOWS:
                col = f"outcome_{label}"
                # Skip if already filled
                if decision[col] is not None:
                    continue

                # Check if enough time has passed
                if (now - dt).days < days:
                    continue

                # Get price at decision time and at outcome time
                outcome_return = self._get_return(ticker, dt, days)
                if outcome_return is not None:
                    self.decision_dao.update_outcome(decision_id, label, outcome_return)
                    updated += 1
                    logger.info(
                        "Updated %s outcome for decision %d (%s): %+.2f%%",
                        label, decision_id, ticker, outcome_return
                    )

            # Also update decision_outcomes table
            self._update_outcomes_table(decision)

        print(f"Updated {updated} outcome entries across {len(decisions)} decisions.")

    def _get_return(self, ticker: str, decision_date: datetime, days: int) -> float | None:
        """Calculate actual return from decision date to N days later."""
        try:
            start = decision_date - timedelta(days=2)
            end = decision_date + timedelta(days=days + 5)

            data = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )

            if data.empty or len(data) < 2:
                return None

            # Find closest price to decision date
            decision_str = decision_date.strftime("%Y-%m-%d")
            close_prices = data["Close"]

            # Price at/near decision
            price_at_decision = None
            for i in range(len(close_prices)):
                if str(close_prices.index[i].date()) >= decision_str:
                    price_at_decision = close_prices.iloc[i]
                    break
            if price_at_decision is None:
                price_at_decision = close_prices.iloc[0]

            # Price at outcome window
            target_date = decision_date + timedelta(days=days)
            target_str = target_date.strftime("%Y-%m-%d")
            price_at_outcome = None
            for i in range(len(close_prices) - 1, -1, -1):
                if str(close_prices.index[i].date()) <= target_str:
                    price_at_outcome = close_prices.iloc[i]
                    break
            if price_at_outcome is None:
                price_at_outcome = close_prices.iloc[-1]

            if price_at_decision and price_at_decision > 0:
                return round(((price_at_outcome - price_at_decision) / price_at_decision) * 100, 2)
            return None
        except Exception as e:
            logger.warning("Return calculation failed for %s: %s", ticker, e)
            return None

    def _update_outcomes_table(self, decision):
        """Update the decision_outcomes detail table."""
        decision_id = decision["id"]
        ticker = decision["ticker"]

        existing = self.db.execute_one(
            "SELECT id FROM decision_outcomes WHERE decision_id = ?",
            (decision_id,),
        )

        if not existing:
            self.db.execute_insert(
                """INSERT INTO decision_outcomes
                   (decision_id, ticker, decided_at, price_at_decision,
                    return_1w, return_1m, return_3m, return_6m)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision_id, ticker, decision["decided_at"],
                    None,
                    decision.get("outcome_1w"),
                    decision.get("outcome_1m"),
                    decision.get("outcome_3m"),
                    decision.get("outcome_6m"),
                ),
            )
        else:
            self.db.execute(
                """UPDATE decision_outcomes SET
                     return_1w = COALESCE(?, return_1w),
                     return_1m = COALESCE(?, return_1m),
                     return_3m = COALESCE(?, return_3m),
                     return_6m = COALESCE(?, return_6m),
                     updated_at = CURRENT_TIMESTAMP
                   WHERE decision_id = ?""",
                (
                    decision.get("outcome_1w"),
                    decision.get("outcome_1m"),
                    decision.get("outcome_3m"),
                    decision.get("outcome_6m"),
                    decision_id,
                ),
            )

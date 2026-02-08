"""Weight optimizer: conservative automatic weight adjustment based on accuracy."""

import json
import logging
import numpy as np
from datetime import datetime

from config.settings import get_settings
from database.connection import get_connection
from utils.console import header, separator, ok, fail, neutral

logger = logging.getLogger("stock_model.learning.weight_optimizer")

# Constraints
MIN_DECISIONS_REQUIRED = 50
MAX_WEIGHT_CHANGE = 0.05  # +/- 5% per optimization
SMOOTHING_FACTOR = 0.30   # 30% new, 70% old
MIN_WEIGHT = 0.02         # No weight below 2%
MANUAL_APPROVAL_RUNS = 3  # First 3 runs require manual approval


class WeightOptimizer:
    """Optimizes analyzer weights based on historical accuracy."""

    def __init__(self):
        self.settings = get_settings()
        self.db = get_connection()

    def optimize(self, auto_approve: bool = False):
        """Run weight optimization."""
        print(header("WEIGHT OPTIMIZATION"))

        # Check prerequisites
        decision_count = self.db.execute_one(
            "SELECT COUNT(*) as cnt FROM decisions WHERE outcome_1m IS NOT NULL"
        )
        count = decision_count["cnt"] if decision_count else 0

        if count < MIN_DECISIONS_REQUIRED:
            print(f"\n  Need at least {MIN_DECISIONS_REQUIRED} decisions with outcomes.")
            print(f"  Currently have: {count}")
            print(f"  Keep analyzing stocks and tracking outcomes.")
            return

        # Get current weights
        current_weights = dict(self.settings.analysis_weights)
        print(f"\n  Current weights:")
        for name, weight in sorted(current_weights.items()):
            print(f"    {name:<16} {weight:.2f} ({weight*100:.0f}%)")

        # Calculate optimal weights based on accuracy
        new_weights = self._calculate_optimal_weights(current_weights)

        if not new_weights:
            print(f"\n  {fail('Could not calculate new weights. Insufficient data.')}")
            return

        # Apply smoothing and constraints
        adjusted = self._apply_constraints(current_weights, new_weights)

        print(f"\n  Proposed weights:")
        changes = []
        for name in sorted(adjusted.keys()):
            old = current_weights.get(name, 0)
            new = adjusted[name]
            diff = new - old
            fn = ok if abs(diff) < 0.01 else neutral
            changes.append((name, old, new, diff))
            print(f"    {name:<16} {old:.2f} -> {new:.2f} ({diff:+.3f})")

        # Check if manual approval is needed
        run_count = self.db.execute_one(
            "SELECT COUNT(*) as cnt FROM weight_history WHERE approved = 1"
        )
        runs = run_count["cnt"] if run_count else 0

        needs_approval = runs < MANUAL_APPROVAL_RUNS and not auto_approve

        # Store proposed weights
        self.db.execute_insert(
            """INSERT INTO weight_history (weights_json, reason, approved)
               VALUES (?, ?, ?)""",
            (
                json.dumps(adjusted),
                f"Optimization run #{runs + 1}: based on {count} decisions",
                0 if needs_approval else 1,
            ),
        )

        if needs_approval:
            print(f"\n  This is run #{runs + 1} of {MANUAL_APPROVAL_RUNS} requiring approval.")
            print(f"  Review the proposed weights above.")
            print(f"  To approve, run: python main.py optimize-weights --auto")
            print(f"  Weights will auto-apply after {MANUAL_APPROVAL_RUNS} successful runs.")
        else:
            # Auto-apply
            self._apply_weights(adjusted)
            print(f"\n  {ok('Weights updated successfully!')}")

    def _calculate_optimal_weights(self, current_weights: dict) -> dict | None:
        """Calculate optimal weights from analyzer accuracy data."""
        accuracy_data = self.db.execute(
            """SELECT analyzer_name,
                      AVG(direction_accuracy) as avg_accuracy,
                      AVG(information_coefficient) as avg_ic,
                      SUM(total_predictions) as total_preds
               FROM analyzer_accuracy
               WHERE period = '1m'
               GROUP BY analyzer_name"""
        )

        if not accuracy_data:
            return None

        accuracy_data = list(accuracy_data)

        # Score each analyzer: weighted combination of accuracy and IC
        scores = {}
        for row in accuracy_data:
            name = row["analyzer_name"]
            accuracy = row["avg_accuracy"] or 50
            ic = row["avg_ic"] or 0
            preds = row["total_preds"] or 0

            # Combined score: 60% accuracy, 30% IC, 10% data volume
            score = (
                (accuracy / 100) * 0.6 +
                max(0, ic) * 0.3 +
                min(1, preds / 100) * 0.1
            )
            scores[name] = max(0.01, score)

        # Normalize to sum to 1.0
        total = sum(scores.values())
        if total == 0:
            return None

        new_weights = {}
        for name in current_weights:
            if name in scores:
                new_weights[name] = scores[name] / total
            else:
                new_weights[name] = current_weights[name]

        # Re-normalize
        total = sum(new_weights.values())
        return {k: v / total for k, v in new_weights.items()}

    def _apply_constraints(self, current: dict, proposed: dict) -> dict:
        """Apply smoothing and constraints to proposed weights."""
        adjusted = {}

        for name in current:
            old = current[name]
            new = proposed.get(name, old)

            # Smoothing: 70% old + 30% new
            smoothed = old * (1 - SMOOTHING_FACTOR) + new * SMOOTHING_FACTOR

            # Max change per optimization
            diff = smoothed - old
            if abs(diff) > MAX_WEIGHT_CHANGE:
                smoothed = old + MAX_WEIGHT_CHANGE * (1 if diff > 0 else -1)

            # Floor
            smoothed = max(MIN_WEIGHT, smoothed)
            adjusted[name] = smoothed

        # Re-normalize to sum to 1.0
        total = sum(adjusted.values())
        adjusted = {k: v / total for k, v in adjusted.items()}

        return {k: round(v, 4) for k, v in adjusted.items()}

    def _apply_weights(self, weights: dict):
        """Apply new weights to the settings."""
        # Update app_config in database
        self.db.execute_insert(
            """INSERT OR REPLACE INTO app_config (key, value)
               VALUES ('analysis_weights', ?)""",
            (json.dumps(weights),),
        )

        # Mark latest weight history as approved
        self.db.execute(
            """UPDATE weight_history SET approved = 1
               WHERE id = (SELECT MAX(id) FROM weight_history)"""
        )

        logger.info("Applied new weights: %s", weights)

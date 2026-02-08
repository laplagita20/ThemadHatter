"""Accuracy tracker: per-analyzer predictive accuracy and performance stats."""

import logging
import json
import numpy as np
from datetime import datetime

from database.connection import get_connection
from utils.console import header, separator, ok, fail, neutral
from tabulate import tabulate

logger = logging.getLogger("stock_model.learning.accuracy_tracker")


class AccuracyTracker:
    """Tracks and reports per-analyzer predictive accuracy."""

    def __init__(self):
        self.db = get_connection()

    def calculate_accuracy(self, period: str = "1m") -> list[dict]:
        """Calculate accuracy metrics for each analyzer."""
        # Get decisions with outcomes
        outcome_col = f"outcome_{period}"
        decisions = self.db.execute(
            f"""SELECT d.id, d.ticker, d.action, d.composite_score,
                       d.{outcome_col} as outcome, d.analysis_breakdown_json
                FROM decisions d
                WHERE d.{outcome_col} IS NOT NULL""",
        )

        if not decisions:
            return []

        decisions = list(decisions)

        # Analyze each analyzer's contribution
        analyzer_stats = {}

        for decision in decisions:
            outcome = decision["outcome"]
            if outcome is None:
                continue

            # Parse analysis breakdown
            try:
                breakdown = json.loads(decision["analysis_breakdown_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                continue

            actual_direction = 1 if outcome > 0 else -1 if outcome < 0 else 0

            for analyzer_name, result in breakdown.items():
                if analyzer_name not in analyzer_stats:
                    analyzer_stats[analyzer_name] = {
                        "predictions": [],
                        "correct": 0,
                        "total": 0,
                        "scores_when_correct": [],
                        "scores_when_wrong": [],
                    }

                stats = analyzer_stats[analyzer_name]
                score = result.get("score", 0)
                predicted_direction = 1 if score > 0 else -1 if score < 0 else 0

                stats["total"] += 1
                stats["predictions"].append((score, outcome))

                if predicted_direction == actual_direction and actual_direction != 0:
                    stats["correct"] += 1
                    stats["scores_when_correct"].append(abs(score))
                elif predicted_direction != 0:
                    stats["scores_when_wrong"].append(abs(score))

        # Calculate metrics
        results = []
        for name, stats in analyzer_stats.items():
            total = stats["total"]
            correct = stats["correct"]
            direction_accuracy = (correct / total * 100) if total > 0 else 0

            # Information Coefficient (correlation between predictions and outcomes)
            ic = 0
            if len(stats["predictions"]) > 5:
                scores = [p[0] for p in stats["predictions"]]
                outcomes = [p[1] for p in stats["predictions"]]
                if np.std(scores) > 0 and np.std(outcomes) > 0:
                    ic = float(np.corrcoef(scores, outcomes)[0, 1])

            mean_correct = np.mean(stats["scores_when_correct"]) if stats["scores_when_correct"] else 0
            mean_wrong = np.mean(stats["scores_when_wrong"]) if stats["scores_when_wrong"] else 0

            result = {
                "analyzer_name": name,
                "period": period,
                "total_predictions": total,
                "correct_direction": correct,
                "direction_accuracy": round(direction_accuracy, 1),
                "mean_score_when_correct": round(mean_correct, 1),
                "mean_score_when_wrong": round(mean_wrong, 1),
                "information_coefficient": round(ic, 3),
            }
            results.append(result)

            # Store in database
            self.db.execute_insert(
                """INSERT OR REPLACE INTO analyzer_accuracy
                   (analyzer_name, period, total_predictions, correct_direction,
                    direction_accuracy, mean_score_when_correct,
                    mean_score_when_wrong, information_coefficient)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, period, total, correct, direction_accuracy,
                 mean_correct, mean_wrong, ic),
            )

        return sorted(results, key=lambda x: x["direction_accuracy"], reverse=True)

    def print_report(self):
        """Print a formatted accuracy report for all time windows."""
        print(header("ANALYZER ACCURACY REPORT"))

        for period in ["1w", "1m", "3m"]:
            results = self.calculate_accuracy(period)
            if not results:
                print(f"\n  {period.upper()}: No data available")
                continue

            print(f"\n  {period.upper()} OUTCOMES:")
            table_data = []
            for r in results:
                acc = r["direction_accuracy"]
                fn = ok if acc > 55 else fail if acc < 45 else neutral
                table_data.append([
                    r["analyzer_name"].title(),
                    r["total_predictions"],
                    f"{r['correct_direction']}/{r['total_predictions']}",
                    fn(f"{acc:.1f}%"),
                    f"{r['information_coefficient']:.3f}",
                    f"{r['mean_score_when_correct']:.1f}",
                    f"{r['mean_score_when_wrong']:.1f}",
                ])

            headers = ["Analyzer", "Total", "Correct", "Accuracy", "IC", "Avg|Correct|", "Avg|Wrong|"]
            print(tabulate(table_data, headers=headers, tablefmt="simple"))

        # Overall assessment
        all_results = self.calculate_accuracy("1m")
        if all_results:
            best = max(all_results, key=lambda x: x["direction_accuracy"])
            worst = min(all_results, key=lambda x: x["direction_accuracy"])
            print(f"\n  Best Performer:  {best['analyzer_name'].title()} ({best['direction_accuracy']:.1f}%)")
            print(f"  Worst Performer: {worst['analyzer_name'].title()} ({worst['direction_accuracy']:.1f}%)")

            high_ic = [r for r in all_results if r["information_coefficient"] > 0.1]
            if high_ic:
                print(f"  High IC Analyzers: {', '.join(r['analyzer_name'].title() for r in high_ic)}")

        print()

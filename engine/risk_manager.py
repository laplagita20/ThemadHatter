"""Risk manager: Kelly Criterion, VaR, Monte Carlo, correlation, stress testing, drawdown.

Professional-grade portfolio risk management used by hedge funds and institutional investors.
"""

import logging
import json
import numpy as np
from datetime import datetime, timedelta

from config.settings import get_settings
from database.models import PortfolioDAO, PriceDAO, RiskSimulationDAO
from database.connection import get_connection

logger = logging.getLogger("stock_model.engine.risk")


class RiskManager:
    """Professional-grade portfolio risk management."""

    def __init__(self, user_id: int = None):
        self.settings = get_settings()
        self.portfolio_dao = PortfolioDAO()
        self.price_dao = PriceDAO()
        self.risk_dao = RiskSimulationDAO()
        self.db = get_connection()
        self._user_id = user_id

    def _get_holdings(self):
        """Get holdings for the current user (or all if no user)."""
        return self.portfolio_dao.get_latest_holdings(self._user_id)

    # =========================================================================
    # Original Risk Checks (preserved)
    # =========================================================================
    def check_position_size(self, ticker: str, proposed_pct: float) -> dict:
        max_pct = self.settings.max_single_position_pct
        if proposed_pct > max_pct:
            return {
                "allowed": False,
                "adjusted_pct": max_pct,
                "reason": f"Position size {proposed_pct:.1f}% exceeds max {max_pct:.1f}%",
            }
        return {"allowed": True, "adjusted_pct": proposed_pct, "reason": "Within limits"}

    def check_sector_concentration(self, sector: str) -> dict:
        holdings = self._get_holdings()
        if not holdings:
            return {"allowed": True, "current_pct": 0, "reason": "No existing holdings"}

        total_value = sum(h["market_value"] or 0 for h in holdings)
        if total_value == 0:
            return {"allowed": True, "current_pct": 0, "reason": "No portfolio value"}

        sector_value = sum(
            h["market_value"] or 0 for h in holdings
            if (h["sector"] or "").lower() == sector.lower()
        )
        sector_pct = (sector_value / total_value) * 100

        max_pct = self.settings.max_single_sector_pct
        if sector_pct >= max_pct:
            return {
                "allowed": False,
                "current_pct": sector_pct,
                "reason": f"Sector {sector} at {sector_pct:.1f}% (max {max_pct:.1f}%)",
            }
        return {"allowed": True, "current_pct": sector_pct, "reason": "Within limits"}

    def check_diversification(self) -> dict:
        holdings = self._get_holdings()
        if not holdings:
            return {"meets_minimum": False, "num_sectors": 0, "reason": "No holdings"}

        sectors = set(h["sector"] for h in holdings if h["sector"])
        num_sectors = len(sectors)
        min_sectors = self.settings.min_sectors_held

        return {
            "meets_minimum": num_sectors >= min_sectors,
            "num_sectors": num_sectors,
            "sectors": list(sectors),
            "reason": f"{num_sectors} sectors (min {min_sectors})",
        }

    def calculate_stop_loss(self, entry_price: float, conviction: str) -> dict:
        s = self.settings
        if conviction == "high":
            trailing_pct = s.trailing_stop_tactical_pct
        else:
            trailing_pct = s.trailing_stop_core_pct

        return {
            "trailing_stop_pct": trailing_pct,
            "trailing_stop_price": entry_price * (1 - trailing_pct / 100),
            "hard_stop_pct": s.hard_stop_pct,
            "hard_stop_price": entry_price * (1 - s.hard_stop_pct / 100),
        }

    def get_portfolio_risk_summary(self) -> dict:
        holdings = self._get_holdings()
        if not holdings:
            return {"status": "no_holdings"}

        total_value = sum(h["market_value"] or 0 for h in holdings)
        if total_value == 0:
            return {"status": "no_value"}

        positions = []
        for h in holdings:
            pct = ((h["market_value"] or 0) / total_value) * 100
            positions.append({"ticker": h["ticker"], "weight_pct": pct})
        positions.sort(key=lambda x: x["weight_pct"], reverse=True)

        sector_weights = {}
        for h in holdings:
            sector = h["sector"] or "Unknown"
            sector_weights[sector] = sector_weights.get(sector, 0) + ((h["market_value"] or 0) / total_value * 100)

        hhi = sum(p["weight_pct"] ** 2 for p in positions) / 10000

        return {
            "status": "ok",
            "total_value": total_value,
            "num_positions": len(holdings),
            "num_sectors": len(sector_weights),
            "top_positions": positions[:5],
            "sector_weights": dict(sorted(sector_weights.items(), key=lambda x: -x[1])),
            "max_position_pct": positions[0]["weight_pct"] if positions else 0,
            "max_sector_pct": max(sector_weights.values()) if sector_weights else 0,
            "hhi": hhi,
        }

    # =========================================================================
    # Kelly Criterion Position Sizing
    # =========================================================================
    def kelly_criterion(self, ticker: str = None, use_half_kelly: bool = True) -> dict:
        """Calculate optimal position size using Kelly Criterion.

        Kelly % = W - (1-W)/R
        W = win rate, R = avg win / avg loss ratio
        """
        try:
            outcomes = self.db.execute(
                """SELECT action_was_correct, return_1m FROM decision_outcomes
                   WHERE return_1m IS NOT NULL
                   ORDER BY updated_at DESC LIMIT 100"""
            )
            outcomes = list(outcomes)

            if len(outcomes) < 30:
                return {
                    "kelly_pct": None,
                    "half_kelly_pct": None,
                    "reason": f"Insufficient history ({len(outcomes)} outcomes, need 30+)",
                    "fallback_pct": self.settings.position_size_medium_conviction,
                }

            wins = [o for o in outcomes if o["return_1m"] and o["return_1m"] > 0]
            losses = [o for o in outcomes if o["return_1m"] and o["return_1m"] < 0]

            if not wins or not losses:
                return {
                    "kelly_pct": None,
                    "half_kelly_pct": None,
                    "reason": "Need both wins and losses for Kelly calculation",
                    "fallback_pct": self.settings.position_size_medium_conviction,
                }

            win_rate = len(wins) / len(outcomes)
            avg_win = np.mean([w["return_1m"] for w in wins])
            avg_loss = abs(np.mean([l["return_1m"] for l in losses]))

            if avg_loss == 0:
                return {"kelly_pct": 0, "reason": "Zero average loss"}

            win_loss_ratio = avg_win / avg_loss
            kelly_pct = (win_rate - (1 - win_rate) / win_loss_ratio) * 100
            kelly_pct = max(0, kelly_pct)  # Never negative

            half_kelly = kelly_pct / 2 if use_half_kelly else kelly_pct

            # Cap at max position size
            max_pos = self.settings.max_single_position_pct
            recommended = min(half_kelly, max_pos)

            return {
                "kelly_pct": round(kelly_pct, 2),
                "half_kelly_pct": round(half_kelly, 2),
                "recommended_pct": round(recommended, 2),
                "win_rate": round(win_rate, 3),
                "win_loss_ratio": round(win_loss_ratio, 3),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "sample_size": len(outcomes),
            }
        except Exception as e:
            logger.warning("Kelly Criterion calculation failed: %s", e)
            return {"kelly_pct": None, "reason": str(e), "fallback_pct": self.settings.position_size_medium_conviction}

    # =========================================================================
    # Value at Risk (VaR)
    # =========================================================================
    def calculate_var(self, confidence_level: float = 0.95, horizon_days: int = 1) -> dict:
        """Calculate Value at Risk using historical and parametric methods.

        VaR answers: 'What is the maximum loss at X% confidence over Y days?'
        """
        try:
            holdings = self._get_holdings()
            if not holdings:
                return {"error": "No portfolio holdings"}

            total_value = sum(h["market_value"] or 0 for h in holdings)
            if total_value == 0:
                return {"error": "No portfolio value"}

            # Get daily returns for each holding
            all_returns = []
            weights = []
            for h in holdings:
                history = list(self.price_dao.get_history(h["ticker"], days=252))
                if len(history) < 30:
                    continue

                prices = [row["close"] for row in reversed(history) if row["close"]]
                if len(prices) < 30:
                    continue

                returns = np.diff(prices) / prices[:-1]
                all_returns.append(returns)
                weights.append((h["market_value"] or 0) / total_value)

            if not all_returns:
                return {"error": "Insufficient price history"}

            # Align return series to same length
            min_len = min(len(r) for r in all_returns)
            aligned_returns = np.array([r[-min_len:] for r in all_returns])
            weights = np.array(weights[:len(all_returns)])
            weights = weights / weights.sum()

            # Portfolio returns
            portfolio_returns = np.dot(weights, aligned_returns)

            # Historical VaR
            alpha = 1 - confidence_level
            historical_var = np.percentile(portfolio_returns, alpha * 100)
            historical_var_dollar = abs(historical_var) * total_value * np.sqrt(horizon_days)

            # Parametric VaR
            mu = np.mean(portfolio_returns)
            sigma = np.std(portfolio_returns)
            from scipy.stats import norm
            z_score = norm.ppf(alpha)
            parametric_var = -(mu + z_score * sigma) * np.sqrt(horizon_days)
            parametric_var_dollar = parametric_var * total_value

            # CVaR (Conditional VaR / Expected Shortfall)
            tail_returns = portfolio_returns[portfolio_returns <= np.percentile(portfolio_returns, alpha * 100)]
            cvar = abs(np.mean(tail_returns)) if len(tail_returns) > 0 else abs(historical_var)
            cvar_dollar = cvar * total_value * np.sqrt(horizon_days)

            # Also calculate 99% VaR
            var_99 = abs(np.percentile(portfolio_returns, 1))
            var_99_dollar = var_99 * total_value * np.sqrt(horizon_days)

            result = {
                "portfolio_value": round(total_value, 2),
                "horizon_days": horizon_days,
                "confidence_level": confidence_level,
                "historical_var_pct": round(abs(historical_var) * 100 * np.sqrt(horizon_days), 3),
                "historical_var_dollar": round(historical_var_dollar, 2),
                "parametric_var_pct": round(parametric_var * 100, 3),
                "parametric_var_dollar": round(parametric_var_dollar, 2),
                "cvar_pct": round(cvar * 100 * np.sqrt(horizon_days), 3),
                "cvar_dollar": round(cvar_dollar, 2),
                "var_99_pct": round(var_99 * 100 * np.sqrt(horizon_days), 3),
                "var_99_dollar": round(var_99_dollar, 2),
                "portfolio_volatility_annual": round(sigma * np.sqrt(252) * 100, 2),
                "data_points": min_len,
            }

            # Store
            try:
                self.risk_dao.insert({
                    "simulation_type": "var",
                    "portfolio_value": total_value,
                    "var_95": result["historical_var_dollar"],
                    "var_99": result["var_99_dollar"],
                    "cvar_95": result["cvar_dollar"],
                    "parameters": {
                        "confidence": confidence_level,
                        "horizon": horizon_days,
                        "volatility": result["portfolio_volatility_annual"],
                    },
                })
            except Exception as e:
                logger.debug("VaR storage failed: %s", e)

            return result
        except ImportError:
            # scipy not available, use simplified version
            return self._calculate_var_simple(confidence_level, horizon_days)
        except Exception as e:
            logger.warning("VaR calculation failed: %s", e)
            return {"error": str(e)}

    def _calculate_var_simple(self, confidence_level: float = 0.95, horizon_days: int = 1) -> dict:
        """Simplified VaR without scipy."""
        try:
            holdings = self._get_holdings()
            if not holdings:
                return {"error": "No portfolio holdings"}

            total_value = sum(h["market_value"] or 0 for h in holdings)
            all_returns = []
            weights = []

            for h in holdings:
                history = list(self.price_dao.get_history(h["ticker"], days=252))
                if len(history) < 30:
                    continue
                prices = [row["close"] for row in reversed(history) if row["close"]]
                if len(prices) < 30:
                    continue
                returns = np.diff(prices) / prices[:-1]
                all_returns.append(returns)
                weights.append((h["market_value"] or 0) / total_value)

            if not all_returns:
                return {"error": "Insufficient data"}

            min_len = min(len(r) for r in all_returns)
            aligned = np.array([r[-min_len:] for r in all_returns])
            weights = np.array(weights[:len(all_returns)])
            weights = weights / weights.sum()

            portfolio_returns = np.dot(weights, aligned)
            alpha = 1 - confidence_level
            var = abs(np.percentile(portfolio_returns, alpha * 100))

            # Z-scores lookup (no scipy needed)
            z_lookup = {0.95: 1.645, 0.99: 2.326, 0.975: 1.96}
            z = z_lookup.get(confidence_level, 1.645)
            sigma = np.std(portfolio_returns)
            parametric_var = z * sigma * np.sqrt(horizon_days)

            return {
                "portfolio_value": round(total_value, 2),
                "historical_var_pct": round(var * 100 * np.sqrt(horizon_days), 3),
                "historical_var_dollar": round(var * total_value * np.sqrt(horizon_days), 2),
                "parametric_var_pct": round(parametric_var * 100, 3),
                "parametric_var_dollar": round(parametric_var * total_value, 2),
                "portfolio_volatility_annual": round(sigma * np.sqrt(252) * 100, 2),
            }
        except Exception as e:
            return {"error": str(e)}

    # =========================================================================
    # Monte Carlo Simulation
    # =========================================================================
    def monte_carlo_simulation(self, num_simulations: int = 10000,
                                horizon_days: int = 252) -> dict:
        """Run Monte Carlo simulation of portfolio outcomes over the given horizon.

        Returns probability distribution of portfolio values.
        """
        try:
            holdings = self._get_holdings()
            if not holdings:
                return {"error": "No portfolio holdings"}

            total_value = sum(h["market_value"] or 0 for h in holdings)
            if total_value == 0:
                return {"error": "No portfolio value"}

            # Get returns for portfolio
            all_returns = []
            weights = []
            tickers_used = []

            for h in holdings:
                history = list(self.price_dao.get_history(h["ticker"], days=252))
                if len(history) < 30:
                    continue

                prices = [row["close"] for row in reversed(history) if row["close"]]
                if len(prices) < 30:
                    continue

                returns = np.diff(prices) / prices[:-1]
                all_returns.append(returns)
                weights.append((h["market_value"] or 0) / total_value)
                tickers_used.append(h["ticker"])

            if not all_returns:
                return {"error": "Insufficient price history for simulation"}

            min_len = min(len(r) for r in all_returns)
            aligned_returns = np.array([r[-min_len:] for r in all_returns])
            weights = np.array(weights[:len(all_returns)])
            weights = weights / weights.sum()

            portfolio_returns = np.dot(weights, aligned_returns)
            mu = np.mean(portfolio_returns)
            sigma = np.std(portfolio_returns)

            # Run simulations using geometric Brownian motion
            np.random.seed(42)
            simulated_returns = np.random.normal(mu, sigma, (num_simulations, horizon_days))
            simulated_paths = total_value * np.cumprod(1 + simulated_returns, axis=1)

            final_values = simulated_paths[:, -1]

            # Calculate percentiles
            percentiles = {
                "p5": float(np.percentile(final_values, 5)),
                "p10": float(np.percentile(final_values, 10)),
                "p25": float(np.percentile(final_values, 25)),
                "p50": float(np.percentile(final_values, 50)),
                "p75": float(np.percentile(final_values, 75)),
                "p90": float(np.percentile(final_values, 90)),
                "p95": float(np.percentile(final_values, 95)),
            }

            # Probability of various returns
            prob_positive = float(np.mean(final_values > total_value))
            prob_10pct_gain = float(np.mean(final_values > total_value * 1.10))
            prob_10pct_loss = float(np.mean(final_values < total_value * 0.90))
            prob_25pct_loss = float(np.mean(final_values < total_value * 0.75))

            # Sample paths for charting (10 representative paths)
            sample_indices = np.linspace(0, num_simulations - 1, 10, dtype=int)
            sample_paths = simulated_paths[sample_indices].tolist()

            # Percentile paths for fan chart
            p10_path = np.percentile(simulated_paths, 10, axis=0).tolist()
            p50_path = np.percentile(simulated_paths, 50, axis=0).tolist()
            p90_path = np.percentile(simulated_paths, 90, axis=0).tolist()

            result = {
                "portfolio_value": round(total_value, 2),
                "horizon_days": horizon_days,
                "num_simulations": num_simulations,
                "expected_value": round(float(np.mean(final_values)), 2),
                "expected_return_pct": round((np.mean(final_values) / total_value - 1) * 100, 2),
                "percentiles": {k: round(v, 2) for k, v in percentiles.items()},
                "bear_case": round(percentiles["p10"], 2),
                "base_case": round(percentiles["p50"], 2),
                "bull_case": round(percentiles["p90"], 2),
                "prob_positive_return": round(prob_positive, 3),
                "prob_10pct_gain": round(prob_10pct_gain, 3),
                "prob_10pct_loss": round(prob_10pct_loss, 3),
                "prob_25pct_loss": round(prob_25pct_loss, 3),
                "fan_chart": {
                    "p10": p10_path[::max(1, len(p10_path) // 50)],  # Downsample for storage
                    "p50": p50_path[::max(1, len(p50_path) // 50)],
                    "p90": p90_path[::max(1, len(p90_path) // 50)],
                },
                "annualized_return_mu": round(mu * 252 * 100, 2),
                "annualized_volatility": round(sigma * np.sqrt(252) * 100, 2),
            }

            # Store
            try:
                self.risk_dao.insert({
                    "simulation_type": "monte_carlo",
                    "portfolio_value": total_value,
                    "var_95": round(total_value - percentiles["p5"], 2),
                    "var_99": None,
                    "cvar_95": None,
                    "monte_carlo": {
                        "percentiles": result["percentiles"],
                        "probabilities": {
                            "positive": result["prob_positive_return"],
                            "gain_10pct": result["prob_10pct_gain"],
                            "loss_10pct": result["prob_10pct_loss"],
                        },
                    },
                    "parameters": {
                        "simulations": num_simulations,
                        "horizon": horizon_days,
                        "mu": round(mu, 6),
                        "sigma": round(sigma, 6),
                    },
                })
            except Exception as e:
                logger.debug("Monte Carlo storage failed: %s", e)

            return result
        except Exception as e:
            logger.warning("Monte Carlo simulation failed: %s", e)
            return {"error": str(e)}

    # =========================================================================
    # Correlation Matrix & Diversification Score
    # =========================================================================
    def calculate_correlation_matrix(self) -> dict:
        """Calculate pairwise correlations and diversification ratio."""
        try:
            holdings = self._get_holdings()
            if not holdings or len(holdings) < 2:
                return {"error": "Need at least 2 holdings for correlation analysis"}

            total_value = sum(h["market_value"] or 0 for h in holdings)
            if total_value == 0:
                return {"error": "No portfolio value"}

            all_returns = []
            tickers = []
            weights = []

            for h in holdings:
                history = list(self.price_dao.get_history(h["ticker"], days=252))
                if len(history) < 30:
                    continue

                prices = [row["close"] for row in reversed(history) if row["close"]]
                if len(prices) < 30:
                    continue

                returns = np.diff(prices) / prices[:-1]
                all_returns.append(returns)
                tickers.append(h["ticker"])
                weights.append((h["market_value"] or 0) / total_value)

            if len(all_returns) < 2:
                return {"error": "Insufficient data for correlation (need 2+ tickers with history)"}

            min_len = min(len(r) for r in all_returns)
            aligned = np.array([r[-min_len:] for r in all_returns])
            weights = np.array(weights)
            weights = weights / weights.sum()

            # Correlation matrix
            corr_matrix = np.corrcoef(aligned)

            # Find highly correlated pairs (>0.8)
            high_corr_pairs = []
            for i in range(len(tickers)):
                for j in range(i + 1, len(tickers)):
                    corr = corr_matrix[i, j]
                    if abs(corr) > 0.8:
                        high_corr_pairs.append({
                            "pair": f"{tickers[i]}/{tickers[j]}",
                            "correlation": round(float(corr), 3),
                        })

            # Diversification ratio
            individual_vols = np.std(aligned, axis=1)
            weighted_individual_vol = np.dot(weights, individual_vols)
            cov_matrix = np.cov(aligned)
            portfolio_vol = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))
            diversification_ratio = weighted_individual_vol / portfolio_vol if portfolio_vol > 0 else 1.0

            max_corr = 0.0
            for i in range(len(tickers)):
                for j in range(i + 1, len(tickers)):
                    max_corr = max(max_corr, abs(float(corr_matrix[i, j])))

            result = {
                "tickers": tickers,
                "correlation_matrix": corr_matrix.tolist(),
                "high_corr_pairs": high_corr_pairs,
                "max_correlation": round(max_corr, 3),
                "diversification_ratio": round(float(diversification_ratio), 3),
                "is_well_diversified": diversification_ratio > 1.2,
                "portfolio_volatility": round(float(portfolio_vol * np.sqrt(252) * 100), 2),
            }

            # Store
            try:
                self.db.execute_insert(
                    """INSERT INTO correlation_matrix
                       (tickers_json, matrix_json, diversification_ratio,
                        max_correlation, high_corr_pairs_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        json.dumps(tickers),
                        json.dumps(corr_matrix.tolist()),
                        float(diversification_ratio),
                        max_corr,
                        json.dumps(high_corr_pairs),
                    ),
                )
            except Exception as e:
                logger.debug("Correlation storage failed: %s", e)

            return result
        except Exception as e:
            logger.warning("Correlation matrix failed: %s", e)
            return {"error": str(e)}

    # =========================================================================
    # Stress Testing
    # =========================================================================
    def run_stress_tests(self) -> list[dict]:
        """Simulate portfolio under historical crisis scenarios."""
        scenarios = [
            {"name": "2008 Financial Crisis", "description": "Global financial meltdown", "market_shock": -0.38},
            {"name": "2020 COVID Crash", "description": "Pandemic-driven market collapse", "market_shock": -0.34},
            {"name": "2022 Rate Hike", "description": "Aggressive Fed tightening cycle", "market_shock": -0.25},
            {"name": "Tech Sector Crash", "description": "Technology sector correction", "market_shock": -0.40, "sector_filter": ["Technology", "Information Technology", "Communication Services"]},
            {"name": "Energy Collapse", "description": "Oil price crash scenario", "market_shock": -0.50, "sector_filter": ["Energy"]},
        ]

        holdings = self._get_holdings()
        if not holdings:
            return [{"error": "No portfolio holdings for stress testing"}]

        total_value = sum(h["market_value"] or 0 for h in holdings)
        if total_value == 0:
            return [{"error": "No portfolio value"}]

        results = []
        for scenario in scenarios:
            holdings_impact = []
            total_loss = 0.0

            for h in holdings:
                ticker = h["ticker"]
                mkt_val = h["market_value"] or 0
                sector = h["sector"] or "Unknown"

                # Get beta for more accurate stress test
                beta = self._get_beta(ticker)

                # Sector-specific scenarios only affect matching sectors
                sector_filter = scenario.get("sector_filter")
                if sector_filter:
                    if sector in sector_filter:
                        shock = scenario["market_shock"]
                    else:
                        shock = scenario["market_shock"] * 0.3  # Spillover effect
                else:
                    shock = scenario["market_shock"]

                # Beta-adjusted impact
                position_shock = shock * beta
                position_loss = mkt_val * position_shock

                holdings_impact.append({
                    "ticker": ticker,
                    "sector": sector,
                    "beta": round(beta, 2),
                    "shock_pct": round(position_shock * 100, 1),
                    "loss": round(position_loss, 2),
                })
                total_loss += position_loss

            portfolio_impact_pct = (total_loss / total_value) * 100

            result = {
                "scenario_name": scenario["name"],
                "scenario_description": scenario["description"],
                "market_shock_pct": scenario["market_shock"] * 100,
                "portfolio_impact_pct": round(portfolio_impact_pct, 2),
                "portfolio_loss": round(total_loss, 2),
                "portfolio_value_after": round(total_value + total_loss, 2),
                "holdings_impact": holdings_impact,
            }
            results.append(result)

            # Store
            try:
                self.db.execute_insert(
                    """INSERT INTO stress_test_results
                       (scenario_name, scenario_description, market_shock_pct,
                        portfolio_impact_pct, portfolio_loss, holdings_impact_json)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        scenario["name"], scenario["description"],
                        scenario["market_shock"] * 100,
                        portfolio_impact_pct, total_loss,
                        json.dumps(holdings_impact),
                    ),
                )
            except Exception as e:
                logger.debug("Stress test storage failed: %s", e)

        return results

    def _get_beta(self, ticker: str) -> float:
        """Get beta for a ticker, default 1.0."""
        try:
            row = self.db.execute_one(
                "SELECT beta FROM stock_fundamentals WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1",
                (ticker,),
            )
            if row and row["beta"]:
                return float(row["beta"])
        except Exception:
            pass
        return 1.0

    # =========================================================================
    # Maximum Drawdown Monitoring
    # =========================================================================
    def calculate_max_drawdown(self) -> dict:
        """Track running peak-to-trough decline across portfolio history."""
        try:
            snapshots = self.db.execute(
                """SELECT total_equity, snapshot_date FROM portfolio_snapshots
                   WHERE total_equity IS NOT NULL
                   ORDER BY snapshot_date ASC"""
            )
            snapshots = list(snapshots)

            if len(snapshots) < 2:
                return {"error": "Insufficient portfolio snapshot history"}

            equities = [s["total_equity"] for s in snapshots]
            dates = [s["snapshot_date"] for s in snapshots]

            # Calculate drawdown series
            peak = equities[0]
            max_drawdown = 0
            max_drawdown_start = dates[0]
            max_drawdown_end = dates[0]
            current_drawdown_start = dates[0]

            drawdown_series = []
            for i, equity in enumerate(equities):
                if equity > peak:
                    peak = equity
                    current_drawdown_start = dates[i]

                drawdown = (equity - peak) / peak
                drawdown_series.append(round(drawdown * 100, 2))

                if drawdown < max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_start = current_drawdown_start
                    max_drawdown_end = dates[i]

            current_drawdown = (equities[-1] - max(equities)) / max(equities)

            # Alert thresholds
            alerts = []
            if abs(current_drawdown) > 0.25:
                alerts.append("CRITICAL: Portfolio drawdown exceeds 25% - consider circuit breaker")
            elif abs(current_drawdown) > 0.15:
                alerts.append("WARNING: Portfolio drawdown exceeds 15%")
            elif abs(current_drawdown) > 0.10:
                alerts.append("CAUTION: Portfolio drawdown at 10%+")

            # Circuit breaker: if drawdown > 20%, recommend 50% size reduction
            circuit_breaker_active = abs(current_drawdown) > 0.20

            return {
                "max_drawdown_pct": round(max_drawdown * 100, 2),
                "max_drawdown_start": max_drawdown_start,
                "max_drawdown_end": max_drawdown_end,
                "current_drawdown_pct": round(current_drawdown * 100, 2),
                "peak_equity": round(max(equities), 2),
                "current_equity": round(equities[-1], 2),
                "circuit_breaker_active": circuit_breaker_active,
                "position_size_multiplier": 0.5 if circuit_breaker_active else 1.0,
                "alerts": alerts,
                "drawdown_series": drawdown_series[-50:],  # Last 50 for charting
            }
        except Exception as e:
            logger.warning("Max drawdown calculation failed: %s", e)
            return {"error": str(e)}

    # =========================================================================
    # Full Risk Report
    # =========================================================================
    def generate_risk_report(self) -> dict:
        """Generate comprehensive risk report combining all risk metrics."""
        report = {
            "generated_at": datetime.now().isoformat(),
            "portfolio_summary": self.get_portfolio_risk_summary(),
            "kelly_criterion": self.kelly_criterion(),
            "var": self.calculate_var(confidence_level=0.95, horizon_days=5),
            "monte_carlo": self.monte_carlo_simulation(num_simulations=10000, horizon_days=252),
            "correlation": self.calculate_correlation_matrix(),
            "stress_tests": self.run_stress_tests(),
            "max_drawdown": self.calculate_max_drawdown(),
            "diversification": self.check_diversification(),
        }
        return report

    def print_risk_report(self, report: dict = None):
        """Print formatted risk report to console."""
        from utils.console import header, separator, ok, fail, neutral

        if report is None:
            report = self.generate_risk_report()

        print(header("PROFESSIONAL RISK REPORT"))

        # Portfolio summary
        summary = report.get("portfolio_summary", {})
        if summary.get("status") == "ok":
            print(f"\n  PORTFOLIO OVERVIEW:")
            print(f"    Total Value:     ${summary['total_value']:,.2f}")
            print(f"    Positions:       {summary['num_positions']}")
            print(f"    Sectors:         {summary['num_sectors']}")
            print(f"    Max Position:    {summary['max_position_pct']:.1f}%")
            print(f"    HHI:             {summary['hhi']:.4f}")

        # VaR
        var_data = report.get("var", {})
        if "error" not in var_data:
            print(f"\n{separator()}")
            print(f"  VALUE AT RISK (5-day):")
            print(f"    95% VaR:  ${var_data.get('historical_var_dollar', 0):,.2f} ({var_data.get('historical_var_pct', 0):.2f}%)")
            print(f"    99% VaR:  ${var_data.get('var_99_dollar', 0):,.2f} ({var_data.get('var_99_pct', 0):.2f}%)")
            print(f"    CVaR 95%: ${var_data.get('cvar_dollar', 0):,.2f}")
            print(f"    Annual Vol: {var_data.get('portfolio_volatility_annual', 0):.1f}%")

        # Monte Carlo
        mc = report.get("monte_carlo", {})
        if "error" not in mc:
            print(f"\n{separator()}")
            print(f"  MONTE CARLO SIMULATION (12-month, {mc.get('num_simulations', 0):,} paths):")
            print(f"    Bear Case (10th %ile): ${mc.get('bear_case', 0):,.2f}")
            print(f"    Base Case (50th %ile): ${mc.get('base_case', 0):,.2f}")
            print(f"    Bull Case (90th %ile): ${mc.get('bull_case', 0):,.2f}")
            print(f"    P(positive return):    {mc.get('prob_positive_return', 0):.0%}")
            print(f"    P(>10% gain):          {mc.get('prob_10pct_gain', 0):.0%}")
            print(f"    P(>10% loss):          {mc.get('prob_10pct_loss', 0):.0%}")

        # Kelly
        kelly = report.get("kelly_criterion", {})
        if kelly.get("kelly_pct") is not None:
            print(f"\n{separator()}")
            print(f"  KELLY CRITERION:")
            print(f"    Full Kelly:  {kelly['kelly_pct']:.1f}%")
            print(f"    Half Kelly:  {kelly['half_kelly_pct']:.1f}% (recommended)")
            print(f"    Win Rate:    {kelly['win_rate']:.0%}")
            print(f"    W/L Ratio:   {kelly['win_loss_ratio']:.2f}")

        # Correlation
        corr = report.get("correlation", {})
        if "error" not in corr:
            print(f"\n{separator()}")
            print(f"  DIVERSIFICATION:")
            div_fn = ok if corr.get("is_well_diversified") else fail
            div_ratio = corr.get("diversification_ratio", 0)
            print(f"    Diversification Ratio: {div_fn(f'{div_ratio:.2f}')}")
            print(f"    Max Correlation:       {corr.get('max_correlation', 0):.2f}")
            if corr.get("high_corr_pairs"):
                for pair in corr["high_corr_pairs"][:3]:
                    pair_name = pair["pair"]
                    pair_corr = pair["correlation"]
                    print(f"    {fail(f'High correlation: {pair_name} ({pair_corr:.2f})')}")

        # Stress Tests
        stress = report.get("stress_tests", [])
        if stress and "error" not in stress[0]:
            print(f"\n{separator()}")
            print(f"  STRESS TESTS:")
            for s in stress:
                loss_fn = fail if s["portfolio_impact_pct"] < -20 else neutral
                impact = s["portfolio_impact_pct"]
                scenario = s["scenario_name"]
                loss = s["portfolio_loss"]
                print(f"    {scenario:<25} {loss_fn(f'{impact:+.1f}%')} (${loss:+,.0f})")

        # Drawdown
        dd = report.get("max_drawdown", {})
        if "error" not in dd:
            print(f"\n{separator()}")
            print(f"  DRAWDOWN:")
            print(f"    Max Drawdown:    {dd.get('max_drawdown_pct', 0):.1f}%")
            print(f"    Current:         {dd.get('current_drawdown_pct', 0):.1f}%")
            if dd.get("circuit_breaker_active"):
                print(f"    {fail('CIRCUIT BREAKER ACTIVE - Position sizes reduced 50%')}")
            for alert in dd.get("alerts", []):
                print(f"    {fail(alert)}")

        print(f"\n{'=' * 60}\n")

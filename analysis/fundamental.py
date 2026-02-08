"""Fundamental analysis: valuation, profitability, growth, balance sheet, cash flow.

Phase 7A additions: DCF, Piotroski F-Score, Altman Z-Score, Beneish M-Score,
DuPont Analysis, Owner Earnings.
"""

import logging
import numpy as np
import yfinance as yf

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.models import ComputedScoreDAO, DCFValuationDAO

logger = logging.getLogger("stock_model.analysis.fundamental")


class FundamentalAnalyzer(BaseAnalyzer):
    """Fundamental analysis using yfinance data and SEC EDGAR XBRL when available."""

    name = "fundamental"

    def __init__(self):
        self.score_dao = ComputedScoreDAO()
        self.dcf_dao = DCFValuationDAO()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running fundamental analysis for %s", ticker)
        factors = []
        score = 0.0
        confidence_count = 0
        data_points = 0

        # Get fundamentals from data dict or fetch directly
        stock = yf.Ticker(ticker)
        info = (data or {}).get("info")
        if info is None:
            info = stock.info

        if not info:
            return self._make_result(0, 0.1, [], "No fundamental data available")

        sector = info.get("sector", "Unknown")

        # --- VALUATION ---
        pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        if pe is not None:
            data_points += 1
            if pe < 0:
                impact = -15
                explanation = f"Negative P/E ({pe:.1f}) indicates losses"
            elif pe < 12:
                impact = 20
                explanation = f"Low P/E ratio ({pe:.1f}) suggests undervaluation"
            elif pe < 20:
                impact = 10
                explanation = f"Moderate P/E ratio ({pe:.1f}) - fairly valued"
            elif pe < 35:
                impact = -5
                explanation = f"High P/E ratio ({pe:.1f}) - growth priced in"
            else:
                impact = -15
                explanation = f"Very high P/E ratio ({pe:.1f}) - potentially overvalued"
            score += impact
            factors.append(AnalysisFactor("P/E Ratio", f"{pe:.1f}", impact, explanation))
            confidence_count += 1

        if forward_pe is not None and pe is not None and pe > 0 and forward_pe > 0:
            data_points += 1
            pe_improvement = ((pe - forward_pe) / pe) * 100
            if pe_improvement > 15:
                impact = 8
                explanation = f"Forward P/E ({forward_pe:.1f}) much lower than trailing ({pe:.1f}) - earnings growth expected"
            elif pe_improvement > 0:
                impact = 3
                explanation = f"Forward P/E ({forward_pe:.1f}) lower than trailing ({pe:.1f}) - modest growth"
            else:
                impact = -5
                explanation = f"Forward P/E ({forward_pe:.1f}) higher than trailing ({pe:.1f}) - earnings decline expected"
            score += impact
            factors.append(AnalysisFactor("Forward P/E", f"{forward_pe:.1f}", impact, explanation))

        # P/B Ratio
        pb = info.get("priceToBook")
        if pb is not None:
            data_points += 1
            if pb < 1:
                impact = 12
                explanation = f"P/B below 1 ({pb:.2f}) - trading below book value"
            elif pb < 3:
                impact = 5
                explanation = f"Reasonable P/B ratio ({pb:.2f})"
            elif pb > 10:
                impact = -8
                explanation = f"Very high P/B ratio ({pb:.2f})"
            else:
                impact = 0
                explanation = f"P/B ratio: {pb:.2f}"
            score += impact
            factors.append(AnalysisFactor("P/B Ratio", f"{pb:.2f}", impact, explanation))

        # P/S Ratio
        ps = info.get("priceToSalesTrailing12Months")
        if ps is not None:
            data_points += 1
            if ps < 1:
                impact = 10
                explanation = f"Low P/S ({ps:.2f}) - revenue not reflected in price"
            elif ps < 5:
                impact = 3
                explanation = f"Moderate P/S ratio ({ps:.2f})"
            elif ps > 15:
                impact = -10
                explanation = f"Very high P/S ({ps:.2f}) - priced for extreme growth"
            else:
                impact = -3
                explanation = f"Elevated P/S ratio ({ps:.2f})"
            score += impact
            factors.append(AnalysisFactor("P/S Ratio", f"{ps:.2f}", impact, explanation))

        # PEG Ratio
        peg = info.get("pegRatio")
        if peg is not None and peg > 0:
            data_points += 1
            if peg < 1:
                impact = 12
                explanation = f"PEG below 1 ({peg:.2f}) - growth at reasonable price"
            elif peg < 1.5:
                impact = 5
                explanation = f"Fair PEG ratio ({peg:.2f})"
            elif peg > 2.5:
                impact = -10
                explanation = f"High PEG ({peg:.2f}) - overpaying for growth"
            else:
                impact = -2
                explanation = f"PEG ratio: {peg:.2f}"
            score += impact
            factors.append(AnalysisFactor("PEG Ratio", f"{peg:.2f}", impact, explanation))

        # EV/EBITDA
        ev_ebitda = info.get("enterpriseToEbitda")
        if ev_ebitda is not None and ev_ebitda > 0:
            data_points += 1
            if ev_ebitda < 8:
                impact = 10
                explanation = f"Low EV/EBITDA ({ev_ebitda:.1f}) - potentially undervalued"
            elif ev_ebitda < 15:
                impact = 3
                explanation = f"Fair EV/EBITDA ({ev_ebitda:.1f})"
            elif ev_ebitda > 25:
                impact = -8
                explanation = f"High EV/EBITDA ({ev_ebitda:.1f})"
            else:
                impact = -2
                explanation = f"EV/EBITDA: {ev_ebitda:.1f}"
            score += impact
            factors.append(AnalysisFactor("EV/EBITDA", f"{ev_ebitda:.1f}", impact, explanation))

        # --- PROFITABILITY ---
        margin = info.get("profitMargins")
        if margin is not None:
            data_points += 1
            margin_pct = margin * 100
            if margin > 0.25:
                impact = 15
                explanation = f"Excellent profit margin ({margin_pct:.1f}%)"
            elif margin > 0.10:
                impact = 8
                explanation = f"Good profit margin ({margin_pct:.1f}%)"
            elif margin > 0:
                impact = 2
                explanation = f"Thin profit margin ({margin_pct:.1f}%)"
            else:
                impact = -20
                explanation = f"Negative profit margin ({margin_pct:.1f}%) - company is losing money"
            score += impact
            factors.append(AnalysisFactor("Profit Margin", f"{margin_pct:.1f}%", impact, explanation))
            confidence_count += 1

        op_margin = info.get("operatingMargins")
        if op_margin is not None:
            data_points += 1
            op_pct = op_margin * 100
            if op_margin > 0.25:
                impact = 8
            elif op_margin > 0.10:
                impact = 4
            elif op_margin > 0:
                impact = 0
            else:
                impact = -10
            score += impact
            factors.append(AnalysisFactor(
                "Operating Margin", f"{op_pct:.1f}%", impact,
                f"Operating margin: {op_pct:.1f}%"))

        # ROE
        roe = info.get("returnOnEquity")
        if roe is not None:
            data_points += 1
            roe_pct = roe * 100
            if roe > 0.20:
                impact = 10
                explanation = f"Strong ROE ({roe_pct:.1f}%) - efficient use of equity"
            elif roe > 0.10:
                impact = 5
                explanation = f"Decent ROE ({roe_pct:.1f}%)"
            elif roe > 0:
                impact = 0
                explanation = f"Low ROE ({roe_pct:.1f}%)"
            else:
                impact = -10
                explanation = f"Negative ROE ({roe_pct:.1f}%)"
            score += impact
            factors.append(AnalysisFactor("ROE", f"{roe_pct:.1f}%", impact, explanation))

        # ROA
        roa = info.get("returnOnAssets")
        if roa is not None:
            data_points += 1
            roa_pct = roa * 100
            if roa > 0.10:
                impact = 5
            elif roa > 0.05:
                impact = 2
            elif roa > 0:
                impact = 0
            else:
                impact = -5
            score += impact
            factors.append(AnalysisFactor(
                "ROA", f"{roa_pct:.1f}%", impact,
                f"Return on assets: {roa_pct:.1f}%"))

        # --- GROWTH ---
        rev_growth = info.get("revenueGrowth")
        if rev_growth is not None:
            data_points += 1
            rg_pct = rev_growth * 100
            if rev_growth > 0.25:
                impact = 15
                explanation = f"Strong revenue growth ({rg_pct:.1f}%)"
            elif rev_growth > 0.10:
                impact = 8
                explanation = f"Good revenue growth ({rg_pct:.1f}%)"
            elif rev_growth > 0:
                impact = 2
                explanation = f"Modest revenue growth ({rg_pct:.1f}%)"
            else:
                impact = -12
                explanation = f"Revenue declining ({rg_pct:.1f}%)"
            score += impact
            factors.append(AnalysisFactor("Revenue Growth", f"{rg_pct:.1f}%", impact, explanation))
            confidence_count += 1

        earn_growth = info.get("earningsGrowth")
        if earn_growth is not None:
            data_points += 1
            eg_pct = earn_growth * 100
            if earn_growth > 0.25:
                impact = 12
            elif earn_growth > 0.10:
                impact = 6
            elif earn_growth > 0:
                impact = 2
            else:
                impact = -10
            score += impact
            factors.append(AnalysisFactor(
                "Earnings Growth", f"{eg_pct:.1f}%", impact,
                f"Earnings growth: {eg_pct:.1f}%"))

        # --- BALANCE SHEET ---
        de = info.get("debtToEquity")
        if de is not None:
            data_points += 1
            if de < 30:
                impact = 10
                explanation = f"Low debt-to-equity ({de:.0f}) - conservative balance sheet"
            elif de < 80:
                impact = 3
                explanation = f"Moderate debt-to-equity ({de:.0f})"
            elif de < 150:
                impact = -5
                explanation = f"Elevated debt-to-equity ({de:.0f})"
            else:
                impact = -12
                explanation = f"High debt-to-equity ({de:.0f}) - leverage risk"
            score += impact
            factors.append(AnalysisFactor("Debt/Equity", f"{de:.0f}", impact, explanation))
            confidence_count += 1

        current_ratio = info.get("currentRatio")
        if current_ratio is not None:
            data_points += 1
            if current_ratio > 2:
                impact = 5
                explanation = f"Strong current ratio ({current_ratio:.2f}) - ample liquidity"
            elif current_ratio > 1:
                impact = 2
                explanation = f"Adequate current ratio ({current_ratio:.2f})"
            else:
                impact = -10
                explanation = f"Low current ratio ({current_ratio:.2f}) - liquidity concern"
            score += impact
            factors.append(AnalysisFactor("Current Ratio", f"{current_ratio:.2f}", impact, explanation))

        # --- CASH FLOW ---
        fcf = info.get("freeCashflow")
        market_cap = info.get("marketCap")
        if fcf is not None and market_cap is not None and market_cap > 0:
            data_points += 1
            fcf_yield = (fcf / market_cap) * 100
            if fcf_yield > 8:
                impact = 10
                explanation = f"High FCF yield ({fcf_yield:.1f}%) - strong cash generation"
            elif fcf_yield > 4:
                impact = 5
                explanation = f"Good FCF yield ({fcf_yield:.1f}%)"
            elif fcf_yield > 0:
                impact = 0
                explanation = f"Positive FCF yield ({fcf_yield:.1f}%)"
            else:
                impact = -8
                explanation = f"Negative FCF yield ({fcf_yield:.1f}%) - burning cash"
            score += impact
            factors.append(AnalysisFactor("FCF Yield", f"{fcf_yield:.1f}%", impact, explanation))

        div_yield = info.get("dividendYield")
        if div_yield is not None and div_yield > 0:
            data_points += 1
            dy_pct = div_yield * 100
            if dy_pct > 5:
                impact = 3
                explanation = f"High dividend yield ({dy_pct:.2f}%) - check sustainability"
            elif dy_pct > 2:
                impact = 5
                explanation = f"Attractive dividend yield ({dy_pct:.2f}%)"
            else:
                impact = 2
                explanation = f"Modest dividend yield ({dy_pct:.2f}%)"
            score += impact
            factors.append(AnalysisFactor("Dividend Yield", f"{dy_pct:.2f}%", impact, explanation))

        # =====================================================================
        # PHASE 7A: PROFESSIONAL SCORING MODELS
        # =====================================================================

        # --- DCF Intrinsic Value ---
        dcf_result = self._calculate_dcf(ticker, stock, info)
        if dcf_result:
            data_points += 1
            score += dcf_result["impact"]
            factors.append(AnalysisFactor(
                "DCF Intrinsic Value",
                f"${dcf_result['intrinsic_value']:.2f}",
                dcf_result["impact"],
                dcf_result["explanation"],
            ))
            confidence_count += 1

        # --- Piotroski F-Score ---
        piotroski = self._calculate_piotroski(stock, info)
        if piotroski:
            data_points += 1
            score += piotroski["impact"]
            factors.append(AnalysisFactor(
                "Piotroski F-Score",
                f"{piotroski['score']}/9",
                piotroski["impact"],
                piotroski["explanation"],
            ))
            confidence_count += 1

        # --- Altman Z-Score ---
        altman = self._calculate_altman_z(stock, info)
        if altman:
            data_points += 1
            score += altman["impact"]
            factors.append(AnalysisFactor(
                "Altman Z-Score",
                f"{altman['z_score']:.2f}",
                altman["impact"],
                altman["explanation"],
            ))

        # --- Beneish M-Score ---
        beneish = self._calculate_beneish(stock)
        if beneish:
            data_points += 1
            score += beneish["impact"]
            factors.append(AnalysisFactor(
                "Beneish M-Score",
                f"{beneish['m_score']:.2f}",
                beneish["impact"],
                beneish["explanation"],
            ))

        # --- DuPont Analysis ---
        dupont = self._calculate_dupont(info)
        if dupont:
            data_points += 1
            score += dupont["impact"]
            factors.append(AnalysisFactor(
                "DuPont Analysis",
                dupont["driver"],
                dupont["impact"],
                dupont["explanation"],
            ))

        # --- Owner Earnings ---
        owner_earnings = self._calculate_owner_earnings(stock, info)
        if owner_earnings:
            data_points += 1
            score += owner_earnings["impact"]
            factors.append(AnalysisFactor(
                "Owner Earnings",
                f"${owner_earnings['value']:,.0f}",
                owner_earnings["impact"],
                owner_earnings["explanation"],
            ))

        # Confidence based on data availability (updated max for new models)
        max_expected = 22  # 16 original + 6 new models
        confidence = min(1.0, (data_points / max_expected) * 0.8 + 0.2)
        if confidence_count >= 4:
            confidence = min(1.0, confidence + 0.1)

        # Normalize score to -100/+100 range
        if data_points > 0:
            max_possible = data_points * 15
            score = (score / max(max_possible, 1)) * 100
            score = max(-100, min(100, score))

        summary = self._build_summary(score, factors, sector)
        return self._make_result(score, confidence, factors, summary)

    # =========================================================================
    # DCF Intrinsic Value
    # =========================================================================
    def _calculate_dcf(self, ticker: str, stock, info: dict) -> dict | None:
        """Warren Buffett's DCF intrinsic value calculation."""
        try:
            fcf = info.get("freeCashflow")
            shares = info.get("sharesOutstanding")
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            rev_growth = info.get("revenueGrowth")

            if not all([fcf, shares, current_price]) or fcf <= 0 or shares <= 0:
                return None

            # Growth rate: use revenue growth or default 5%
            growth_rate = min(rev_growth or 0.05, 0.25)  # Cap at 25%
            if growth_rate < 0:
                growth_rate = 0.02  # Floor at 2% for declining companies

            discount_rate = 0.10  # 10% WACC default
            terminal_growth = 0.03  # 3% perpetual growth
            projection_years = 10

            # Project FCF for each year and discount
            intrinsic_value = 0.0
            for t in range(1, projection_years + 1):
                projected_fcf = fcf * (1 + growth_rate) ** t
                discounted = projected_fcf / (1 + discount_rate) ** t
                intrinsic_value += discounted

            # Terminal value (Gordon Growth Model)
            terminal_fcf = fcf * (1 + growth_rate) ** projection_years * (1 + terminal_growth)
            terminal_value = terminal_fcf / (discount_rate - terminal_growth)
            discounted_terminal = terminal_value / (1 + discount_rate) ** projection_years
            intrinsic_value += discounted_terminal

            # Per share
            intrinsic_per_share = intrinsic_value / shares
            margin_of_safety = ((intrinsic_per_share - current_price) / current_price) * 100

            # Score impact: +-25 points
            if margin_of_safety > 30:
                impact = 25
                explanation = f"DCF fair value ${intrinsic_per_share:.2f} vs ${current_price:.2f} - {margin_of_safety:.0f}% margin of safety (STRONG BUY zone)"
            elif margin_of_safety > 10:
                impact = 15
                explanation = f"DCF fair value ${intrinsic_per_share:.2f} vs ${current_price:.2f} - {margin_of_safety:.0f}% undervalued"
            elif margin_of_safety > -10:
                impact = 0
                explanation = f"DCF fair value ${intrinsic_per_share:.2f} vs ${current_price:.2f} - fairly valued"
            elif margin_of_safety > -30:
                impact = -10
                explanation = f"DCF fair value ${intrinsic_per_share:.2f} vs ${current_price:.2f} - {abs(margin_of_safety):.0f}% overvalued"
            else:
                impact = -25
                explanation = f"DCF fair value ${intrinsic_per_share:.2f} vs ${current_price:.2f} - {abs(margin_of_safety):.0f}% overvalued (DANGER)"

            # Store in database
            try:
                self.dcf_dao.insert(ticker, {
                    "intrinsic_value": intrinsic_per_share,
                    "current_price": current_price,
                    "margin_of_safety": margin_of_safety,
                    "free_cash_flow": fcf,
                    "growth_rate": growth_rate,
                    "discount_rate": discount_rate,
                    "terminal_growth_rate": terminal_growth,
                    "shares_outstanding": shares,
                    "projection_years": projection_years,
                })
            except Exception as e:
                logger.debug("DCF storage failed: %s", e)

            # Store computed score
            try:
                self.score_dao.insert(ticker, "dcf", intrinsic_per_share, {
                    "margin_of_safety": margin_of_safety,
                    "growth_rate": growth_rate,
                    "discount_rate": discount_rate,
                })
            except Exception as e:
                logger.debug("Score storage failed: %s", e)

            return {
                "intrinsic_value": intrinsic_per_share,
                "margin_of_safety": margin_of_safety,
                "impact": impact,
                "explanation": explanation,
            }
        except Exception as e:
            logger.warning("DCF calculation failed for %s: %s", ticker, e)
            return None

    # =========================================================================
    # Piotroski F-Score (0-9)
    # =========================================================================
    def _calculate_piotroski(self, stock, info: dict) -> dict | None:
        """Calculate Piotroski F-Score: 9 binary financial health tests."""
        try:
            fscore = 0
            tests_passed = []

            # Need financial statements
            try:
                income_stmt = stock.income_stmt
                balance_sheet = stock.balance_sheet
                cashflow = stock.cashflow
            except Exception:
                return None

            if income_stmt is None or income_stmt.empty:
                return None
            if balance_sheet is None or balance_sheet.empty:
                return None
            if cashflow is None or cashflow.empty:
                return None

            # Use most recent and prior year columns
            cols = income_stmt.columns
            if len(cols) < 2:
                return None

            # Helper to safely get a value from financial statement
            def _get(df, label, col_idx=0):
                for name in (label,):
                    if name in df.index:
                        val = df.iloc[df.index.get_loc(name), col_idx]
                        if val is not None and not (isinstance(val, float) and np.isnan(val)):
                            return float(val)
                return None

            # 1. Net Income > 0
            net_income = _get(income_stmt, "Net Income")
            if net_income is not None and net_income > 0:
                fscore += 1
                tests_passed.append("Positive Net Income")

            # 2. Operating Cash Flow > 0
            ocf = _get(cashflow, "Operating Cash Flow")
            if ocf is not None and ocf > 0:
                fscore += 1
                tests_passed.append("Positive Operating Cash Flow")

            # 3. ROA increasing (compare current vs prior year)
            total_assets_curr = _get(balance_sheet, "Total Assets", 0)
            total_assets_prev = _get(balance_sheet, "Total Assets", 1)
            net_income_prev = _get(income_stmt, "Net Income", 1)
            if all(v is not None and v != 0 for v in [net_income, total_assets_curr, net_income_prev, total_assets_prev]):
                roa_curr = net_income / total_assets_curr
                roa_prev = net_income_prev / total_assets_prev
                if roa_curr > roa_prev:
                    fscore += 1
                    tests_passed.append("ROA Increasing")

            # 4. Cash flow from operations > Net Income (earnings quality)
            if ocf is not None and net_income is not None and ocf > net_income:
                fscore += 1
                tests_passed.append("Cash Flow > Net Income (Quality)")

            # 5. Long-term debt ratio decreasing
            lt_debt_curr = _get(balance_sheet, "Long Term Debt", 0)
            lt_debt_prev = _get(balance_sheet, "Long Term Debt", 1)
            if lt_debt_curr is not None and lt_debt_prev is not None and total_assets_curr and total_assets_prev:
                debt_ratio_curr = lt_debt_curr / total_assets_curr
                debt_ratio_prev = lt_debt_prev / total_assets_prev
                if debt_ratio_curr <= debt_ratio_prev:
                    fscore += 1
                    tests_passed.append("Debt Ratio Decreasing")
            elif lt_debt_curr is None or lt_debt_curr == 0:
                fscore += 1
                tests_passed.append("No Long-Term Debt")

            # 6. Current ratio increasing
            curr_assets_curr = _get(balance_sheet, "Current Assets", 0)
            curr_liab_curr = _get(balance_sheet, "Current Liabilities", 0)
            curr_assets_prev = _get(balance_sheet, "Current Assets", 1)
            curr_liab_prev = _get(balance_sheet, "Current Liabilities", 1)
            if all(v is not None and v != 0 for v in [curr_assets_curr, curr_liab_curr, curr_assets_prev, curr_liab_prev]):
                cr_curr = curr_assets_curr / curr_liab_curr
                cr_prev = curr_assets_prev / curr_liab_prev
                if cr_curr > cr_prev:
                    fscore += 1
                    tests_passed.append("Current Ratio Increasing")

            # 7. No new shares issued
            shares_curr = _get(balance_sheet, "Ordinary Shares Number", 0) or _get(balance_sheet, "Share Issued", 0)
            shares_prev = _get(balance_sheet, "Ordinary Shares Number", 1) or _get(balance_sheet, "Share Issued", 1)
            if shares_curr is not None and shares_prev is not None:
                if shares_curr <= shares_prev:
                    fscore += 1
                    tests_passed.append("No Dilution")

            # 8. Gross margin increasing
            gross_curr = _get(income_stmt, "Gross Profit", 0)
            rev_curr = _get(income_stmt, "Total Revenue", 0)
            gross_prev = _get(income_stmt, "Gross Profit", 1)
            rev_prev = _get(income_stmt, "Total Revenue", 1)
            if all(v is not None and v != 0 for v in [gross_curr, rev_curr, gross_prev, rev_prev]):
                gm_curr = gross_curr / rev_curr
                gm_prev = gross_prev / rev_prev
                if gm_curr > gm_prev:
                    fscore += 1
                    tests_passed.append("Gross Margin Increasing")

            # 9. Asset turnover increasing
            if all(v is not None and v != 0 for v in [rev_curr, total_assets_curr, rev_prev, total_assets_prev]):
                at_curr = rev_curr / total_assets_curr
                at_prev = rev_prev / total_assets_prev
                if at_curr > at_prev:
                    fscore += 1
                    tests_passed.append("Asset Turnover Increasing")

            # Score impact: +-20 points
            if fscore >= 8:
                impact = 20
                zone = "STRONG (value buy signal)"
            elif fscore >= 6:
                impact = 10
                zone = "GOOD (financially healthy)"
            elif fscore >= 4:
                impact = 0
                zone = "AVERAGE"
            elif fscore >= 2:
                impact = -10
                zone = "WEAK (financial concerns)"
            else:
                impact = -20
                zone = "DISTRESSED (avoid)"

            passed_str = ", ".join(tests_passed[:4]) if tests_passed else "None"
            explanation = f"Piotroski F-Score: {fscore}/9 - {zone}. Passed: {passed_str}"

            try:
                self.score_dao.insert(ticker=stock.ticker, score_type="piotroski",
                                      score_value=fscore, details={"tests_passed": tests_passed})
            except Exception as e:
                logger.debug("Piotroski storage failed: %s", e)

            return {"score": fscore, "impact": impact, "explanation": explanation}
        except Exception as e:
            logger.warning("Piotroski calculation failed: %s", e)
            return None

    # =========================================================================
    # Altman Z-Score (Bankruptcy Prediction)
    # =========================================================================
    def _calculate_altman_z(self, stock, info: dict) -> dict | None:
        """Calculate Altman Z-Score for bankruptcy prediction."""
        try:
            try:
                balance_sheet = stock.balance_sheet
                income_stmt = stock.income_stmt
            except Exception:
                return None

            if balance_sheet is None or balance_sheet.empty:
                return None
            if income_stmt is None or income_stmt.empty:
                return None

            def _get(df, label, col_idx=0):
                if label in df.index:
                    val = df.iloc[df.index.get_loc(label), col_idx]
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return float(val)
                return None

            total_assets = _get(balance_sheet, "Total Assets")
            if not total_assets or total_assets == 0:
                return None

            # Components
            current_assets = _get(balance_sheet, "Current Assets") or 0
            current_liab = _get(balance_sheet, "Current Liabilities") or 0
            working_capital = current_assets - current_liab

            retained_earnings = _get(balance_sheet, "Retained Earnings") or 0

            ebit = _get(income_stmt, "EBIT") or _get(income_stmt, "Operating Income") or 0

            market_cap = info.get("marketCap") or 0
            total_liab = _get(balance_sheet, "Total Liabilities Net Minority Interest") or _get(balance_sheet, "Total Liabilities") or 0

            revenue = _get(income_stmt, "Total Revenue") or 0

            if total_liab == 0:
                total_liab = total_assets - (_get(balance_sheet, "Stockholders Equity") or 0)

            # Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
            a = working_capital / total_assets
            b = retained_earnings / total_assets
            c = ebit / total_assets
            d = market_cap / total_liab if total_liab > 0 else 0
            e = revenue / total_assets

            z_score = 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e

            # Interpret
            if z_score > 2.99:
                impact = 10
                zone = "SAFE zone"
                explanation = f"Altman Z-Score {z_score:.2f} - {zone} (low bankruptcy risk)"
            elif z_score > 1.81:
                impact = -5
                zone = "GREY zone"
                explanation = f"Altman Z-Score {z_score:.2f} - {zone} (moderate risk, monitor closely)"
            else:
                impact = -15
                zone = "DISTRESS zone"
                explanation = f"Altman Z-Score {z_score:.2f} - {zone} (HIGH bankruptcy risk)"

            try:
                self.score_dao.insert(ticker=stock.ticker, score_type="altman_z",
                                      score_value=z_score, details={
                    "A_working_capital": round(a, 4),
                    "B_retained_earnings": round(b, 4),
                    "C_ebit": round(c, 4),
                    "D_market_cap_to_liab": round(d, 4),
                    "E_revenue": round(e, 4),
                })
            except Exception as e_db:
                logger.debug("Altman Z storage failed: %s", e_db)

            return {"z_score": z_score, "impact": impact, "explanation": explanation}
        except Exception as e:
            logger.warning("Altman Z-Score calculation failed: %s", e)
            return None

    # =========================================================================
    # Beneish M-Score (Earnings Manipulation Detection)
    # =========================================================================
    def _calculate_beneish(self, stock) -> dict | None:
        """Calculate Beneish M-Score to detect earnings manipulation."""
        try:
            try:
                income_stmt = stock.income_stmt
                balance_sheet = stock.balance_sheet
                cashflow = stock.cashflow
            except Exception:
                return None

            if any(df is None or df.empty for df in [income_stmt, balance_sheet]):
                return None
            if len(income_stmt.columns) < 2 or len(balance_sheet.columns) < 2:
                return None

            def _get(df, label, col_idx=0):
                if label in df.index:
                    val = df.iloc[df.index.get_loc(label), col_idx]
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return float(val)
                return None

            # Current period (0) and prior period (1)
            rev_curr = _get(income_stmt, "Total Revenue", 0)
            rev_prev = _get(income_stmt, "Total Revenue", 1)
            cogs_curr = _get(income_stmt, "Cost Of Revenue", 0)
            cogs_prev = _get(income_stmt, "Cost Of Revenue", 1)
            receivables_curr = _get(balance_sheet, "Accounts Receivable", 0) or _get(balance_sheet, "Net Receivables", 0) or 0
            receivables_prev = _get(balance_sheet, "Accounts Receivable", 1) or _get(balance_sheet, "Net Receivables", 1) or 0
            total_assets_curr = _get(balance_sheet, "Total Assets", 0)
            total_assets_prev = _get(balance_sheet, "Total Assets", 1)
            ppe_curr = _get(balance_sheet, "Net PPE", 0) or _get(balance_sheet, "Property Plant Equipment Net", 0) or 0
            ppe_prev = _get(balance_sheet, "Net PPE", 1) or _get(balance_sheet, "Property Plant Equipment Net", 1) or 0
            depreciation_curr = _get(income_stmt, "Depreciation And Amortization In Income Statement", 0) or _get(income_stmt, "Depreciation", 0) or 0
            depreciation_prev = _get(income_stmt, "Depreciation And Amortization In Income Statement", 1) or _get(income_stmt, "Depreciation", 1) or 0
            sga_curr = _get(income_stmt, "Selling General And Administration", 0) or 0
            sga_prev = _get(income_stmt, "Selling General And Administration", 1) or 0
            net_income_curr = _get(income_stmt, "Net Income", 0)
            ocf_curr = _get(cashflow, "Operating Cash Flow", 0) if cashflow is not None and not cashflow.empty else None

            # Need minimum data
            if not all([rev_curr, rev_prev, total_assets_curr, total_assets_prev]):
                return None
            if rev_prev == 0 or total_assets_prev == 0 or total_assets_curr == 0:
                return None

            # 1. DSRI - Days Sales in Receivables Index
            dsr_curr = receivables_curr / rev_curr if rev_curr else 0
            dsr_prev = receivables_prev / rev_prev if rev_prev else 0
            dsri = dsr_curr / dsr_prev if dsr_prev > 0 else 1.0

            # 2. GMI - Gross Margin Index
            gm_curr = (rev_curr - (cogs_curr or 0)) / rev_curr if rev_curr else 0
            gm_prev = (rev_prev - (cogs_prev or 0)) / rev_prev if rev_prev else 0
            gmi = gm_prev / gm_curr if gm_curr > 0 else 1.0

            # 3. AQI - Asset Quality Index
            ca_curr = _get(balance_sheet, "Current Assets", 0) or 0
            ca_prev = _get(balance_sheet, "Current Assets", 1) or 0
            aq_curr = 1 - (ca_curr + ppe_curr) / total_assets_curr if total_assets_curr else 0
            aq_prev = 1 - (ca_prev + ppe_prev) / total_assets_prev if total_assets_prev else 0
            aqi = aq_curr / aq_prev if aq_prev > 0 else 1.0

            # 4. SGI - Sales Growth Index
            sgi = rev_curr / rev_prev

            # 5. DEPI - Depreciation Index
            depi_curr = depreciation_curr / (depreciation_curr + ppe_curr) if (depreciation_curr + ppe_curr) > 0 else 0
            depi_prev = depreciation_prev / (depreciation_prev + ppe_prev) if (depreciation_prev + ppe_prev) > 0 else 0
            depi = depi_prev / depi_curr if depi_curr > 0 else 1.0

            # 6. SGAI - SGA Expense Index
            sgai_curr = sga_curr / rev_curr if rev_curr else 0
            sgai_prev = sga_prev / rev_prev if rev_prev else 0
            sgai = sgai_curr / sgai_prev if sgai_prev > 0 else 1.0

            # 7. LVGI - Leverage Index (total debt / total assets)
            total_liab_curr = _get(balance_sheet, "Total Liabilities Net Minority Interest", 0) or _get(balance_sheet, "Total Liabilities", 0) or 0
            total_liab_prev = _get(balance_sheet, "Total Liabilities Net Minority Interest", 1) or _get(balance_sheet, "Total Liabilities", 1) or 0
            lev_curr = total_liab_curr / total_assets_curr if total_assets_curr else 0
            lev_prev = total_liab_prev / total_assets_prev if total_assets_prev else 0
            lvgi = lev_curr / lev_prev if lev_prev > 0 else 1.0

            # 8. TATA - Total Accruals to Total Assets
            if net_income_curr is not None and ocf_curr is not None and total_assets_curr:
                tata = (net_income_curr - ocf_curr) / total_assets_curr
            else:
                tata = 0

            # Beneish M-Score = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
            #                   + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI
            m_score = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi
                       + 0.892 * sgi + 0.115 * depi - 0.172 * sgai
                       + 4.679 * tata - 0.327 * lvgi)

            # M-Score > -1.78 = likely manipulator
            if m_score > -1.78:
                impact = -25
                explanation = f"Beneish M-Score {m_score:.2f} > -1.78 - LIKELY EARNINGS MANIPULATION (critical risk)"
            elif m_score > -2.22:
                impact = -10
                explanation = f"Beneish M-Score {m_score:.2f} - borderline, monitor closely"
            else:
                impact = 5
                explanation = f"Beneish M-Score {m_score:.2f} - earnings appear genuine"

            try:
                self.score_dao.insert(ticker=stock.ticker, score_type="beneish_m",
                                      score_value=m_score, details={
                    "DSRI": round(dsri, 3), "GMI": round(gmi, 3),
                    "AQI": round(aqi, 3), "SGI": round(sgi, 3),
                    "DEPI": round(depi, 3), "SGAI": round(sgai, 3),
                    "LVGI": round(lvgi, 3), "TATA": round(tata, 4),
                })
            except Exception as e:
                logger.debug("Beneish storage failed: %s", e)

            return {"m_score": m_score, "impact": impact, "explanation": explanation}
        except Exception as e:
            logger.warning("Beneish M-Score calculation failed: %s", e)
            return None

    # =========================================================================
    # DuPont Analysis (ROE Decomposition)
    # =========================================================================
    def _calculate_dupont(self, info: dict) -> dict | None:
        """Decompose ROE into profit margin * asset turnover * equity multiplier."""
        try:
            profit_margin = info.get("profitMargins")
            roe = info.get("returnOnEquity")

            # We need at least profit margin and some way to derive the components
            if profit_margin is None or roe is None:
                return None

            # Get components from yfinance info
            roa = info.get("returnOnAssets")
            if roa is not None and roa != 0:
                equity_multiplier = roe / roa
            else:
                de = info.get("debtToEquity")
                equity_multiplier = 1 + (de / 100 if de else 0)

            # Asset turnover = ROA / Profit Margin
            if profit_margin != 0:
                asset_turnover = roa / profit_margin if roa else 0
            else:
                asset_turnover = 0

            # Determine primary ROE driver
            drivers = []
            if abs(profit_margin) > 0.15:
                drivers.append("high margins")
            if asset_turnover > 1.0:
                drivers.append("efficient assets")
            if equity_multiplier > 3.0:
                drivers.append("HIGH LEVERAGE")

            # Score: penalize leverage-driven ROE, reward margin-driven
            if roe > 0.15 and profit_margin > 0.10 and equity_multiplier < 3:
                impact = 10
                driver = "margin-driven"
                explanation = f"DuPont: ROE driven by strong margins ({profit_margin:.0%}) - sustainable"
            elif roe > 0.15 and equity_multiplier > 4:
                impact = -10
                driver = "leverage-driven"
                explanation = f"DuPont: High ROE but driven by leverage (equity multiplier {equity_multiplier:.1f}x) - risky"
            elif roe > 0.10:
                impact = 5
                driver = "balanced"
                explanation = f"DuPont: Balanced ROE composition - margin {profit_margin:.0%}, turnover {asset_turnover:.2f}x, leverage {equity_multiplier:.1f}x"
            else:
                impact = 0
                driver = "weak"
                explanation = f"DuPont: Weak ROE decomposition - margin {profit_margin:.0%}, leverage {equity_multiplier:.1f}x"

            return {"driver": driver, "impact": impact, "explanation": explanation}
        except Exception as e:
            logger.warning("DuPont analysis failed: %s", e)
            return None

    # =========================================================================
    # Owner Earnings (Buffett's preferred metric)
    # =========================================================================
    def _calculate_owner_earnings(self, stock, info: dict) -> dict | None:
        """Calculate Owner Earnings = Net Income + D&A - CapEx - WC changes."""
        try:
            try:
                cashflow = stock.cashflow
                income_stmt = stock.income_stmt
            except Exception:
                return None

            if cashflow is None or cashflow.empty:
                return None
            if income_stmt is None or income_stmt.empty:
                return None

            def _get(df, label, col_idx=0):
                if label in df.index:
                    val = df.iloc[df.index.get_loc(label), col_idx]
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return float(val)
                return None

            net_income = _get(income_stmt, "Net Income")
            depreciation = _get(cashflow, "Depreciation And Amortization") or _get(income_stmt, "Depreciation And Amortization In Income Statement") or 0
            capex = _get(cashflow, "Capital Expenditure") or 0
            wc_change = _get(cashflow, "Change In Working Capital") or 0

            if net_income is None:
                return None

            # Owner Earnings = Net Income + D&A - CapEx - Working Capital changes
            # Note: capex from cashflow is typically negative, wc_change can be positive or negative
            owner_earnings = net_income + depreciation + capex - wc_change

            # Compare to reported net income
            reported_fcf = info.get("freeCashflow", 0) or 0
            market_cap = info.get("marketCap", 0)

            if market_cap and market_cap > 0:
                oe_yield = (owner_earnings / market_cap) * 100
                if oe_yield > 8:
                    impact = 8
                    explanation = f"Owner Earnings yield {oe_yield:.1f}% - excellent cash generation for owners"
                elif oe_yield > 4:
                    impact = 4
                    explanation = f"Owner Earnings yield {oe_yield:.1f}% - good cash generation"
                elif oe_yield > 0:
                    impact = 0
                    explanation = f"Owner Earnings yield {oe_yield:.1f}% - positive but modest"
                else:
                    impact = -8
                    explanation = f"Owner Earnings yield {oe_yield:.1f}% - negative, not generating cash for owners"
            else:
                if owner_earnings > 0:
                    impact = 3
                    explanation = f"Owner Earnings positive (${owner_earnings:,.0f})"
                else:
                    impact = -5
                    explanation = f"Owner Earnings negative (${owner_earnings:,.0f})"

            return {"value": owner_earnings, "impact": impact, "explanation": explanation}
        except Exception as e:
            logger.warning("Owner Earnings calculation failed: %s", e)
            return None

    # =========================================================================
    # Summary Builder
    # =========================================================================
    def _build_summary(self, score: float, factors: list[AnalysisFactor], sector: str) -> str:
        if score > 20:
            outlook = "positive"
        elif score < -20:
            outlook = "negative"
        else:
            outlook = "neutral"

        bullish = [f for f in factors if f.impact > 5]
        bearish = [f for f in factors if f.impact < -5]

        parts = [f"Fundamental outlook is {outlook} for this {sector} company."]
        if bullish:
            strengths = ", ".join(f.name for f in bullish[:3])
            parts.append(f"Strengths: {strengths}.")
        if bearish:
            weaknesses = ", ".join(f.name for f in bearish[:3])
            parts.append(f"Concerns: {weaknesses}.")

        return " ".join(parts)

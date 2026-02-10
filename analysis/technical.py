"""Technical analysis: trend, momentum, volume, volatility indicators."""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from ta.trend import SMAIndicator, EMAIndicator, MACD, ADXIndicator, IchimokuIndicator
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator, MFIIndicator

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor

logger = logging.getLogger("stock_model.analysis.technical")


class TechnicalAnalyzer(BaseAnalyzer):
    """Enhanced technical analysis with multiple indicator groups."""

    name = "technical"

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running technical analysis for %s", ticker)
        factors = []
        score = 0.0
        confidence_factors = []

        # Get price data
        hist = data.get("price_history") if data else None
        if hist is None or hist.empty:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")

        if hist.empty or len(hist) < 50:
            return self._make_result(0, 0.1, [], "Insufficient price data for technical analysis")

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]
        current_price = close.iloc[-1]

        # --- TREND INDICATORS ---
        # SMA Cross
        sma_20 = SMAIndicator(close, window=20).sma_indicator()
        sma_50 = SMAIndicator(close, window=50).sma_indicator()
        sma_200 = SMAIndicator(close, window=200).sma_indicator() if len(close) >= 200 else None

        # Golden/Death Cross
        if sma_200 is not None and not sma_50.empty and not sma_200.empty:
            if sma_50.iloc[-1] > sma_200.iloc[-1]:
                impact = 15
                score += impact
                factors.append(AnalysisFactor(
                    "SMA Cross", "Golden Cross",
                    impact, "50-day SMA above 200-day SMA (bullish trend)"))
            else:
                impact = -15
                score += impact
                factors.append(AnalysisFactor(
                    "SMA Cross", "Death Cross",
                    impact, "50-day SMA below 200-day SMA (bearish trend)"))
            confidence_factors.append(0.9)

        # Price vs SMAs
        if not sma_50.empty:
            above_50 = current_price > sma_50.iloc[-1]
            impact = 10 if above_50 else -10
            score += impact
            factors.append(AnalysisFactor(
                "Price vs SMA50",
                f"{'Above' if above_50 else 'Below'} ({current_price:.2f} vs {sma_50.iloc[-1]:.2f})",
                impact, f"Price {'above' if above_50 else 'below'} 50-day moving average"))

        # EMA (12, 26) trend
        ema_12 = EMAIndicator(close, window=12).ema_indicator()
        ema_26 = EMAIndicator(close, window=26).ema_indicator()
        if not ema_12.empty and not ema_26.empty:
            ema_bullish = ema_12.iloc[-1] > ema_26.iloc[-1]
            impact = 5 if ema_bullish else -5
            score += impact
            factors.append(AnalysisFactor(
                "EMA Trend", "Bullish" if ema_bullish else "Bearish",
                impact, f"EMA(12) {'above' if ema_bullish else 'below'} EMA(26)"))

        # MACD
        macd_ind = MACD(close)
        macd_line = macd_ind.macd()
        macd_signal = macd_ind.macd_signal()
        macd_hist = macd_ind.macd_diff()
        if not macd_line.empty and not macd_signal.empty:
            macd_bullish = macd_line.iloc[-1] > macd_signal.iloc[-1]
            macd_hist_positive = macd_hist.iloc[-1] > 0 if not macd_hist.empty else False
            impact = 10 if macd_bullish else -10
            if macd_hist_positive == macd_bullish:
                impact = int(impact * 1.2)
            score += impact
            factors.append(AnalysisFactor(
                "MACD", f"{'Bullish' if macd_bullish else 'Bearish'} (hist: {macd_hist.iloc[-1]:.3f})",
                impact, f"MACD {'above' if macd_bullish else 'below'} signal line"))
            confidence_factors.append(0.8)

        # --- MOMENTUM INDICATORS ---
        # RSI
        rsi = RSIIndicator(close, window=14).rsi()
        if not rsi.empty:
            current_rsi = rsi.iloc[-1]
            if current_rsi < 30:
                impact = 15
                explanation = f"RSI oversold at {current_rsi:.1f} (potential bounce)"
            elif current_rsi > 70:
                impact = -15
                explanation = f"RSI overbought at {current_rsi:.1f} (potential pullback)"
            elif current_rsi < 45:
                impact = 5
                explanation = f"RSI slightly bearish at {current_rsi:.1f}"
            elif current_rsi > 55:
                impact = 5
                explanation = f"RSI slightly bullish at {current_rsi:.1f}"
            else:
                impact = 0
                explanation = f"RSI neutral at {current_rsi:.1f}"
            score += impact
            factors.append(AnalysisFactor("RSI(14)", f"{current_rsi:.1f}", impact, explanation))
            confidence_factors.append(0.85)

        # Stochastic
        if len(close) >= 14:
            stoch = StochasticOscillator(high, low, close, window=14)
            stoch_k = stoch.stoch()
            if not stoch_k.empty:
                k_val = stoch_k.iloc[-1]
                if k_val < 20:
                    impact = 8
                elif k_val > 80:
                    impact = -8
                else:
                    impact = 0
                score += impact
                factors.append(AnalysisFactor(
                    "Stochastic", f"K={k_val:.1f}", impact,
                    f"Stochastic {'oversold' if k_val < 20 else 'overbought' if k_val > 80 else 'neutral'}"))

        # Williams %R
        if len(close) >= 14:
            williams = WilliamsRIndicator(high, low, close, lbp=14).williams_r()
            if not williams.empty:
                wr_val = williams.iloc[-1]
                if wr_val < -80:
                    impact = 5
                elif wr_val > -20:
                    impact = -5
                else:
                    impact = 0
                score += impact
                factors.append(AnalysisFactor("Williams %R", f"{wr_val:.1f}", impact,
                    f"Williams %R {'oversold' if wr_val < -80 else 'overbought' if wr_val > -20 else 'neutral'}"))

        # --- VOLUME ---
        # Volume vs 20-day average
        if len(volume) >= 20:
            avg_vol = volume.rolling(20).mean().iloc[-1]
            vol_ratio = volume.iloc[-1] / avg_vol if avg_vol > 0 else 1
            if vol_ratio > 1.5:
                # High volume - confirms trend
                impact = 5 if score > 0 else -5
                factors.append(AnalysisFactor(
                    "Volume", f"{vol_ratio:.1f}x avg",
                    impact, f"Volume {vol_ratio:.1f}x above 20-day average (trend confirmation)"))
                score += impact
            confidence_factors.append(min(1.0, 0.5 + vol_ratio * 0.2))

        # OBV trend
        obv = OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        if len(obv) >= 20:
            obv_sma = obv.rolling(20).mean()
            obv_bullish = obv.iloc[-1] > obv_sma.iloc[-1]
            impact = 5 if obv_bullish else -5
            score += impact
            factors.append(AnalysisFactor(
                "OBV", "Rising" if obv_bullish else "Falling",
                impact, f"On-Balance Volume {'above' if obv_bullish else 'below'} its 20-day average"))

        # --- VOLATILITY ---
        # Bollinger Bands
        bb = BollingerBands(close, window=20, window_dev=2)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_pct = bb.bollinger_pband().iloc[-1] if hasattr(bb, 'bollinger_pband') else None

        if current_price <= bb_lower:
            impact = 10
            explanation = f"Price at/below lower Bollinger Band (oversold, ${current_price:.2f} vs ${bb_lower:.2f})"
        elif current_price >= bb_upper:
            impact = -10
            explanation = f"Price at/above upper Bollinger Band (overbought, ${current_price:.2f} vs ${bb_upper:.2f})"
        else:
            impact = 0
            explanation = f"Price within Bollinger Bands (${bb_lower:.2f} - ${bb_upper:.2f})"
        score += impact
        factors.append(AnalysisFactor("Bollinger Bands", f"${current_price:.2f}", impact, explanation))

        # ATR for volatility assessment
        atr = AverageTrueRange(high, low, close, window=14).average_true_range()
        if not atr.empty:
            atr_pct = (atr.iloc[-1] / current_price) * 100
            factors.append(AnalysisFactor(
                "ATR(14)", f"{atr_pct:.2f}% of price",
                0, f"Average True Range is {atr_pct:.2f}% of price (volatility measure)"))

        # --- MOMENTUM (30-day) ---
        if len(close) >= 30:
            month_ago = close.iloc[-30]
            momentum = ((current_price - month_ago) / month_ago) * 100
            if momentum > 10:
                impact = 10
            elif momentum > 5:
                impact = 5
            elif momentum < -10:
                impact = -10
            elif momentum < -5:
                impact = -5
            else:
                impact = 0
            score += impact
            factors.append(AnalysisFactor(
                "30-Day Momentum", f"{momentum:+.1f}%", impact,
                f"Price {'up' if momentum > 0 else 'down'} {abs(momentum):.1f}% over 30 days"))
            confidence_factors.append(0.7)

        # --- 52-Week Range ---
        if len(close) >= 252:
            high_52w = close.rolling(252).max().iloc[-1]
            low_52w = close.rolling(252).min().iloc[-1]
        else:
            high_52w = close.max()
            low_52w = close.min()
        range_pos = (current_price - low_52w) / (high_52w - low_52w) if high_52w != low_52w else 0.5
        factors.append(AnalysisFactor(
            "52-Week Position", f"{range_pos*100:.0f}% (${low_52w:.2f}-${high_52w:.2f})",
            0, f"Trading at {range_pos*100:.0f}% of 52-week range"))

        # --- MONEY FLOW INDEX (MFI) ---
        if len(close) >= 14:
            try:
                mfi = MFIIndicator(high, low, close, volume, window=14).money_flow_index()
                if not mfi.empty:
                    mfi_val = mfi.iloc[-1]
                    if mfi_val < 20:
                        impact = 10
                        explanation = f"MFI oversold at {mfi_val:.1f} (money flowing in)"
                    elif mfi_val > 80:
                        impact = -10
                        explanation = f"MFI overbought at {mfi_val:.1f} (money flowing out)"
                    else:
                        impact = 0
                        explanation = f"MFI neutral at {mfi_val:.1f}"
                    score += impact
                    factors.append(AnalysisFactor("MFI(14)", f"{mfi_val:.1f}", impact, explanation))
                    confidence_factors.append(0.8)
            except Exception:
                pass

        # --- ADX (Average Directional Index) ---
        if len(close) >= 14:
            try:
                adx_ind = ADXIndicator(high, low, close, window=14)
                adx_val = adx_ind.adx().iloc[-1]
                adx_pos = adx_ind.adx_pos().iloc[-1]
                adx_neg = adx_ind.adx_neg().iloc[-1]
                if adx_val > 25:
                    # Strong trend — direction from +DI vs -DI
                    if adx_pos > adx_neg:
                        impact = 8
                        explanation = f"Strong uptrend (ADX={adx_val:.0f}, +DI > -DI)"
                    else:
                        impact = -8
                        explanation = f"Strong downtrend (ADX={adx_val:.0f}, -DI > +DI)"
                else:
                    impact = 0
                    explanation = f"Weak/no trend (ADX={adx_val:.0f})"
                score += impact
                factors.append(AnalysisFactor("ADX", f"{adx_val:.0f}", impact, explanation))
            except Exception:
                pass

        # --- ICHIMOKU CLOUD ---
        if len(close) >= 52:
            try:
                ichi = IchimokuIndicator(high, low, window1=9, window2=26, window3=52)
                span_a = ichi.ichimoku_a().iloc[-1]
                span_b = ichi.ichimoku_b().iloc[-1]
                if current_price > max(span_a, span_b):
                    impact = 10
                    explanation = f"Price above Ichimoku Cloud (bullish, cloud: {min(span_a, span_b):.2f}-{max(span_a, span_b):.2f})"
                elif current_price < min(span_a, span_b):
                    impact = -10
                    explanation = f"Price below Ichimoku Cloud (bearish, cloud: {min(span_a, span_b):.2f}-{max(span_a, span_b):.2f})"
                else:
                    impact = 0
                    explanation = f"Price inside Ichimoku Cloud (consolidation)"
                score += impact
                factors.append(AnalysisFactor("Ichimoku", f"${current_price:.2f}", impact, explanation))
                confidence_factors.append(0.85)
            except Exception:
                pass

        # --- RSI DIVERGENCE ---
        if not rsi.empty and len(rsi) >= 20:
            try:
                rsi_20 = rsi.iloc[-20:]
                price_20 = close.iloc[-20:]
                price_direction = 1 if price_20.iloc[-1] > price_20.iloc[0] else -1
                rsi_direction = 1 if rsi_20.iloc[-1] > rsi_20.iloc[0] else -1
                if price_direction != rsi_direction:
                    if price_direction > 0 and rsi_direction < 0:
                        impact = -8
                        explanation = "Bearish RSI divergence: price rising but RSI falling"
                    else:
                        impact = 8
                        explanation = "Bullish RSI divergence: price falling but RSI rising"
                    score += impact
                    factors.append(AnalysisFactor("RSI Divergence", "Detected", impact, explanation))
            except Exception:
                pass

        # --- RELATIVE STRENGTH VS SPY ---
        try:
            spy = yf.Ticker("SPY").history(period="3mo")
            if not spy.empty and len(spy) >= 20:
                spy_close = spy["Close"]
                stock_ret_20 = (close.iloc[-1] / close.iloc[-20] - 1) * 100
                spy_ret_20 = (spy_close.iloc[-1] / spy_close.iloc[-20] - 1) * 100
                rel_strength = stock_ret_20 - spy_ret_20
                if rel_strength > 5:
                    impact = 8
                    explanation = f"Outperforming SPY by {rel_strength:+.1f}% over 20 days"
                elif rel_strength < -5:
                    impact = -8
                    explanation = f"Underperforming SPY by {rel_strength:+.1f}% over 20 days"
                else:
                    impact = 0
                    explanation = f"Tracking SPY ({rel_strength:+.1f}% relative over 20 days)"
                score += impact
                factors.append(AnalysisFactor("Rel. Strength vs SPY", f"{rel_strength:+.1f}%", impact, explanation))
        except Exception:
            pass

        # Calculate confidence
        if confidence_factors:
            confidence = np.mean(confidence_factors) * min(1.0, len(hist) / 200)
        else:
            confidence = 0.5

        score = max(-100, min(100, score))
        summary = self._build_summary(score, factors)
        return self._make_result(score, confidence, factors, summary)

    def _build_summary(self, score: float, factors: list[AnalysisFactor]) -> str:
        bullish = [f for f in factors if f.impact > 0]
        bearish = [f for f in factors if f.impact < 0]

        parts = []
        if score > 20:
            parts.append(f"Technical outlook is bullish ({len(bullish)} positive signals)")
        elif score < -20:
            parts.append(f"Technical outlook is bearish ({len(bearish)} negative signals)")
        else:
            parts.append("Technical outlook is neutral (mixed signals)")

        top_factors = sorted(factors, key=lambda f: abs(f.impact), reverse=True)[:3]
        for f in top_factors:
            parts.append(f"  - {f.name}: {f.explanation}")

        return ". ".join(parts[:1]) + "\n" + "\n".join(parts[1:])

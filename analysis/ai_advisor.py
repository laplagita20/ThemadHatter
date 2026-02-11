"""AI Financial Advisor powered by Groq (free tier).

Provides personalized portfolio insights, stock explanations, trade suggestions,
and free-form Q&A. Gracefully degrades when no API key is configured.
"""

import json
import logging
from datetime import datetime

from config.settings import get_settings
from database.models import (
    PortfolioDAO, DecisionDAO, UserPreferencesDAO,
    AIAdviceCacheDAO, AnalysisResultDAO, UserWatchlistDAO,
)

logger = logging.getLogger("stock_model.ai_advisor")

# Model constants
PRIMARY_MODEL = "llama-3.3-70b-versatile"


class GroqAdvisor:
    """AI financial advisor backed by Groq API (free tier)."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self._client = None
        self._prefs = None
        self._cache_dao = AIAdviceCacheDAO()
        self._prefs_dao = UserPreferencesDAO()

    def is_available(self) -> bool:
        """Check if the Groq API key is configured."""
        settings = get_settings()
        return bool(settings.groq_api_key)

    def _get_client(self):
        """Lazy-init Groq client."""
        if self._client is None:
            try:
                from groq import Groq
                settings = get_settings()
                self._client = Groq(api_key=settings.groq_api_key)
            except Exception as e:
                logger.error("Failed to initialize Groq client: %s", e)
                raise
        return self._client

    def _get_prefs(self) -> dict:
        """Get user preferences (cached per instance)."""
        if self._prefs is None:
            self._prefs = self._prefs_dao.get(self.user_id)
        return self._prefs

    def _build_system_prompt(self) -> str:
        """Build a personalized system prompt based on user preferences."""
        prefs = self._get_prefs()
        risk = prefs.get("risk_tolerance", "moderate")
        horizon = prefs.get("investment_horizon", "medium")
        experience = prefs.get("experience_level", "intermediate")
        personality = prefs.get("ai_personality", "balanced")

        personality_map = {
            "concise": "Be very brief and direct. Use bullet points. No fluff.",
            "balanced": "Be clear and informative. Balance detail with readability.",
            "detailed": "Be thorough and educational. Explain reasoning in depth.",
            "encouraging": "Be supportive and positive while being honest about risks.",
        }
        style = personality_map.get(personality, personality_map["balanced"])

        experience_map = {
            "beginner": "Explain financial concepts simply. Avoid jargon or define it when used.",
            "intermediate": "You can use standard financial terminology.",
            "advanced": "Use technical financial language freely. Include quantitative details.",
        }
        exp_style = experience_map.get(experience, experience_map["intermediate"])

        return f"""You are The Mad Hatter, an AI financial advisor built into a portfolio management app.

User Profile:
- Risk Tolerance: {risk}
- Investment Horizon: {horizon} term
- Experience Level: {experience}

Communication Style:
{style}
{exp_style}

Guidelines:
- Always be honest about uncertainty and risks.
- Never guarantee returns or make promises about future performance.
- Reference specific data when available (scores, prices, P&L).
- Format responses with markdown for readability.
- Keep responses focused and actionable.
- When suggesting actions, explain the reasoning.
- Today's date is {datetime.now().strftime('%B %d, %Y')}."""

    def _build_portfolio_context(self) -> str:
        """Build context string with user's current portfolio."""
        portfolio_dao = PortfolioDAO()
        holdings = list(portfolio_dao.get_latest_holdings(self.user_id))
        if not holdings:
            return "User has no portfolio holdings."

        total_value = sum(h.get("market_value") or 0 for h in holdings)
        total_pl = sum(h.get("unrealized_pl") or 0 for h in holdings)

        lines = [f"Portfolio: {len(holdings)} positions, ${total_value:,.0f} total value, "
                 f"${total_pl:+,.0f} unrealized P&L"]
        lines.append("Holdings:")
        for h in holdings[:20]:  # Cap context size
            ticker = h["ticker"]
            qty = h.get("quantity", 0)
            cost = h.get("average_cost", 0)
            price = h.get("current_price", 0)
            mv = h.get("market_value", 0)
            pl = h.get("unrealized_pl", 0)
            pl_pct = h.get("unrealized_pl_pct", 0)
            lines.append(
                f"  {ticker}: {qty} shares @ ${cost:,.2f} avg, "
                f"now ${price:,.2f}, value ${mv:,.0f}, P&L ${pl:+,.0f} ({pl_pct:+.1f}%)"
            )
        return "\n".join(lines)

    def _build_decisions_context(self, tickers: list[str] = None) -> str:
        """Build context with latest analysis decisions for given tickers."""
        decision_dao = DecisionDAO()
        if tickers is None:
            # Use portfolio tickers
            portfolio_dao = PortfolioDAO()
            holdings = list(portfolio_dao.get_latest_holdings(self.user_id))
            tickers = [h["ticker"] for h in holdings]

        if not tickers:
            return "No analysis data available."

        lines = ["Latest Analysis:"]
        for ticker in tickers[:15]:
            d = decision_dao.get_latest(ticker, self.user_id)
            if d:
                lines.append(
                    f"  {ticker}: {d['action']} (score {d.get('composite_score', 0):.1f}, "
                    f"confidence {d.get('confidence', 0):.0%})"
                )
                if d.get("bull_case"):
                    lines.append(f"    Bull: {d['bull_case'][:100]}")
                if d.get("bear_case"):
                    lines.append(f"    Bear: {d['bear_case'][:100]}")
        return "\n".join(lines)

    def _build_watchlist_context(self) -> str:
        """Build context with user's watchlist."""
        wl_dao = UserWatchlistDAO()
        tickers = wl_dao.get_tickers(self.user_id)
        if not tickers:
            return "Watchlist is empty."
        return f"Watchlist: {', '.join(tickers)}"

    def _call_llm(self, messages: list[dict], system: str = None,
                  model: str = None, max_tokens: int = 1500) -> tuple[str, dict]:
        """Make a Groq API call. Returns (response_text, usage_dict)."""
        client = self._get_client()
        model = model or PRIMARY_MODEL
        system = system or self._build_system_prompt()

        full_messages = [{"role": "system", "content": system}] + messages
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        text = response.choices[0].message.content
        usage = {
            "model": model,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.prompt_tokens + response.usage.completion_tokens,
        }
        return text, usage

    def _stream_llm(self, messages: list[dict], system: str = None,
                    model: str = None, max_tokens: int = 1500):
        """Stream a Groq API response. Yields text chunks."""
        client = self._get_client()
        model = model or PRIMARY_MODEL
        system = system or self._build_system_prompt()

        full_messages = [{"role": "system", "content": system}] + messages
        stream = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices[0].delta else None
            if delta:
                yield delta

    # --- Public API ---

    def get_portfolio_digest(self) -> str:
        """Get a daily portfolio summary with insights. Cached 12h."""
        if not self.is_available():
            return None

        cache_key = datetime.now().strftime("%Y-%m-%d")
        cached = self._cache_dao.get_cached(self.user_id, "portfolio_digest", cache_key)
        if cached:
            return cached["response_text"]

        portfolio_ctx = self._build_portfolio_context()
        decisions_ctx = self._build_decisions_context()

        messages = [{"role": "user", "content": f"""Give me a daily portfolio digest.

{portfolio_ctx}

{decisions_ctx}

Provide:
1. Overall portfolio health assessment (1-2 sentences)
2. Notable changes or concerns (if any)
3. One actionable suggestion for today

Keep it concise and conversational."""}]

        try:
            text, usage = self._call_llm(messages, max_tokens=800)
            self._cache_dao.store(
                self.user_id, "portfolio_digest", cache_key, text,
                model_used=usage["model"], tokens_used=usage["total_tokens"],
                ttl_hours=12,
            )
            return text
        except Exception as e:
            logger.error("Portfolio digest failed: %s", e)
            return None

    def explain_stock(self, ticker: str) -> str:
        """Get a plain-English explanation of a stock's analysis. Cached 6h."""
        if not self.is_available():
            return None

        cached = self._cache_dao.get_cached(self.user_id, "stock_explain", ticker)
        if cached:
            return cached["response_text"]

        # Gather context
        decision_dao = DecisionDAO()
        analysis_dao = AnalysisResultDAO()
        d = decision_dao.get_latest(ticker, self.user_id)
        analyses = list(analysis_dao.get_latest(ticker) or [])

        portfolio_ctx = self._build_portfolio_context()

        analysis_lines = [f"Analysis for {ticker}:"]
        if d:
            analysis_lines.append(f"Overall: {d['action']} (score {d.get('composite_score', 0):.1f})")
            if d.get("bull_case"):
                analysis_lines.append(f"Bull case: {d['bull_case']}")
            if d.get("bear_case"):
                analysis_lines.append(f"Bear case: {d['bear_case']}")
            if d.get("risk_warnings"):
                analysis_lines.append(f"Risks: {d['risk_warnings']}")
        for a in analyses:
            analysis_lines.append(
                f"  {a['analyzer_name']}: {a['signal']} (score {a['score']:.1f}, "
                f"confidence {a['confidence']:.0%}) — {a.get('summary', '')}"
            )

        messages = [{"role": "user", "content": f"""Explain {ticker} to me in plain English.

{chr(10).join(analysis_lines)}

{portfolio_ctx}

Tell me:
1. What does this stock do? (brief)
2. What does the analysis say? (translate scores into plain language)
3. Does it fit my portfolio? Why or why not?
4. What would you suggest? (buy, hold, sell, or watch)"""}]

        try:
            text, usage = self._call_llm(messages, max_tokens=1200)
            self._cache_dao.store(
                self.user_id, "stock_explain", ticker, text,
                model_used=usage["model"], tokens_used=usage["total_tokens"],
                ttl_hours=6,
            )
            return text
        except Exception as e:
            logger.error("Stock explain failed for %s: %s", ticker, e)
            return None

    def answer_question(self, question: str) -> str:
        """Answer a free-form question about the user's portfolio/markets."""
        if not self.is_available():
            return None

        portfolio_ctx = self._build_portfolio_context()
        decisions_ctx = self._build_decisions_context()
        watchlist_ctx = self._build_watchlist_context()

        messages = [{"role": "user", "content": f"""User question: {question}

Context:
{portfolio_ctx}

{decisions_ctx}

{watchlist_ctx}

Answer the question helpfully and concisely. If the question is about a specific stock,
reference analysis data if available. If it's a general market question, provide your
best analysis while noting uncertainty."""}]

        try:
            text, _ = self._call_llm(messages, max_tokens=1500)
            return text
        except Exception as e:
            logger.error("Answer question failed: %s", e)
            return None

    def stream_answer(self, question: str, chat_history: list[dict] = None):
        """Stream an answer to a free-form question. Yields text chunks."""
        if not self.is_available():
            yield "AI advisor is not configured. Add your Groq API key in Settings (it's free!)."
            return

        portfolio_ctx = self._build_portfolio_context()
        decisions_ctx = self._build_decisions_context()
        watchlist_ctx = self._build_watchlist_context()

        system = self._build_system_prompt() + f"""

Current Portfolio Context:
{portfolio_ctx}

{decisions_ctx}

{watchlist_ctx}"""

        messages = []
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": question})

        try:
            yield from self._stream_llm(messages, system=system, max_tokens=1500)
        except Exception as e:
            logger.error("Stream answer failed: %s", e)
            yield f"Sorry, I encountered an error: {e}"

    def get_trade_suggestion(self) -> str:
        """Get a deep AI-powered trade suggestion. Cached 24h."""
        if not self.is_available():
            return None

        cache_key = datetime.now().strftime("%Y-%m-%d")
        cached = self._cache_dao.get_cached(self.user_id, "trade_suggestion", cache_key)
        if cached:
            return cached["response_text"]

        portfolio_ctx = self._build_portfolio_context()
        decisions_ctx = self._build_decisions_context()
        watchlist_ctx = self._build_watchlist_context()

        messages = [{"role": "user", "content": f"""As my financial advisor, what is the single best trade I should consider right now?

{portfolio_ctx}

{decisions_ctx}

{watchlist_ctx}

Analyze deeply and provide:
1. **The Trade**: Specific action (buy/sell ticker, approximate allocation)
2. **Why Now**: What makes this timely?
3. **The Bull Case**: Best scenario and upside potential
4. **The Bear Case**: What could go wrong and downside risk
5. **Risk Management**: Suggested stop-loss or position size
6. **Confidence Level**: How confident are you (low/medium/high) and why

Be thorough but practical. This should be an actionable recommendation."""}]

        try:
            text, usage = self._call_llm(
                messages, model=PRIMARY_MODEL, max_tokens=2000
            )
            self._cache_dao.store(
                self.user_id, "trade_suggestion", cache_key, text,
                model_used=usage["model"], tokens_used=usage["total_tokens"],
                ttl_hours=24,
            )
            return text
        except Exception as e:
            logger.error("Trade suggestion failed: %s", e)
            return None

    def get_smart_alerts(self) -> list[dict]:
        """Generate rule-based smart alerts (no AI needed).

        Returns list of {severity, title, detail, category} dicts.
        """
        alerts = []
        portfolio_dao = PortfolioDAO()
        decision_dao = DecisionDAO()
        holdings = list(portfolio_dao.get_latest_holdings(self.user_id))

        if not holdings:
            return alerts

        # Tax-loss harvest candidates
        for h in holdings:
            pl_pct = h.get("unrealized_pl_pct", 0) or 0
            if pl_pct < -10:
                alerts.append({
                    "severity": "info",
                    "title": f"Tax-loss harvest: {h['ticker']}",
                    "detail": f"Down {pl_pct:.1f}% — consider harvesting the loss for tax benefits.",
                    "category": "tax",
                })

        # Strong signals from analysis
        for h in holdings:
            d = decision_dao.get_latest(h["ticker"], self.user_id)
            if not d:
                continue
            score = d.get("composite_score", 0) or 0
            action = d.get("action", "")
            if score >= 0.7 and action.upper() in ("STRONG BUY", "BUY"):
                alerts.append({
                    "severity": "success",
                    "title": f"Strong buy signal: {h['ticker']}",
                    "detail": f"Score {score:.2f} — analysis is very bullish.",
                    "category": "signal",
                })
            elif score <= -0.5 and action.upper() in ("SELL", "STRONG SELL"):
                alerts.append({
                    "severity": "warning",
                    "title": f"Sell signal: {h['ticker']}",
                    "detail": f"Score {score:.2f} — consider reducing position.",
                    "category": "signal",
                })

        # Concentration risk
        total_value = sum(h.get("market_value") or 0 for h in holdings) or 1
        for h in holdings:
            weight = ((h.get("market_value") or 0) / total_value) * 100
            if weight > 25:
                alerts.append({
                    "severity": "warning",
                    "title": f"Concentration risk: {h['ticker']}",
                    "detail": f"{weight:.0f}% of portfolio — consider diversifying.",
                    "category": "risk",
                })

        return alerts


# Backward-compatibility alias
ClaudeAdvisor = GroqAdvisor

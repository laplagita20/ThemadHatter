"""Teach Me - plain English educational explanations for financial concepts.

Every metric, chart, and recommendation in the dashboard can have a
'Teach Me' expander that breaks it down in simple terms.
"""

import streamlit as st

# Plain-English explanations keyed by topic
EXPLANATIONS = {
    # --- Portfolio Concepts ---
    "portfolio_value": {
        "title": "Portfolio Value",
        "simple": "This is the total dollar amount your investments are worth right now, based on today's stock prices.",
        "detail": (
            "Think of it like checking your bank balance, but for stocks. "
            "If you own 10 shares of a $150 stock and 5 shares of a $300 stock, "
            "your portfolio value is (10 x $150) + (5 x $300) = $3,000. "
            "This number changes every day as stock prices move."
        ),
    },
    "unrealized_pl": {
        "title": "Unrealized P&L (Profit & Loss)",
        "simple": "How much money you've made or lost on paper - but haven't actually cashed out yet.",
        "detail": (
            "If you bought a stock at $100 and it's now worth $120, you have an 'unrealized' gain of $20. "
            "It's 'unrealized' because you haven't sold it yet - the profit only becomes real (realized) when you sell. "
            "A positive number means you're up, negative means you're down."
        ),
    },
    "cost_basis": {
        "title": "Cost Basis",
        "simple": "The average price you paid per share. This is your break-even point.",
        "detail": (
            "If you bought 5 shares at $100 and 5 more at $120, your cost basis is $110 per share "
            "(total spent $1,100 / 10 shares). The stock price needs to be above your cost basis for you to be in profit."
        ),
    },
    "sector_allocation": {
        "title": "Sector Allocation",
        "simple": "How your money is spread across different types of businesses (tech, healthcare, finance, etc).",
        "detail": (
            "Diversification is like not putting all your eggs in one basket. "
            "If all your money is in tech stocks and the tech industry has a bad year, your whole portfolio suffers. "
            "Spreading across sectors helps protect you. Most advisors suggest no single sector should be more than 25-30% of your portfolio."
        ),
    },
    "recurring_investment": {
        "title": "Recurring Investment (DCA)",
        "simple": "Automatically investing a fixed dollar amount on a regular schedule, regardless of the stock price.",
        "detail": (
            "This strategy is called Dollar-Cost Averaging (DCA). Instead of trying to time the market "
            "(buy low, sell high - which is extremely hard), you invest the same amount regularly. "
            "When prices are low, your money buys more shares. When prices are high, you buy fewer shares. "
            "Over time, this averages out and removes the stress of timing. "
            "It's one of the most recommended strategies for long-term investing."
        ),
    },

    # --- Analysis Concepts ---
    "composite_score": {
        "title": "Composite Score",
        "simple": "A single number from -100 to +100 that summarizes whether a stock looks like a good buy, hold, or sell.",
        "detail": (
            "We run multiple types of analysis (technical patterns, financial health, insider buying, etc.) "
            "and combine them into one score. Think of it like a report card grade that averages all subjects. "
            "+50 or higher = strong buy signal. 0 = neutral. -50 or lower = strong sell signal."
        ),
    },
    "confidence": {
        "title": "Confidence Level",
        "simple": "How sure the system is about its recommendation. Higher = more data supporting the conclusion.",
        "detail": (
            "A confidence of 80% means the system has plenty of data and the signals agree. "
            "A confidence of 30% means there's limited data or the signals are mixed/contradicting each other. "
            "Low confidence recommendations should be taken with a grain of salt - do more research."
        ),
    },
    "conviction_score": {
        "title": "Conviction Score",
        "simple": "How strongly all the different analysis signals agree with each other.",
        "detail": (
            "If technical analysis says buy, fundamentals say buy, and insider buying is heavy - that's high conviction. "
            "If technical says buy but fundamentals say sell - that's low conviction. "
            "High conviction (70+) means the opportunity looks solid from multiple angles."
        ),
    },
    "position_size": {
        "title": "Recommended Position Size",
        "simple": "What percentage of your total portfolio should go into this stock.",
        "detail": (
            "A 5% position size means if you have $10,000 invested total, you'd put $500 in this stock. "
            "Larger position sizes (8-10%) mean the system is very confident. "
            "Smaller sizes (1-3%) mean it's a speculative idea - worth having but don't bet big on it. "
            "Never putting too much in one stock protects you if things go wrong."
        ),
    },
    "stop_loss": {
        "title": "Stop Loss",
        "simple": "A safety net - the price at which you should sell to cut your losses before they get too big.",
        "detail": (
            "A 15% stop loss means if the stock drops 15% from your purchase price, you sell. "
            "It's like having a fire alarm - you don't want to use it, but it protects you from disaster. "
            "Professional traders always have stop losses. Never let a small loss turn into a big one."
        ),
    },

    # --- Technical Analysis ---
    "technical_analysis": {
        "title": "Technical Analysis",
        "simple": "Studying stock price charts and patterns to predict where the price might go next.",
        "detail": (
            "Technical analysis looks at things like: Is the stock trending up or down? "
            "Is it moving on high trading volume (lots of people buying/selling)? "
            "Are there repeating patterns? It's like weather forecasting but for stocks - "
            "it looks at what happened before to guess what might happen next. "
            "It works best for short-term timing decisions."
        ),
    },
    "fundamental_analysis": {
        "title": "Fundamental Analysis",
        "simple": "Looking at a company's financial health - is it making money, growing, and priced fairly?",
        "detail": (
            "This is like checking a company's report card: How much profit does it make? "
            "Is revenue growing? Does it have too much debt? "
            "A company can have a high stock price but actually be in terrible financial shape (overvalued), "
            "or a low stock price but be incredibly healthy (undervalued). "
            "Fundamental analysis helps you tell the difference."
        ),
    },
    "insider_trading": {
        "title": "Insider Trading Activity",
        "simple": "When company executives buy or sell their own company's stock - a clue about what they think is coming.",
        "detail": (
            "Company insiders (CEOs, CFOs, board members) know their business better than anyone. "
            "When they buy stock with their own money, it's often a bullish signal - they think the stock will go up. "
            "When they sell heavily, it might mean they think the stock is overvalued. "
            "Note: insiders sell for many reasons (buying a house, diversifying), so selling isn't always bearish."
        ),
    },

    # --- Price Targets & Scenarios ---
    "price_targets": {
        "title": "Price Targets",
        "simple": "Where analysts think the stock price is heading over the next 12 months.",
        "detail": (
            "Price targets come from different methods: "
            "DCF (calculating what the company is actually worth), "
            "analyst consensus (what Wall Street professionals predict), and "
            "technical targets (based on chart patterns). "
            "The 'blended target' combines all of these. If the target is above the current price, it suggests upside."
        ),
    },
    "scenario_analysis": {
        "title": "Scenario Analysis",
        "simple": "Three possible futures: what happens if things go great (bull), okay (base), or badly (bear).",
        "detail": (
            "Bull case: Everything goes right - strong earnings, positive news, market momentum. "
            "Base case: Things continue roughly as they are. "
            "Bear case: Things go wrong - missed earnings, bad news, market downturn. "
            "Each scenario has a probability and a price target. This helps you understand your risk vs reward."
        ),
    },

    # --- Risk Concepts ---
    "var": {
        "title": "Value at Risk (VaR)",
        "simple": "The worst-case daily loss you can expect 95% of the time.",
        "detail": (
            "If your VaR is 2%, that means on 95 out of 100 trading days, "
            "you should NOT lose more than 2% of your portfolio. "
            "The other 5 days could be worse. It's a way to measure how risky your portfolio is. "
            "Lower VaR = less risky. A VaR above 5% means your portfolio is quite aggressive."
        ),
    },
    "monte_carlo": {
        "title": "Monte Carlo Simulation",
        "simple": "Running thousands of 'what-if' scenarios to see the range of possible outcomes for your portfolio.",
        "detail": (
            "Imagine rolling dice 10,000 times to see all possible outcomes. "
            "That's what Monte Carlo does with your stocks - it simulates thousands of possible futures "
            "based on how your stocks have behaved historically. "
            "The fan chart shows the best case (top), worst case (bottom), and most likely case (middle)."
        ),
    },
    "diversification": {
        "title": "Diversification",
        "simple": "Don't put all your eggs in one basket. Spread your money across different stocks and sectors.",
        "detail": (
            "When stocks are correlated (they move together), you're not truly diversified. "
            "If you own 5 tech stocks, they'll all drop together when tech has a bad day. "
            "True diversification means mixing stocks that don't always move the same way - "
            "so when some go down, others might go up or stay flat."
        ),
    },

    # --- News ---
    "news_sentiment": {
        "title": "News Sentiment",
        "simple": "Whether recent news about a stock is positive, negative, or neutral overall.",
        "detail": (
            "News drives short-term stock movements. If a company beats earnings expectations, "
            "the news is positive and the stock often jumps. Bad news like lawsuits, product recalls, "
            "or missed targets can cause drops. We analyze news headlines to gauge the overall mood "
            "around a stock, which can help predict near-term price direction."
        ),
    },

    # --- Scoring Models ---
    "piotroski_score": {
        "title": "Piotroski F-Score",
        "simple": "A 0-9 score measuring a company's financial strength. Higher is healthier.",
        "detail": (
            "Created by professor Joseph Piotroski, this score checks 9 things: "
            "Is the company profitable? Is profitability improving? Is cash flow positive? "
            "Is debt decreasing? Are margins expanding? Is the company efficient? "
            "A score of 7-9 means the company is financially rock-solid. "
            "0-3 means the company might be in trouble. Great for filtering out unhealthy companies."
        ),
    },
    "altman_z_score": {
        "title": "Altman Z-Score",
        "simple": "Predicts whether a company might go bankrupt within 2 years. Above 3 = safe, below 1.8 = danger.",
        "detail": (
            "Invented by Edward Altman in 1968, this formula has been amazingly accurate at predicting bankruptcy. "
            "It looks at working capital, retained earnings, profitability, market value vs debt, and revenue efficiency. "
            "Z > 3.0 = Safe zone. 1.8 < Z < 3.0 = Gray zone (caution). Z < 1.8 = Distress zone (danger)."
        ),
    },
    "dcf_valuation": {
        "title": "DCF Valuation",
        "simple": "Calculating what a stock is actually worth by adding up all the money the company will make in the future.",
        "detail": (
            "DCF stands for Discounted Cash Flow. The idea is: a company is worth the total of all its future profits, "
            "but future money is worth less than today's money (because of inflation and opportunity cost). "
            "If the DCF value is higher than the current stock price, the stock might be undervalued (a bargain). "
            "Margin of Safety is how much cheaper the stock is vs the DCF value - bigger margin = better deal."
        ),
    },

    # --- Recommendations ---
    "buy_recommendation": {
        "title": "Buy Recommendation",
        "simple": "The system thinks this stock is likely to increase in value based on multiple analysis methods.",
        "detail": (
            "A buy recommendation means the composite score is positive (above +15), "
            "the confidence level is reasonable, and multiple analysis signals agree. "
            "It's not a guarantee - it's an informed opinion based on data. "
            "Always consider: position sizing (don't go all-in), stop losses (protect yourself), "
            "and your own research (no system is perfect)."
        ),
    },
    "hold_recommendation": {
        "title": "Hold Recommendation",
        "simple": "The stock is in a neutral zone - no strong reason to buy more or sell what you have.",
        "detail": (
            "A hold means the signals are mixed or the stock is fairly valued. "
            "If you already own it, keep it. If you don't own it, there might be better opportunities elsewhere. "
            "Hold doesn't mean 'do nothing forever' - it means 'wait for a clearer signal.'"
        ),
    },
    "sell_recommendation": {
        "title": "Sell Recommendation",
        "simple": "The system sees warning signs - the stock may decline. Consider reducing your position.",
        "detail": (
            "A sell recommendation means the composite score is negative (below -15) and/or "
            "multiple risk factors are present: deteriorating financials, insider selling, "
            "negative technical trends, or overvaluation. "
            "Selling is the hardest decision in investing, but cutting losers early is what separates good investors from bad ones."
        ),
    },
    "macro_regime": {
        "title": "Macro Economic Regime",
        "simple": "The big-picture economic environment that affects ALL stocks - growth, inflation, interest rates.",
        "detail": (
            "Macro regimes are like the weather for the stock market. In a 'Goldilocks' economy "
            "(moderate growth, low inflation), most stocks do well. In 'stagflation' "
            "(slow growth + high inflation), most stocks struggle. "
            "Understanding the macro regime helps you know whether to be aggressive (more stocks) "
            "or defensive (more cash, safer sectors)."
        ),
    },
}


def teach_me(topic: str, inline: bool = False):
    """Render a 'Teach Me' educational expander for the given topic.

    Args:
        topic: Key from the EXPLANATIONS dict.
        inline: If True, show a compact tooltip-style explanation.
    """
    info = EXPLANATIONS.get(topic)
    if not info:
        return

    if inline:
        st.caption(f"**{info['title']}**: {info['simple']}")
    else:
        with st.expander(f"Teach Me: {info['title']}"):
            st.markdown(f"**In plain English:** {info['simple']}")
            st.markdown("---")
            st.markdown(f"**Going deeper:** {info['detail']}")


def teach_me_sidebar():
    """Add a learning mode toggle in the sidebar."""
    if "teach_mode" not in st.session_state:
        st.session_state.teach_mode = False
    st.session_state.teach_mode = st.sidebar.toggle(
        "Learning Mode",
        value=st.session_state.teach_mode,
        help="Show 'Teach Me' explanations throughout the dashboard",
    )
    return st.session_state.teach_mode


def teach_if_enabled(topic: str, inline: bool = False):
    """Show teach_me content only if Learning Mode is active."""
    if st.session_state.get("teach_mode", False):
        teach_me(topic, inline=inline)

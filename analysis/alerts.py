"""Rule-based smart alerts for portfolio monitoring.

Generates alerts for tax-loss harvest candidates, strong buy/sell signals,
and concentration risk — no AI dependency.
"""

from database.models import PortfolioDAO, DecisionDAO


def get_smart_alerts(user_id: int) -> list[dict]:
    """Generate rule-based smart alerts.

    Returns list of {severity, title, detail, category} dicts.
    """
    alerts = []
    portfolio_dao = PortfolioDAO()
    decision_dao = DecisionDAO()
    holdings = list(portfolio_dao.get_latest_holdings(user_id))

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
        d = decision_dao.get_latest(h["ticker"], user_id)
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

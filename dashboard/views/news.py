"""News Feed Dashboard Page - Portfolio, market, and political news from credible sources."""

import time
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from database.connection import get_connection
from database.models import StockDAO, NewsDAO, UserWatchlistDAO
from dashboard.components.auth import get_current_user_id
from dashboard.components.teach_me import teach_if_enabled

# Auto-refresh news if older than this many minutes
NEWS_STALE_MINUTES = 30

# Credible financial and political news sources (whitelist)
CREDIBLE_SOURCES = {
    # Tier 1 - Most credible
    "Reuters", "Associated Press", "AP News", "Bloomberg", "The Wall Street Journal",
    "WSJ", "Financial Times", "FT", "The New York Times", "The Washington Post",
    "BBC News", "BBC", "NPR",
    # Tier 2 - Major financial
    "CNBC", "MarketWatch", "Barron's", "Investor's Business Daily", "IBD",
    "The Economist", "Forbes", "Fortune", "Business Insider",
    # Tier 3 - Specialized financial
    "Seeking Alpha", "Motley Fool", "Yahoo Finance", "Yahoo", "Zacks",
    "TipRanks", "Benzinga", "TheStreet", "Morningstar",
    # Tier 4 - Political / General
    "Politico", "The Hill", "CNN", "CBS News", "NBC News", "ABC News",
    "PBS", "C-SPAN", "Al Jazeera", "The Guardian",
}

# Credibility scores (higher = more credible)
SOURCE_CREDIBILITY = {
    "Reuters": 1.0, "Associated Press": 1.0, "AP News": 1.0, "Bloomberg": 0.95,
    "The Wall Street Journal": 0.95, "WSJ": 0.95, "Financial Times": 0.95,
    "FT": 0.95, "The New York Times": 0.90, "BBC News": 0.90, "BBC": 0.90,
    "CNBC": 0.85, "MarketWatch": 0.85, "Barron's": 0.85, "The Economist": 0.90,
    "Forbes": 0.80, "Yahoo Finance": 0.75, "Yahoo": 0.75, "Seeking Alpha": 0.70,
    "Motley Fool": 0.70, "Benzinga": 0.70, "Morningstar": 0.85,
}

# Political/market news tickers (proxies for market-wide and political news)
MARKET_TICKERS = ["SPY", "QQQ", "DIA", "IWM", "VTI"]
POLITICAL_TICKERS = ["GLD", "TLT", "UUP", "DXY"]  # Gold, bonds, dollar - sensitive to political events


def _is_credible(source: str) -> bool:
    """Check if a source is in our credible whitelist (fuzzy match)."""
    if not source:
        return False
    source_lower = source.lower().strip()
    for cs in CREDIBLE_SOURCES:
        if cs.lower() in source_lower or source_lower in cs.lower():
            return True
    return False


def _get_credibility_score(source: str) -> float:
    """Get the credibility weight for a source."""
    if not source:
        return 0.5
    for name, score in SOURCE_CREDIBILITY.items():
        if name.lower() in source.lower() or source.lower() in name.lower():
            return score
    return 0.6  # Default for known but unscored sources


def _fetch_yfinance_news(ticker: str) -> list[dict]:
    """Fetch latest news for a ticker from yfinance, filtering for credible sources."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        news = stock.news
        if not news:
            return []
        articles = []
        for item in news:
            content = item.get("content", {})
            source = content.get("provider", {}).get("displayName", "Yahoo Finance")

            pub_date = content.get("pubDate", "")
            articles.append({
                "title": content.get("title", item.get("title", "No title")),
                "summary": content.get("summary", ""),
                "source": source,
                "url": content.get("canonicalUrl", {}).get("url", item.get("link", "")),
                "published_at": pub_date,
                "ticker": ticker,
                "credibility_weight": _get_credibility_score(source),
                "is_credible": _is_credible(source),
            })
        return articles
    except Exception:
        return []


def _store_articles(articles: list[dict]):
    """Store fetched articles in the database."""
    news_dao = NewsDAO()
    for article in articles:
        news_dao.insert(article)


def _render_article_card(article: dict, show_credibility: bool = False):
    """Render a single news article as a styled card."""
    source = article.get("source", "Unknown")
    pub = article.get("published_at") or article.get("fetched_at", "")
    if pub:
        try:
            if isinstance(pub, str):
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            else:
                dt = pub
            pub_display = dt.strftime("%b %d, %Y %I:%M %p")
        except (ValueError, TypeError):
            pub_display = str(pub)[:16]
    else:
        pub_display = ""

    url = article.get("url", "")
    title = article.get("title", "No title")
    summary = article.get("summary", "")
    ticker = article.get("ticker", "")
    credibility = article.get("credibility_weight", 0.7)

    # Credibility badge
    if credibility >= 0.9:
        cred_badge = '<span style="background: #10b981; color: white; padding: 1px 6px; border-radius: 3px; font-size: 0.65rem; margin-left: 6px;">VERIFIED</span>'
    elif credibility >= 0.8:
        cred_badge = '<span style="background: #06b6d4; color: white; padding: 1px 6px; border-radius: 3px; font-size: 0.65rem; margin-left: 6px;">TRUSTED</span>'
    else:
        cred_badge = ""

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(45, 27, 105, 0.3), rgba(30, 20, 70, 0.5));
                border: 1px solid rgba(124, 58, 237, 0.2); border-radius: 10px;
                padding: 16px; margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="color: #06b6d4; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px;">
                {source}{cred_badge if show_credibility else ""}
            </span>
            <span style="color: #94a3b8; font-size: 0.75rem;">{pub_display}</span>
        </div>
        <div style="font-size: 1.05rem; font-weight: 600; color: #e2e8f0; margin-bottom: 6px;">
            <a href="{url}" target="_blank" style="color: #e2e8f0; text-decoration: none;">
                {title}
            </a>
        </div>
        {"<div style='color: #94a3b8; font-size: 0.85rem; margin-bottom: 8px;'>" + summary[:250] + ("..." if len(summary) > 250 else "") + "</div>" if summary else ""}
        <div style="display: flex; gap: 8px; align-items: center;">
            {"<span style='background: rgba(124, 58, 237, 0.3); color: #a78bfa; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;'>" + ticker + "</span>" if ticker else ""}
            {"<a href='" + url + "' target='_blank' style='color: #f59e0b; font-size: 0.8rem; text-decoration: none;'>Read full article &rarr;</a>" if url else ""}
        </div>
    </div>
    """, unsafe_allow_html=True)


def _fetch_and_filter(tickers: list, credible_only: bool = True) -> list[dict]:
    """Fetch news for tickers and filter for credible sources."""
    all_articles = []
    for ticker in tickers:
        articles = _fetch_yfinance_news(ticker)
        _store_articles(articles)
        if credible_only:
            articles = [a for a in articles if a.get("is_credible", True)]
        all_articles.extend(articles)
    return all_articles


def _dedupe_and_sort(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles and sort by date."""
    seen_titles = set()
    unique = []
    for a in articles:
        title = a.get("title", "")
        if title and title not in seen_titles:
            seen_titles.add(title)
            unique.append(a)

    def sort_key(a):
        pub = a.get("published_at", "") or a.get("fetched_at", "") or ""
        return pub if isinstance(pub, str) else ""
    unique.sort(key=sort_key, reverse=True)
    return unique


def _is_news_stale(db) -> bool:
    """Check if the latest news article is older than NEWS_STALE_MINUTES."""
    latest = db.execute_one(
        "SELECT MAX(fetched_at) as last_fetch FROM news_articles"
    )
    if not latest or not latest.get("last_fetch"):
        return True
    try:
        last_dt = datetime.fromisoformat(latest["last_fetch"])
        return datetime.now() - last_dt > timedelta(minutes=NEWS_STALE_MINUTES)
    except (ValueError, TypeError):
        return True


def render():
    """Render the news feed page."""
    st.header("Market News")

    teach_if_enabled("news_sentiment")

    db = get_connection()
    stock_dao = StockDAO()
    user_id = get_current_user_id()
    wl_dao = UserWatchlistDAO()

    # Controls
    ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 1])
    with ctrl1:
        credible_only = st.toggle("Credible Sources Only", value=True,
                                   help="Filter to verified news sources (Reuters, Bloomberg, WSJ, etc.)")
    with ctrl2:
        show_badges = st.toggle("Show Source Badges", value=True)
    with ctrl3:
        refresh = st.button("Refresh All News", type="primary")

    # News freshness indicator
    latest_news = db.execute_one(
        "SELECT MAX(fetched_at) as last_fetch FROM news_articles"
    )
    if latest_news and latest_news.get("last_fetch"):
        try:
            last_dt = datetime.fromisoformat(latest_news["last_fetch"])
            mins_ago = int((datetime.now() - last_dt).total_seconds() / 60)
            if mins_ago < 1:
                freshness = "Just updated"
            elif mins_ago < 60:
                freshness = f"Updated {mins_ago}m ago"
            else:
                freshness = f"Updated at {last_dt.strftime('%I:%M %p')}"
        except (ValueError, TypeError):
            freshness = "Unknown"
    else:
        freshness = "No news data yet"
    st.caption(f"{freshness}  |  Auto-refreshes when older than {NEWS_STALE_MINUTES}m")

    st.divider()

    # Build ticker lists
    portfolio_tickers = []
    holdings = list(db.execute(
        """SELECT DISTINCT ticker FROM portfolio_holdings
           WHERE user_id = ? AND snapshot_date = (
               SELECT MAX(snapshot_date) FROM portfolio_holdings WHERE user_id = ?
           )""",
        (user_id, user_id),
    ))
    portfolio_tickers = [h["ticker"] for h in holdings]

    watchlist_tickers = wl_dao.get_tickers(user_id)

    # Auto-fetch if stale (no button click needed)
    stale = _is_news_stale(db)
    if stale and not refresh:
        refresh = True  # Trigger auto-refresh

    # === TABS ===
    tab_portfolio, tab_market, tab_political, tab_all = st.tabs([
        "Portfolio News", "Market News", "Political & Macro", "All News"
    ])

    # Fetch if refreshing (manual or auto)
    if refresh:
        with st.spinner("Fetching news from credible sources..."):
            progress = st.progress(0)
            all_tickers = list(set(
                portfolio_tickers + watchlist_tickers + MARKET_TICKERS + POLITICAL_TICKERS
            ))
            total = len(all_tickers)
            all_fresh = []
            for i, ticker in enumerate(all_tickers[:30]):  # Cap at 30
                articles = _fetch_yfinance_news(ticker)
                _store_articles(articles)
                all_fresh.extend(articles)
                progress.progress((i + 1) / min(total, 30))
            st.success(f"Fetched {len(all_fresh)} articles from {min(total, 30)} sources")

    # === PORTFOLIO NEWS ===
    with tab_portfolio:
        st.subheader("Your Portfolio")
        if portfolio_tickers:
            st.caption(f"News for: {', '.join(portfolio_tickers[:10])}{'...' if len(portfolio_tickers) > 10 else ''}")

            # Load from DB
            portfolio_articles = []
            for ticker in portfolio_tickers:
                articles = list(db.execute(
                    """SELECT * FROM news_articles
                       WHERE ticker = ? ORDER BY published_at DESC LIMIT 10""",
                    (ticker,),
                ))
                portfolio_articles.extend(articles)

            # If empty, try fetching live
            if not portfolio_articles:
                with st.spinner("Loading portfolio news..."):
                    portfolio_articles = _fetch_and_filter(portfolio_tickers[:10], credible_only)

            if credible_only:
                portfolio_articles = [a for a in portfolio_articles if _is_credible(a.get("source", ""))]

            portfolio_articles = _dedupe_and_sort(portfolio_articles)

            if portfolio_articles:
                for article in portfolio_articles[:30]:
                    _render_article_card(article, show_badges)
            else:
                st.info("No recent credible news for your holdings. Click 'Refresh All News' to fetch latest.")
        else:
            st.info("Add holdings to your portfolio to see personalized news.")

    # === MARKET NEWS ===
    with tab_market:
        st.subheader("Market Headlines")
        st.caption("Broad market news from SPY, QQQ, DIA, and major indices")

        market_articles = []
        for ticker in MARKET_TICKERS:
            articles = list(db.execute(
                """SELECT * FROM news_articles
                   WHERE ticker = ? ORDER BY published_at DESC LIMIT 15""",
                (ticker,),
            ))
            market_articles.extend(articles)

        if not market_articles:
            with st.spinner("Fetching market headlines..."):
                market_articles = _fetch_and_filter(MARKET_TICKERS, credible_only)

        if credible_only:
            market_articles = [a for a in market_articles if _is_credible(a.get("source", ""))]

        market_articles = _dedupe_and_sort(market_articles)

        if market_articles:
            for article in market_articles[:30]:
                _render_article_card(article, show_badges)
        else:
            st.info("No market news cached. Click 'Refresh All News' or add SPY/QQQ to your watchlist.")

    # === POLITICAL & MACRO ===
    with tab_political:
        st.subheader("Political & Macro News")
        st.caption("News affecting gold, bonds, and the dollar - sensitive to geopolitical events")

        political_articles = []
        for ticker in POLITICAL_TICKERS + ["SPY"]:
            articles = list(db.execute(
                """SELECT * FROM news_articles
                   WHERE ticker = ? ORDER BY published_at DESC LIMIT 10""",
                (ticker,),
            ))
            political_articles.extend(articles)

        if not political_articles:
            with st.spinner("Fetching political & macro news..."):
                political_articles = _fetch_and_filter(POLITICAL_TICKERS + ["SPY"], credible_only)

        if credible_only:
            political_articles = [a for a in political_articles if _is_credible(a.get("source", ""))]

        # Filter for political/macro keywords
        political_keywords = [
            "fed", "federal reserve", "interest rate", "inflation", "gdp", "tariff",
            "trade war", "sanctions", "election", "congress", "senate", "president",
            "treasury", "debt ceiling", "fiscal", "monetary", "geopolit", "war",
            "opec", "oil", "energy", "regulation", "antitrust", "tax",
            "china", "europe", "ukraine", "russia", "middle east", "iran",
        ]

        macro_articles = []
        other_articles = []
        for a in political_articles:
            text = (a.get("title", "") + " " + a.get("summary", "")).lower()
            if any(kw in text for kw in political_keywords):
                macro_articles.append(a)
            else:
                other_articles.append(a)

        macro_articles = _dedupe_and_sort(macro_articles)
        other_articles = _dedupe_and_sort(other_articles)

        if macro_articles:
            st.markdown("**Political & Geopolitical**")
            for article in macro_articles[:20]:
                _render_article_card(article, show_badges)
        if other_articles:
            st.markdown("**Other Macro News**")
            for article in other_articles[:10]:
                _render_article_card(article, show_badges)
        if not macro_articles and not other_articles:
            st.info("No political/macro news cached. Click 'Refresh All News' to fetch.")

    # === ALL NEWS ===
    with tab_all:
        st.subheader("All News Feed")

        # Specific stock search
        search_ticker = st.text_input("Search news for a specific ticker", placeholder="NVDA", key="news_search").upper().strip()

        if search_ticker:
            search_articles = list(db.execute(
                """SELECT * FROM news_articles
                   WHERE ticker = ? ORDER BY published_at DESC LIMIT 30""",
                (search_ticker,),
            ))
            if not search_articles:
                with st.spinner(f"Fetching news for {search_ticker}..."):
                    search_articles = _fetch_and_filter([search_ticker], credible_only)

            if credible_only:
                search_articles = [a for a in search_articles if _is_credible(a.get("source", ""))]

            search_articles = _dedupe_and_sort(search_articles)
            if search_articles:
                for article in search_articles[:30]:
                    _render_article_card(article, show_badges)
            else:
                st.info(f"No news found for {search_ticker}.")
        else:
            # Show all cached news
            all_cached = list(db.execute(
                """SELECT * FROM news_articles
                   ORDER BY published_at DESC LIMIT 50"""
            ))

            if credible_only:
                all_cached = [a for a in all_cached if _is_credible(a.get("source", ""))]

            all_cached = _dedupe_and_sort(all_cached)

            if all_cached:
                st.caption(f"Showing {len(all_cached)} articles from credible sources")
                for article in all_cached[:50]:
                    _render_article_card(article, show_badges)
            else:
                st.info("No news cached yet. Click 'Refresh All News' to get started.")

    # === SOURCE TRANSPARENCY ===
    st.divider()
    with st.expander("About Our News Sources"):
        st.markdown("""
        **We only pull from credible, established news organizations:**

        **Tier 1 - Wire Services & Premier Financial Press**
        Reuters, Associated Press, Bloomberg, Wall Street Journal, Financial Times

        **Tier 2 - Major Financial Media**
        CNBC, MarketWatch, Barron's, The Economist, Forbes, Morningstar

        **Tier 3 - Financial Analysis**
        Seeking Alpha, Motley Fool, Yahoo Finance, Benzinga, TipRanks

        **Tier 4 - Political & General News**
        Politico, The Hill, CNN, BBC, NPR, PBS, The Guardian

        News marked **VERIFIED** comes from wire services (Reuters, AP) and top-tier financial press.
        News marked **TRUSTED** comes from established financial media outlets.

        We filter out unverified blogs, social media, and low-credibility sources.
        """)

    # News coverage stats
    st.divider()
    st.subheader("News Coverage Summary")
    all_articles = list(db.execute(
        "SELECT ticker, source, COUNT(*) as cnt FROM news_articles GROUP BY ticker ORDER BY cnt DESC LIMIT 20"
    ))
    if all_articles:
        summary_df = pd.DataFrame([
            {"Ticker": a["ticker"], "Source": a["source"], "Articles": a["cnt"]}
            for a in all_articles
        ])
        st.dataframe(summary_df, width="stretch", hide_index=True)

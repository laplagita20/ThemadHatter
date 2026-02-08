"""Database schema - all CREATE TABLE statements (idempotent)."""

import logging

logger = logging.getLogger("stock_model.schema")

CURRENT_VERSION = 1

TABLES = [
    # --- Phase 1: Foundation ---
    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS stocks (
        ticker TEXT PRIMARY KEY,
        company_name TEXT,
        sector TEXT,
        industry TEXT,
        cik TEXT,
        country TEXT DEFAULT 'US',
        market_cap REAL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1
    )""",

    """CREATE TABLE IF NOT EXISTS app_config (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS data_freshness (
        source TEXT NOT NULL,
        ticker TEXT,
        last_fetched TIMESTAMP,
        next_fetch TIMESTAMP,
        status TEXT DEFAULT 'ok',
        PRIMARY KEY (source, ticker)
    )""",

    # --- Phase 2: Data Collection ---
    """CREATE TABLE IF NOT EXISTS price_history (
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume INTEGER,
        adj_close REAL,
        PRIMARY KEY (ticker, date)
    )""",

    """CREATE TABLE IF NOT EXISTS stock_fundamentals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        pe_ratio REAL,
        forward_pe REAL,
        pb_ratio REAL,
        ps_ratio REAL,
        ev_ebitda REAL,
        peg_ratio REAL,
        profit_margin REAL,
        operating_margin REAL,
        gross_margin REAL,
        roe REAL,
        roa REAL,
        roic REAL,
        revenue_growth REAL,
        earnings_growth REAL,
        debt_to_equity REAL,
        current_ratio REAL,
        quick_ratio REAL,
        free_cash_flow REAL,
        dividend_yield REAL,
        beta REAL,
        market_cap REAL,
        enterprise_value REAL,
        raw_json TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS sec_filings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        cik TEXT,
        filing_type TEXT NOT NULL,
        filed_date TEXT,
        accession_number TEXT UNIQUE,
        primary_document TEXT,
        description TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS sec_financial_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        metric TEXT NOT NULL,
        period_end TEXT NOT NULL,
        period_type TEXT,
        value REAL,
        unit TEXT,
        fiscal_year INTEGER,
        fiscal_quarter INTEGER,
        filed_date TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, metric, period_end, period_type)
    )""",

    """CREATE TABLE IF NOT EXISTS insider_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        filer_name TEXT,
        filer_title TEXT,
        transaction_date TEXT,
        transaction_type TEXT,
        shares REAL,
        price_per_share REAL,
        total_value REAL,
        shares_owned_after REAL,
        accession_number TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS hedge_fund_holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fund_cik TEXT NOT NULL,
        fund_name TEXT,
        ticker TEXT NOT NULL,
        shares REAL,
        value REAL,
        report_date TEXT,
        filed_date TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS macro_indicators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_id TEXT NOT NULL,
        series_name TEXT,
        date TEXT NOT NULL,
        value REAL,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(series_id, date)
    )""",

    """CREATE TABLE IF NOT EXISTS news_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        summary TEXT,
        source TEXT NOT NULL,
        url TEXT,
        published_at TIMESTAMP,
        ticker TEXT,
        credibility_weight REAL DEFAULT 0.7,
        sentiment_score REAL,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(url)
    )""",

    """CREATE TABLE IF NOT EXISTS geopolitical_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_date TEXT,
        source_country TEXT,
        target_country TEXT,
        event_type TEXT,
        goldstein_scale REAL,
        tone REAL,
        num_mentions INTEGER,
        num_sources INTEGER,
        risk_score REAL,
        description TEXT,
        url TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS portfolio_holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        quantity REAL NOT NULL,
        average_cost REAL,
        current_price REAL,
        market_value REAL,
        unrealized_pl REAL,
        unrealized_pl_pct REAL,
        sector TEXT,
        snapshot_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS portfolio_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL,
        total REAL,
        executed_at TIMESTAMP,
        order_type TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_equity REAL,
        cash REAL,
        total_pl REAL,
        total_pl_pct REAL,
        num_positions INTEGER
    )""",

    # --- Alpha Vantage ---
    """CREATE TABLE IF NOT EXISTS alpha_vantage_overview (
        ticker TEXT PRIMARY KEY,
        analyst_target REAL,
        beta REAL,
        revenue_growth_yoy REAL,
        earnings_growth_yoy REAL,
        profit_margin REAL,
        operating_margin REAL,
        roe REAL,
        roa REAL,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS earnings_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        fiscal_date TEXT NOT NULL,
        reported_date TEXT,
        reported_eps REAL,
        estimated_eps REAL,
        surprise REAL,
        surprise_pct REAL,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, fiscal_date)
    )""",

    # --- Phase 3: Analysis ---
    """CREATE TABLE IF NOT EXISTS analysis_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        analyzer_name TEXT NOT NULL,
        score REAL NOT NULL,
        confidence REAL NOT NULL,
        signal TEXT NOT NULL,
        factors_json TEXT,
        summary TEXT,
        analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS macro_regime (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        growth_regime TEXT,
        inflation_regime TEXT,
        rate_regime TEXT,
        risk_regime TEXT,
        composite_regime TEXT,
        details_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS sector_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sector_etf TEXT NOT NULL,
        date TEXT NOT NULL,
        return_1w REAL,
        return_1m REAL,
        return_3m REAL,
        return_6m REAL,
        return_1y REAL,
        relative_strength REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(sector_etf, date)
    )""",

    # --- Phase 4: Decision Engine ---
    """CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        action TEXT NOT NULL,
        composite_score REAL,
        confidence REAL,
        position_size_pct REAL,
        stop_loss_pct REAL,
        target_price REAL,
        time_horizon TEXT,
        reasoning_json TEXT,
        bull_case TEXT,
        bear_case TEXT,
        risk_warnings TEXT,
        analysis_breakdown_json TEXT,
        decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        outcome_1w REAL,
        outcome_1m REAL,
        outcome_3m REAL,
        outcome_6m REAL
    )""",

    """CREATE TABLE IF NOT EXISTS risk_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name TEXT NOT NULL UNIQUE,
        rule_value REAL NOT NULL,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS portfolio_risk (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        portfolio_beta REAL,
        portfolio_var_95 REAL,
        max_position_pct REAL,
        max_sector_pct REAL,
        num_sectors INTEGER,
        concentration_hhi REAL,
        details_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # --- Phase 5: Portfolio ---
    """CREATE TABLE IF NOT EXISTS benchmark_prices (
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        close REAL,
        PRIMARY KEY (ticker, date)
    )""",

    """CREATE TABLE IF NOT EXISTS rebalance_recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        action TEXT NOT NULL,
        current_weight REAL,
        target_weight REAL,
        shares_to_trade REAL,
        reason TEXT,
        priority INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS performance_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        total_return REAL,
        annualized_return REAL,
        sharpe_ratio REAL,
        sortino_ratio REAL,
        max_drawdown REAL,
        alpha REAL,
        beta REAL,
        benchmark TEXT DEFAULT 'SPY',
        calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # --- Phase 6: Learning ---
    """CREATE TABLE IF NOT EXISTS decision_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id INTEGER REFERENCES decisions(id),
        ticker TEXT NOT NULL,
        snapshot_data_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS decision_outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id INTEGER REFERENCES decisions(id),
        ticker TEXT NOT NULL,
        decided_at TIMESTAMP,
        price_at_decision REAL,
        price_1w REAL,
        price_1m REAL,
        price_3m REAL,
        price_6m REAL,
        return_1w REAL,
        return_1m REAL,
        return_3m REAL,
        return_6m REAL,
        action_was_correct INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS analyzer_accuracy (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        analyzer_name TEXT NOT NULL,
        period TEXT NOT NULL,
        total_predictions INTEGER DEFAULT 0,
        correct_direction INTEGER DEFAULT 0,
        direction_accuracy REAL,
        mean_score_when_correct REAL,
        mean_score_when_wrong REAL,
        information_coefficient REAL,
        calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(analyzer_name, period)
    )""",

    """CREATE TABLE IF NOT EXISTS weight_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        weights_json TEXT NOT NULL,
        reason TEXT,
        approved INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_price_history_ticker ON price_history(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(date)",
    "CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker ON stock_fundamentals(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_sec_filings_ticker ON sec_filings(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_sec_filings_type ON sec_filings(filing_type)",
    "CREATE INDEX IF NOT EXISTS idx_sec_financial_ticker ON sec_financial_data(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_articles(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles(published_at)",
    "CREATE INDEX IF NOT EXISTS idx_analysis_ticker ON analysis_results(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_analysis_analyzer ON analysis_results(analyzer_name)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_ticker ON decisions(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_date ON decisions(decided_at)",
    "CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON portfolio_holdings(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_macro_series ON macro_indicators(series_id)",
    "CREATE INDEX IF NOT EXISTS idx_geopolitical_date ON geopolitical_events(event_date)",
    "CREATE INDEX IF NOT EXISTS idx_earnings_ticker ON earnings_history(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_history(fiscal_date)",
]


def initialize_database(db_connection):
    """Create all tables and indexes if they don't exist."""
    with db_connection.connect() as conn:
        for table_sql in TABLES:
            conn.execute(table_sql)

        for index_sql in INDEXES:
            conn.execute(index_sql)

        # Set schema version
        existing = conn.execute(
            "SELECT MAX(version) as v FROM schema_version"
        ).fetchone()
        if existing is None or existing["v"] is None or existing["v"] < CURRENT_VERSION:
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (CURRENT_VERSION,),
            )

    logger.info("Database schema initialized (version %d)", CURRENT_VERSION)

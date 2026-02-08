# The Mad Hatter - AI-Powered Portfolio Management System

A professional-grade stock analysis and portfolio management system that collects data from 8+ free sources, runs 6 independent analysis engines, and produces justified BUY/HOLD/SELL decisions with full reasoning chains.

Built to run like a small capital investment company.

## What It Does

- **Collects data** from Yahoo Finance, SEC EDGAR, FRED, Finnhub, Alpha Vantage, 11 RSS news feeds, and GDELT geopolitical events
- **Analyzes stocks** across 6 dimensions: Technical, Fundamental, Macroeconomic, Sentiment, Geopolitical, and Sector
- **Produces decisions** with composite scores (-100 to +100), confidence levels, position sizing, stop-losses, and full reasoning
- **Tracks performance** with outcome tracking, backtesting, and self-improving weight optimization
- **Manages portfolios** with risk rules, sector concentration limits, and rebalancing recommendations

## Scoring Model

Each stock is scored from **-100 to +100** across 6 analyzers with confidence-adjusted weighting:

| Analyzer | Weight | Data Source |
|----------|--------|-------------|
| Fundamental | 30% | Yahoo Finance, SEC EDGAR XBRL, Alpha Vantage |
| Technical | 20% | Price/volume data, 12+ indicators (SMA, MACD, RSI, Bollinger, etc.) |
| Macroeconomic | 15% | FRED (GDP, CPI, Fed Rate, yield curve, VIX, unemployment) |
| Sentiment | 10% | NLP on 11+ news sources, credibility-weighted, material event detection |
| Sector | 10% | Sector ETF rotation, relative strength, business cycle positioning |
| Geopolitical | 5% | GDELT events, military/trade/regulatory risk scoring |

**Decision thresholds:**
- Score >= +50: STRONG BUY
- Score >= +20: BUY
- Score > -20: HOLD
- Score <= -20: SELL
- Score <= -50: STRONG SELL

Low confidence (< 30%) forces HOLD regardless of score.

## Quick Start

```bash
# Clone
git clone https://github.com/laplagita20/ThemadHatter.git
cd ThemadHatter

# Install dependencies
pip install -r requirements.txt

# Set up API keys (copy and fill in your keys)
cp .env.example .env
# Edit .env with your FRED, Finnhub, Alpha Vantage keys

# Add stocks to watchlist
python main.py watchlist --add AAPL MSFT NVDA

# Collect data
python main.py collect --source yahoo --ticker AAPL
python main.py collect --source news --ticker AAPL
python main.py collect --source fred
python main.py collect --source sec --ticker AAPL
python main.py collect --source alpha_vantage --ticker AAPL

# Run full analysis
python main.py analyze AAPL

# Backtest a strategy
python main.py backtest --tickers AAPL,MSFT --start 2024-01-01
```

## All CLI Commands

| Command | Description |
|---------|-------------|
| `analyze <TICKER>` | Full 6-analyzer analysis with decision |
| `analyze-portfolio` | Analyze all holdings |
| `collect --source <SOURCE> [--ticker <TICKER>]` | Collect data (yahoo, sec, fred, news, gdelt, alpha_vantage, all) |
| `watchlist --add/--remove <TICKERS>` | Manage stock watchlist |
| `import-portfolio` | Import holdings from Robinhood |
| `portfolio-status` | Show current portfolio state |
| `performance --period <1M/3M/6M/1Y>` | Performance metrics vs benchmarks |
| `rebalance` | Generate rebalancing recommendations |
| `backtest --tickers <T1,T2> --start <YYYY-MM-DD>` | Historical strategy replay |
| `track-outcomes` | Update outcome tracking for past decisions |
| `accuracy-report` | Show per-analyzer predictive accuracy |
| `optimize-weights` | Run weight optimization (needs 50+ decisions) |

## API Keys (Free)

| Service | Get Key At | What It Provides |
|---------|-----------|------------------|
| FRED | https://fred.stlouisfed.org/docs/api/api_key.html | 15 macro indicators (GDP, CPI, rates, VIX, etc.) |
| Finnhub | https://finnhub.io/register | Ticker-specific news articles |
| Alpha Vantage | https://www.alphavantage.co/support/#api-key | Earnings history, analyst targets, company overview |
| SEC EDGAR | No key needed (just name + email in User-Agent) | 10-K, 10-Q, 8-K filings, XBRL financial data |

Yahoo Finance, RSS news feeds, and GDELT require no API keys.

## Project Structure

```
stock_model/
├── main.py                  # CLI entry point
├── config/                  # Settings, logging
├── database/                # SQLite with WAL mode, schema, DAOs
├── collectors/              # 8 data collectors with rate limiting & caching
│   ├── yahoo_finance.py     # Price, fundamentals
│   ├── sec_edgar.py         # SEC filings, XBRL
│   ├── fred_collector.py    # Federal Reserve economic data
│   ├── news_collector.py    # 11 RSS feeds + Finnhub API
│   ├── alpha_vantage.py     # Earnings, analyst targets
│   ├── gdelt_collector.py   # Geopolitical events
│   ├── robinhood_collector.py
│   └── scheduler.py         # APScheduler orchestration
├── analysis/                # 6 independent analyzers
│   ├── technical.py         # 12+ technical indicators
│   ├── fundamental.py       # Valuation, profitability, growth, balance sheet
│   ├── macroeconomic.py     # Regime detection, sector sensitivity
│   ├── sentiment.py         # NLP sentiment, credibility weighting
│   ├── geopolitical.py      # GDELT risk scoring
│   └── sector.py            # Sector rotation, relative strength
├── engine/                  # Decision engine, risk management
├── portfolio/               # Portfolio manager, performance, rebalancer
├── learning/                # Backtester, outcome tracker, weight optimizer
├── utils/                   # Rate limiter, cache, console helpers
└── data/                    # SQLite DB, cache, logs (gitignored)
```

## How the Model Self-Improves

The learning system closes the feedback loop:

1. **Decision Logger** - Snapshots every decision with full data state
2. **Outcome Tracker** - Measures actual returns at 1 week, 1 month, 3 months, 6 months
3. **Accuracy Tracker** - Per-analyzer direction accuracy and information coefficient
4. **Weight Optimizer** - Adjusts analyzer weights based on predictive accuracy
   - Only runs after 50+ decisions with outcomes
   - Max weight change: 5% per optimization
   - 70/30 smoothing (conservative adjustment)
   - No weight below 2%

## Tech Stack

- Python 3.12+
- SQLite (WAL mode) for persistence
- yfinance, fredapi, finnhub-python for data
- ta (Technical Analysis) library for indicators
- TextBlob for NLP sentiment
- feedparser for RSS news
- APScheduler for automated collection

## License

Private project. Not for redistribution.

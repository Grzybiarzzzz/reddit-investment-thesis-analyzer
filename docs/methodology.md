# Research methodology

I investigate whether better-supported investment arguments in Reddit discussions correspond to stronger subsequent stock returns. The analysis combines text collection, per-stock LLM assessments, and exploratory comparisons with market and sector benchmarks.

## Dataset and coverage

The database contains 4,046 posts and 31,668 comments from eight investing communities. There are 7,632 per-stock assessments across 5,960 source items, with scoring records dated 12 March–4 April 2026. Some source discussions predate that period.

The tracked sample contains 67 stocks, with 62 nominal seven-day observations and 50 fourteen-day observations. There are no 30- or 90-day outcomes. Multiple assessments can come from one post, and repeated mentions of a stock are not independent investment outcomes.

Only part of the collected text has recorded assessments. Processing status alone does not establish whether an item received an LLM assessment; assessment coverage is counted from the analysis records.

## Argument assessment and stock selection

Ticker recognition and financial-context filters identify candidate text. An LLM evaluates each stock thesis separately for reasoning, specificity, novelty, and credibility, alongside bullish, bearish, or neutral sentiment. These scores represent judgments about the argument, not verified author expertise or factual accuracy.

Tracking eligibility depends on mention frequency and average quality within a lookback window. The configured defaults are five mentions, an average score of at least 65, and a seven-day lookback. The dataset includes discoveries made under different settings; configuration and model versions are not recorded per assessment.

Comparisons use the quality score and mention count stored at discovery. Discovery sentiment is derived from the same eligible mentions, with ties classified as neutral. The included sample has no recorded aggregate discovery sentiment. The separate [directional report](directional-results.md) reconstructs its underlying seven-day assessment windows and verifies their saved counts and mean scores. Later discussions are excluded.

## Timing and returns

Checkpoints have nominal calendar-day horizons of 7, 14, 30, and 90 days. The tracker fetches a current quote when a checkpoint is due. A delayed run can therefore measure a later price, and several overdue checkpoints can be populated during the same run.

The observation-time field records UTC fetch completion when available, not the exchange quote timestamp. Fetch times are unavailable in the included sample, which limits comparisons at exact holding periods.

Returns measure price changes from discovery and exclude trading costs. “Excess vs SPY” is the stock's percentage return minus SPY's percentage return, expressed in percentage points. It is not risk-adjusted alpha. Benchmark comparisons require available stock and benchmark prices.

Portfolio insights use the selected nominal horizon. Score groups count each discovery once, using its stored score. Tracked-stock summaries use each stock's latest available observation and may mix horizons.

## Interpretation

The results describe a small, selected sample. They do not establish that higher argument scores predict stronger returns. Selection thresholds, correlated stocks and discussions, uncertain observation timing, and unvalidated model scores limit inference.

Score-threshold comparisons are exploratory: selecting a threshold using these same outcomes is not an independent evaluation. A follow-up study would specify selection rules and trading-session horizons in advance, retain model and quote provenance, compare scores with human assessments, and evaluate a separate period.

## Historical price evaluation

The [historical outcome report](historical-results.md) compares saved discovery quotes with daily closing prices at matched stock and benchmark sessions. It documents split adjustments, ticker aliases, coverage, and reproducible checkpoint exports. These historical returns are separate from the dashboard’s recorded quote observations.

## Directional argument evaluation

The [directional outcome report](directional-results.md) reconstructs each seven-day discovery window, verifies its saved count and mean score, and evaluates bullish and bearish argument groups separately. Neutral assessments are excluded from directional outcomes, and combined summaries give each stock equal total weight.

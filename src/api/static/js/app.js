/* ==========================================================================
   RedditStockMarket — Main Application JS
   Single-page dashboard: auth, routing, data fetching, page renderers.
   ========================================================================== */

(function () {
  'use strict';

  // -----------------------------------------------------------------------
  // 1. Constants & State
  // -----------------------------------------------------------------------

  const CACHE_TTL = 300000; // 5 minutes
  const CHECKPOINT_DAYS = [7, 14, 30, 90];
  // Mirrors SUBREDDITS in config/settings.py.
  const SUBREDDITS = ['wallstreetbets', 'stocks', 'investing', 'ValueInvesting', 'StockMarket',
    'SecurityAnalysis', 'smallstreetbets', 'pennystocks', 'Undervalued'];
  const ROUTES = ['dashboard', 'feed', 'tracked', 'portfolio', 'analytics', 'project'];

  // -----------------------------------------------------------------------
  // 1b. Theme Management
  // -----------------------------------------------------------------------

  function getTheme() {
    return localStorage.getItem('theme') || 'terminal';
  }

  function setTheme(theme) {
    localStorage.setItem('theme', theme);
    if (theme === 'terminal') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }
    // Update toggle button label
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.textContent = theme === 'terminal' ? 'broadsheet' : 'terminal';
    }
    // Update chart colors for new theme
    if (typeof window.updateChartTheme === 'function') {
      window.updateChartTheme(theme);
    }
  }

  async function toggleTheme() {
    const current = getTheme();
    const next = current === 'terminal' ? 'broadsheet' : 'terminal';
    setTheme(next);
    // Re-render current page to apply layout changes
    invalidateCache();
    await route();
    // Ensure button label is correct after re-render
    var btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = next === 'terminal' ? 'broadsheet' : 'terminal';
  }

  function isBroadsheet() {
    return getTheme() === 'broadsheet';
  }

  const cache = {};
  const feedState = {
    page: 1,
    sentiment: '',
    subreddit: '',
    ticker: '',
    min_score: 0,
    sort: 'newest',
  };
  const trackedState = { status: 'all', sortBy: 'discovered_at', sortDir: 'desc' };
  const portfolioState = { min_score: 0, min_mentions: 0, ticker: '', sentiment: '', sortBy: 'return_pct', sortDir: 'desc', checkpoint: '7', discovered_after: '', discovered_before: '', _initialized: false };

  // -----------------------------------------------------------------------
  // 2. Utility Functions
  // -----------------------------------------------------------------------

  function escapeHtml(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
  }

  function formatPercent(n) {
    if (n == null || isNaN(n)) return { text: '--', cls: '' };
    const val = Number(n);
    const text = (val >= 0 ? '+' : '') + val.toFixed(1) + '%';
    const cls = val >= 0 ? 'positive' : 'negative';
    return { text, cls };
  }

  function formatMoney(n) {
    if (n == null || isNaN(n)) return '--';
    const val = Number(n);
    const sign = val >= 0 ? '+$' : '-$';
    return sign + Math.abs(val).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function formatPrice(n) {
    if (n == null || isNaN(n)) return '--';
    return '$' + Number(n).toFixed(2);
  }

  function timeAgo(dateStr) {
    if (!dateStr) return '';
    const now = Date.now();
    const then = new Date(dateStr).getTime();
    const diff = now - then;
    if (isNaN(diff)) return '';
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + 'm ago';
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs + 'h ago';
    const days = Math.floor(hrs / 24);
    if (days < 30) return days + 'd ago';
    const months = Math.floor(days / 30);
    return months + 'mo ago';
  }

  function sentimentBadge(s) {
    const sentiment = (s || 'neutral').toLowerCase();
    const label = sentiment === 'bull' ? 'BULL' : sentiment === 'bear' ? 'BEAR' : sentiment === 'unknown' ? 'UNKNOWN' : 'NEUTRAL';
    return `<span class="sentiment-badge ${escapeHtml(sentiment)}">${label}</span>`;
  }

  function checkpointDots(stock) {
    const checkpoints = stock.checkpoints || {};
    const done = stock.checkpoints_done || [];
    let html = '<div class="checkpoint-dots">';
    for (const d of CHECKPOINT_DAYS) {
      let cls = '';
      if (checkpoints[d] != null || done.indexOf(d) !== -1) {
        cls = 'done';
      } else if (stock.status === 'active') {
        cls = 'current';
        // Only the first unfinished one is "current"
        html += `<div class="checkpoint-dot ${cls}" title="${d}d"></div>`;
        // remaining are empty
        const idx = CHECKPOINT_DAYS.indexOf(d);
        for (let i = idx + 1; i < CHECKPOINT_DAYS.length; i++) {
          const dd = CHECKPOINT_DAYS[i];
          const ddDone = (checkpoints[dd] != null || done.indexOf(dd) !== -1);
          html += `<div class="checkpoint-dot${ddDone ? ' done' : ''}" title="${dd}d"></div>`;
        }
        html += '</div>';
        return html;
      }
      html += `<div class="checkpoint-dot ${cls}" title="${d}d"></div>`;
    }
    html += '</div>';
    return html;
  }

  function scoreBarHtml(score) {
    const s = Number(score) || 0;
    const fillClass = s >= 70 ? '' : s >= 40 ? 'medium' : 'low';
    return `<div class="score-bar">
      <div class="score-bar-track"><div class="score-bar-fill ${fillClass}" style="width:${s}%"></div></div>
      <span class="score-bar-value">${s}</span>
    </div>`;
  }

  // -----------------------------------------------------------------------
  // 3. Auth Layer
  // -----------------------------------------------------------------------

  function getApiKey() {
    return localStorage.getItem('api_key') || '';
  }

  function showAuth() {
    const overlay = document.getElementById('auth-overlay');
    if (overlay) overlay.classList.remove('hidden');
  }

  function hideAuth() {
    const overlay = document.getElementById('auth-overlay');
    if (overlay) overlay.classList.add('hidden');
  }

  function logout() {
    localStorage.removeItem('api_key');
    showAuth();
  }

  function setupAuthForm() {
    const form = document.getElementById('auth-form');
    if (!form) return;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      const input = form.querySelector('input[type="password"], input[type="text"], input[name="api_key"]');
      const errorEl = form.querySelector('.auth-error');
      if (!input) return;
      const key = input.value.trim();
      if (!key) {
        if (errorEl) errorEl.textContent = 'API key is required.';
        return;
      }
      localStorage.setItem('api_key', key);
      if (errorEl) errorEl.textContent = '';
      hideAuth();
      route();
    });
  }

  // -----------------------------------------------------------------------
  // 4. Data Fetching
  // -----------------------------------------------------------------------

  async function api(path, options) {
    const opts = Object.assign({ method: 'GET' }, options || {});
    const headers = Object.assign({}, opts.headers || {});
    const key = getApiKey();
    if (key) headers['X-API-Key'] = key;
    if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    opts.headers = headers;

    const resp = await fetch(path, opts);
    if (resp.status === 401) {
      showAuth();
      throw new Error('Unauthorized');
    }
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`HTTP ${resp.status}: ${text}`);
    }
    return resp.json();
  }

  async function cachedFetch(path) {
    const now = Date.now();
    if (cache[path] && (now - cache[path].timestamp) < CACHE_TTL) {
      return cache[path].data;
    }
    const data = await api(path);
    cache[path] = { data, timestamp: now };
    return data;
  }

  function invalidateCache(prefix) {
    for (const key of Object.keys(cache)) {
      if (!prefix || key.startsWith(prefix)) {
        delete cache[key];
      }
    }
  }

  // -----------------------------------------------------------------------
  // 5. Loading & Error Helpers
  // -----------------------------------------------------------------------

  function showLoading() {
    const content = document.getElementById('content');
    if (content) {
      content.innerHTML = `<div class="loading-block">
        <div class="loading">Loading data</div>
      </div>`;
      content.classList.add('loading');
    }
  }

  function showError(err) {
    const content = document.getElementById('content');
    if (content) {
      content.classList.remove('loading');
      content.innerHTML = `<div class="error-panel" style="margin:24px;">
        <div class="error-header">Request Failed</div>
        <div class="error-message">${escapeHtml(err.message || String(err))}</div>
      </div>`;
    }
  }

  // -----------------------------------------------------------------------
  // 6. Hash Router
  // -----------------------------------------------------------------------

  function buildCmdText(page) {
    switch (page) {
      case 'dashboard':
        return 'render --page=dashboard --refresh=auto';
      case 'feed': {
        let cmd = 'query --feed --sort=' + feedState.sort;
        if (feedState.subreddit) cmd += ' --sub=' + feedState.subreddit;
        if (feedState.sentiment) cmd += ' --sentiment=' + feedState.sentiment;
        if (feedState.ticker) cmd += ' --ticker=' + feedState.ticker;
        if (feedState.min_score > 0) cmd += ' --min-score=' + feedState.min_score;
        cmd += ' --page=' + feedState.page;
        return cmd;
      }
      case 'tracked':
        return 'track --list --status=' + trackedState.status;
      case 'portfolio': {
        let cmd = 'portfolio --simulate --checkpoint=' + portfolioState.checkpoint;
        if (portfolioState.min_score > 0) cmd += ' --min-score=' + portfolioState.min_score;
        if (portfolioState.min_mentions > 0) cmd += ' --min-mentions=' + portfolioState.min_mentions;
        if (portfolioState.ticker) cmd += ' --ticker=' + portfolioState.ticker;
        return cmd;
      }
      case 'analytics':
        return 'analyze --metrics --charts';
      case 'project':
        return 'cat --readme --about';
      default:
        return '';
    }
  }

  function getPage() {
    const hash = (location.hash || '').replace(/^#\/?/, '');
    return ROUTES.indexOf(hash) !== -1 ? hash : 'dashboard';
  }

  function setActiveTab(page) {
    document.querySelectorAll('.nav-tab').forEach(function (tab) {
      const tabPage = tab.getAttribute('data-page');
      if (tabPage === page) {
        tab.classList.add('active');
      } else {
        tab.classList.remove('active');
      }
    });
  }

  function setCmdText(page) {
    const el = document.getElementById('cmd-text');
    if (el) el.textContent = buildCmdText(page);
  }

  async function route() {
    const page = getPage();
    setActiveTab(page);
    setCmdText(page);
    showLoading();
    try {
      switch (page) {
        case 'dashboard': await renderDashboard(); break;
        case 'feed': await renderFeed(); break;
        case 'tracked': await renderTracked(); break;
        case 'portfolio': await renderPortfolio(); break;
        case 'analytics': await renderAnalytics(); break;
        case 'project': renderProject(); break;
      }
    } catch (err) {
      showError(err);
    }
  }

  function setupNav() {
    document.querySelectorAll('.nav-tab').forEach(function (tab) {
      tab.addEventListener('click', function (e) {
        e.preventDefault();
        const page = tab.getAttribute('data-page');
        if (page) location.hash = '#' + page;
      });
    });
    window.addEventListener('hashchange', route);
  }

  // -----------------------------------------------------------------------
  // 7. Page Renderers
  // -----------------------------------------------------------------------

  // ---- Dashboard --------------------------------------------------------

  function updateTickerStrip(tickers) {
    const strip = document.getElementById('ticker-strip');
    if (!strip) return;
    if (!tickers || tickers.length === 0) {
      strip.innerHTML = '';
      return;
    }
    let html = '';
    for (const t of tickers) {
      const score = Number(t.avg_score) || 0;
      const cls = score >= 60 ? 'up' : 'down';
      html += `<div class="ticker-strip-item">
        <span class="symbol">${escapeHtml(t.ticker)}</span>
        <span class="${cls}">Score ${escapeHtml(t.avg_score)}</span>
      </div>`;
    }
    strip.innerHTML = html;
  }

  async function renderDashboard() {
    const data = await cachedFetch('/api/dashboard');
    const content = document.getElementById('content');
    if (!content) return;

    const kpis = data.kpis || {};
    // Counts are for the latest day with data, which is not today for a frozen snapshot.
    const latestDay = data.as_of ? String(data.as_of).slice(0, 10) : null;
    const alphaFmt = formatPercent(kpis.avg_alpha_30d);
    const winRateVal = kpis.win_rate == null ? null : kpis.win_rate * 100;
    const winRateCls = winRateVal >= 50 ? 'green' : 'red';
    const avgRetFmt = formatPercent(kpis.avg_return);
    const stocks = data.active_stocks || [];
    const feed = data.recent_feed || [];
    const tickers = data.top_tickers || [];
    const bestPick = kpis.best_pick;
    const worstPick = kpis.worst_pick;

    // Update ticker strip for broadsheet theme
    updateTickerStrip(tickers);

    let html = `
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">Win Rate</div>
        <div class="stat-value ${winRateCls}">${winRateVal == null ? "--" : escapeHtml(winRateVal.toFixed(1)) + "%"}</div>
        <div class="stat-sub">${escapeHtml(kpis.wins)}/${escapeHtml(kpis.total_with_data)} beat SPY</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Excess vs SPY (7d)</div>
        <div class="stat-value ${alphaFmt.cls === 'positive' ? 'green' : 'red'}">${escapeHtml(alphaFmt.text)}</div>
        <div class="stat-sub">vs SPY benchmark</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Avg Return</div>
        <div class="stat-value ${avgRetFmt.cls === 'positive' ? 'green' : 'red'}">${escapeHtml(avgRetFmt.text)}</div>
        <div class="stat-sub">${escapeHtml(kpis.total_with_data)} stocks w/ data</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Tracked</div>
        <div class="stat-value cyan">${escapeHtml(kpis.tracked_count)}</div>
        <div class="stat-sub">${escapeHtml(kpis.active_count)} active</div>
      </div>
    </div>

    <div class="stats-row stats-row-secondary">
      <div class="stat-card stat-card-sm">
        <div class="stat-label">Best Pick</div>
        <div class="stat-value green">${bestPick ? escapeHtml(bestPick.ticker) : '--'}</div>
        <div class="stat-sub">${bestPick ? formatPercent(bestPick.return_pct).text : ''}</div>
      </div>
      <div class="stat-card stat-card-sm">
        <div class="stat-label">Worst Pick</div>
        <div class="stat-value red">${worstPick ? escapeHtml(worstPick.ticker) : '--'}</div>
        <div class="stat-sub">${worstPick ? formatPercent(worstPick.return_pct).text : ''}</div>
      </div>
      <div class="stat-card stat-card-sm">
        <div class="stat-label">Latest Scrape Day</div>
        <div class="stat-value amber">${escapeHtml(kpis.posts_today + (kpis.comments_today || 0))}</div>
        <div class="stat-sub">${escapeHtml(kpis.posts_today)} posts · ${escapeHtml(kpis.comments_today || 0)} comments</div>
      </div>
      <div class="stat-card stat-card-sm">
        <div class="stat-label">Scored (Latest Day)</div>
        <div class="stat-value purple">${escapeHtml(kpis.scored_today)}</div>
        <div class="stat-sub">${latestDay ? escapeHtml(latestDay) : 'LLM analyzed'}</div>
      </div>
    </div>

    <div class="main">
      <!-- Panel 1: Active tracked stocks -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Tracked Stocks</span>
          <span class="panel-badge live">Live</span>
        </div>
        <div class="panel-body">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Ticker</th><th>Entry</th><th>Return</th><th>Excess vs SPY</th><th>Checkpoints</th>
              </tr></thead>
              <tbody>`;

    if (stocks.length === 0) {
      html += '<tr><td colspan="5" class="text-muted text-center">No tracked stocks yet</td></tr>';
    }
    for (const s of stocks) {
      const ret = formatPercent(s.return_pct);
      const alpha = formatPercent(s.alpha_pct);
      html += `<tr>
        <td class="ticker">${escapeHtml(s.ticker)}</td>
        <td>${formatPrice(s.discovery_price)}</td>
        <td class="${ret.cls}">${escapeHtml(ret.text)}</td>
        <td class="${alpha.cls}">${escapeHtml(alpha.text)}</td>
        <td>${checkpointDots(s)}</td>
      </tr>`;
    }

    html += `</tbody></table></div></div></div>

      <!-- Panel 2: Performance chart -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Performance</span>
          <span class="panel-badge">30d</span>
        </div>
        <div class="panel-body">
          <div class="chart-area"><canvas id="performance-chart"></canvas></div>
        </div>
      </div>

      <!-- Panel 3: Recent feed -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Recent Signals</span>
          <span class="panel-badge">Latest</span>
        </div>
        <div class="panel-body">`;

    if (feed.length === 0) {
      html += '<div class="text-muted text-center p-2">No scored posts yet</div>';
    }
    for (const item of feed) {
      html += `<div class="feed-item">
        <div class="feed-meta">
          ${sentimentBadge(item.sentiment)}
          <span class="feed-sub">r/${escapeHtml(item.subreddit || '?')}</span>
          <span class="feed-time">${timeAgo(item.analyzed_at)}</span>
        </div>
        <div class="feed-title">${escapeHtml((item.title || '').substring(0, 80))}</div>
        <div class="feed-scores">
          <span>Score: <strong>${escapeHtml(item.overall_score)}</strong></span>
          <span>R: ${escapeHtml(item.reasoning_score)}</span>
          <span>S: ${escapeHtml(item.specificity_score)}</span>
          <span>N: ${escapeHtml(item.novelty_score)}</span>
          <span>C: ${escapeHtml(item.credibility_score)}</span>
        </div>
      </div>`;
    }

    html += `</div></div>

      <!-- Panel 4: Top tickers -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Top Tickers</span>
          <span class="panel-badge">7d</span>
        </div>
        <div class="panel-body">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Ticker</th><th>Mentions</th><th>Sentiment</th><th>Score</th>
              </tr></thead>
              <tbody>`;

    if (tickers.length === 0) {
      html += '<tr><td colspan="4" class="text-muted text-center">No data</td></tr>';
    }
    for (const t of tickers) {
      html += `<tr>
        <td class="ticker">${escapeHtml(t.ticker)}</td>
        <td>${escapeHtml(t.mention_count)}</td>
        <td>${sentimentBadge(t.dominant_sentiment)}</td>
        <td>${scoreBarHtml(t.avg_score)}</td>
      </tr>`;
    }

    html += `</tbody></table></div></div></div>
    </div>`;

    content.classList.remove('loading');
    content.innerHTML = html;

    // Update topbar stats
    const dbStats = document.getElementById('db-stats');
    if (dbStats) {
      dbStats.textContent = `${kpis.tracked_count} tracked / ${kpis.posts_today} posts / ${kpis.comments_today || 0} comments on ${latestDay || 'latest day'}`;
    }

    // Defer chart rendering to next frame so DOM layout is complete
    requestAnimationFrame(() => {
      if (typeof window.renderPerformanceChart === 'function') {
        window.renderPerformanceChart('performance-chart', stocks);
      }
    });
  }

  // ---- Feed -------------------------------------------------------------

  async function renderFeed() {
    setCmdText('feed');
    const params = new URLSearchParams();
    params.set('page', feedState.page);
    params.set('sort', feedState.sort);
    if (feedState.sentiment) params.set('sentiment', feedState.sentiment);
    if (feedState.subreddit) params.set('subreddit', feedState.subreddit);
    if (feedState.ticker) params.set('ticker', feedState.ticker);
    if (feedState.min_score > 0) params.set('min_score', feedState.min_score);

    const data = await api('/api/feed?' + params.toString());
    const content = document.getElementById('content');
    if (!content) return;

    let html = `
    <div class="filter-bar">
      <label>Sub</label>
      <select id="filter-subreddit">
        <option value="">All</option>
        ${SUBREDDITS.map(function (name) {
          return `<option value="${name}" ${feedState.subreddit === name ? 'selected' : ''}>${name}</option>`;
        }).join('')}
      </select>
      <label>Sentiment</label>
      <select id="filter-sentiment">
        <option value="">All</option>
        <option value="bull" ${feedState.sentiment === 'bull' ? 'selected' : ''}>Bull</option>
        <option value="bear" ${feedState.sentiment === 'bear' ? 'selected' : ''}>Bear</option>
        <option value="neutral" ${feedState.sentiment === 'neutral' ? 'selected' : ''}>Neutral</option>
      </select>
      <label>Ticker</label>
      <input type="text" id="filter-ticker" placeholder="e.g. AAPL" value="${escapeHtml(feedState.ticker)}">
      <label>Min Score</label>
      <div class="filter-range">
        <input type="range" id="filter-min-score" min="0" max="100" value="${feedState.min_score}">
        <span class="filter-range-value" id="filter-min-score-val">${feedState.min_score}</span>
      </div>
      <button class="filter-btn ${feedState.sort === 'newest' ? 'active' : ''}" data-sort="newest">Newest</button>
      <button class="filter-btn ${feedState.sort === 'score' ? 'active' : ''}" data-sort="score">Score</button>
    </div>

    <div class="panel full-width" style="border:none;">
      <div class="panel-header">
        <span class="panel-title"><span class="accent">//</span> Scored Feed</span>
        <span class="panel-badge">${escapeHtml(data.total)} results</span>
      </div>
      <div class="panel-body" id="feed-list">`;

    const items = data.items || [];
    if (items.length === 0) {
      html += '<div class="text-muted text-center p-2">No items match filters</div>';
    }
    for (const item of items) {
      const bodySnippet = escapeHtml((item.body_snippet || '').substring(0, 200));
      const redditUrl = escapeHtml(item.reddit_url || '');
      html += `<div class="feed-item" data-id="${escapeHtml(item.id)}">
        <div class="feed-meta">
          ${sentimentBadge(item.sentiment)}
          <span class="ticker">${escapeHtml(item.ticker)}</span>
          <span class="feed-sub">r/${escapeHtml(item.subreddit || '?')}</span>
          <span class="feed-time">${timeAgo(item.analyzed_at)}</span>
          <span class="text-muted text-xs">${escapeHtml(item.source_type)}</span>
        </div>
        <div class="feed-title">${escapeHtml(item.title || 'Untitled')}</div>
        <div class="feed-scores">
          <span class="feed-overall">Score: ${escapeHtml(item.overall_score)}</span>
          <span>R:${escapeHtml(item.reasoning_score)}</span>
          <span>S:${escapeHtml(item.specificity_score)}</span>
          <span>N:${escapeHtml(item.novelty_score)}</span>
          <span>C:${escapeHtml(item.credibility_score)}</span>
        </div>
        <div class="feed-detail hidden" style="margin-top:8px;font-size:11px;color:var(--text-secondary);line-height:1.6;">
          <p>${bodySnippet}</p>
          ${redditUrl ? `<a href="${redditUrl}" target="_blank" rel="noopener" style="margin-top:6px;display:inline-block;">View on Reddit &rarr;</a>` : ''}
        </div>
      </div>`;
    }

    html += '</div>';

    // Pagination
    const pages = data.pages || 1;
    const currentPage = data.page || 1;
    if (pages > 1) {
      html += '<div class="pagination">';
      html += `<span class="pagination-item ${currentPage <= 1 ? 'disabled' : ''}" data-page="${currentPage - 1}">&laquo;</span>`;
      for (let p = 1; p <= pages; p++) {
        if (pages > 7 && p > 3 && p < pages - 2 && Math.abs(p - currentPage) > 1) {
          if (p === 4 || p === pages - 3) html += '<span class="pagination-ellipsis">...</span>';
          continue;
        }
        html += `<span class="pagination-item ${p === currentPage ? 'active' : ''}" data-page="${p}">${p}</span>`;
      }
      html += `<span class="pagination-item ${currentPage >= pages ? 'disabled' : ''}" data-page="${currentPage + 1}">&raquo;</span>`;
      html += '</div>';
    }

    html += '</div>';

    content.classList.remove('loading');
    content.innerHTML = html;

    // Event listeners for filters
    setupFeedListeners();
  }

  function setupFeedListeners() {
    const content = document.getElementById('content');
    if (!content) return;

    const subSelect = document.getElementById('filter-subreddit');
    const sentSelect = document.getElementById('filter-sentiment');
    const tickerInput = document.getElementById('filter-ticker');
    const scoreRange = document.getElementById('filter-min-score');
    const scoreVal = document.getElementById('filter-min-score-val');

    if (subSelect) subSelect.addEventListener('change', function () {
      feedState.subreddit = this.value;
      feedState.page = 1;
      invalidateCache('/api/feed');
      renderFeed().catch(showError);
    });

    if (sentSelect) sentSelect.addEventListener('change', function () {
      feedState.sentiment = this.value;
      feedState.page = 1;
      invalidateCache('/api/feed');
      renderFeed().catch(showError);
    });

    let tickerTimeout;
    if (tickerInput) tickerInput.addEventListener('input', function () {
      clearTimeout(tickerTimeout);
      tickerTimeout = setTimeout(function () {
        feedState.ticker = tickerInput.value.trim().toUpperCase();
        feedState.page = 1;
        invalidateCache('/api/feed');
        renderFeed().catch(showError);
      }, 400);
    });

    if (scoreRange) scoreRange.addEventListener('input', function () {
      if (scoreVal) scoreVal.textContent = this.value;
    });
    if (scoreRange) scoreRange.addEventListener('change', function () {
      feedState.min_score = parseInt(this.value, 10);
      feedState.page = 1;
      invalidateCache('/api/feed');
      renderFeed().catch(showError);
    });

    // Remove previous listener to avoid stacking on re-renders
    if (content._feedHandler) {
      content.removeEventListener('click', content._feedHandler);
    }

    // Sort toggle buttons (event delegation)
    content._feedHandler = function (e) {
      const sortBtn = e.target.closest('[data-sort]');
      if (sortBtn) {
        feedState.sort = sortBtn.getAttribute('data-sort');
        feedState.page = 1;
        invalidateCache('/api/feed');
        renderFeed().catch(showError);
        return;
      }

      // Pagination
      const pageBtn = e.target.closest('.pagination-item:not(.disabled)');
      if (pageBtn) {
        const p = parseInt(pageBtn.getAttribute('data-page'), 10);
        if (p >= 1) {
          feedState.page = p;
          invalidateCache('/api/feed');
          renderFeed().catch(showError);
        }
        return;
      }

      // Feed item expand/collapse
      const feedItem = e.target.closest('.feed-item');
      if (feedItem) {
        const detail = feedItem.querySelector('.feed-detail');
        if (detail) detail.classList.toggle('hidden');
      }
    };
    content.addEventListener('click', content._feedHandler);
  }

  // ---- Tracked ----------------------------------------------------------

  function sortStocks(stocks, sortBy, sortDir) {
    const sorted = stocks.slice();
    sorted.sort(function (a, b) {
      let va = a[sortBy], vb = b[sortBy];
      if (va == null) va = sortDir === 'asc' ? Infinity : -Infinity;
      if (vb == null) vb = sortDir === 'asc' ? Infinity : -Infinity;
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return sorted;
  }

  function sortArrow(col) {
    if (trackedState.sortBy !== col) return '';
    return trackedState.sortDir === 'asc' ? ' &#9650;' : ' &#9660;';
  }

  async function renderTracked() {
    setCmdText('tracked');
    const params = trackedState.status !== 'all' ? '?status=' + trackedState.status : '';
    const data = await api('/api/tracked' + params);
    const content = document.getElementById('content');
    if (!content) return;

    const stocks = sortStocks(data.stocks || [], trackedState.sortBy, trackedState.sortDir);

    // Summary stats for the current view
    const withData = stocks.filter(function (s) { return s.return_pct != null; });
    const paired = withData.filter(function (s) { return s.alpha_pct != null; });
    const wins = paired.filter(function (s) { return s.alpha_pct > 0; }).length;
    const avgRet = withData.length > 0 ? withData.reduce(function (sum, s) { return sum + s.return_pct; }, 0) / withData.length : null;
    const avgAlpha = paired.length > 0 ? paired.reduce(function (sum, s) { return sum + s.alpha_pct; }, 0) / paired.length : null;

    const summaryRetFmt = formatPercent(avgRet);
    const summaryAlphaFmt = formatPercent(avgAlpha);

    let html = `
    <div class="filter-bar">
      <button class="filter-btn ${trackedState.status === 'active' ? 'active' : ''}" data-status="active">Active</button>
      <button class="filter-btn ${trackedState.status === 'completed' ? 'active' : ''}" data-status="completed">Completed</button>
      <button class="filter-btn ${trackedState.status === 'all' ? 'active' : ''}" data-status="all">All</button>
      <span class="filter-summary">
        ${withData.length > 0 ? `<span class="${summaryRetFmt.cls}">Latest available return (mixed horizons): ${summaryRetFmt.text}</span>
        <span class="text-muted">·</span>
        <span class="${summaryAlphaFmt.cls}">Avg Excess vs SPY: ${summaryAlphaFmt.text}</span>
        <span class="text-muted">·</span>
        <span>Win: ${wins}/${paired.length}</span>` : ''}
      </span>
    </div>

    <div class="panel full-width" style="border:none;">
      <div class="panel-header">
        <span class="panel-title"><span class="accent">//</span> Tracked Stocks</span>
        <span class="panel-badge">${stocks.length} stocks</span>
      </div>
      <div class="panel-body">
        <div class="table-wrap">
          <table id="tracked-table">
            <thead><tr>
              <th class="sortable" data-sort="ticker">Ticker${sortArrow('ticker')}</th>
              <th class="sortable" data-sort="discovery_price">Entry Price${sortArrow('discovery_price')}</th>
              <th class="sortable" data-sort="return_pct">Return %${sortArrow('return_pct')}</th>
              <th class="sortable" data-sort="alpha_pct">Excess vs SPY %${sortArrow('alpha_pct')}</th>
              <th class="sortable" data-sort="mention_count">Mentions${sortArrow('mention_count')}</th>
              <th class="sortable" data-sort="avg_quality_score">Score${sortArrow('avg_quality_score')}</th>
              <th>Checkpoints</th>
            </tr></thead>
            <tbody>`;

    if (stocks.length === 0) {
      html += '<tr><td colspan="7" class="text-muted text-center">No stocks found</td></tr>';
    }
    for (const s of stocks) {
      const ret = formatPercent(s.return_pct);
      const alpha = formatPercent(s.alpha_pct);
      html += `<tr class="expandable-row" data-ticker="${escapeHtml(s.ticker)}">
        <td class="ticker">${escapeHtml(s.ticker)}</td>
        <td>${formatPrice(s.discovery_price)}</td>
        <td class="${ret.cls}">${escapeHtml(ret.text)}</td>
        <td class="${alpha.cls}">${escapeHtml(alpha.text)}</td>
        <td>${escapeHtml(s.mention_count || '--')}</td>
        <td>${s.avg_quality_score != null ? scoreBarHtml(Math.round(s.avg_quality_score)) : '--'}</td>
        <td>${checkpointDots(s)}</td>
      </tr>
      <tr class="detail-panel" id="detail-${escapeHtml(s.ticker)}">
        <td colspan="7">
          <div class="loading text-muted">Loading details</div>
        </td>
      </tr>`;
    }

    html += '</tbody></table></div></div></div>';

    content.classList.remove('loading');
    content.innerHTML = html;

    // Remove previous listener to avoid stacking on re-renders
    if (content._trackedHandler) {
      content.removeEventListener('click', content._trackedHandler);
    }

    // Event delegation for status toggle, sort, and row expand
    content._trackedHandler = function (e) {
      const sortHeader = e.target.closest('[data-sort]');
      if (sortHeader) {
        const col = sortHeader.getAttribute('data-sort');
        if (trackedState.sortBy === col) {
          trackedState.sortDir = trackedState.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          trackedState.sortBy = col;
          trackedState.sortDir = col === 'ticker' ? 'asc' : 'desc';
        }
        renderTracked().catch(showError);
        return;
      }

      const statusBtn = e.target.closest('[data-status]');
      if (statusBtn) {
        trackedState.status = statusBtn.getAttribute('data-status');
        invalidateCache('/api/tracked');
        renderTracked().catch(showError);
        return;
      }

      const row = e.target.closest('.expandable-row');
      if (row) {
        const ticker = row.getAttribute('data-ticker');
        const detailRow = document.getElementById('detail-' + ticker);
        if (!detailRow) return;

        row.classList.toggle('expanded');
        detailRow.classList.toggle('open');

        // Fetch detail on first open
        if (detailRow.classList.contains('open') && !detailRow.getAttribute('data-loaded')) {
          loadTrackedDetail(ticker, detailRow);
        }
      }
    };
    content.addEventListener('click', content._trackedHandler);
  }

  async function loadTrackedDetail(ticker, detailRow) {
    try {
      const data = await api('/api/tracked/' + encodeURIComponent(ticker));
      detailRow.setAttribute('data-loaded', '1');

      const stock = data.stock || {};
      const mentions = data.mentions || [];
      const checkpoints = stock.checkpoints || {};

      let html = '<td colspan="7"><div class="detail-content">';

      // Checkpoint details
      for (const d of CHECKPOINT_DAYS) {
        const cp = checkpoints[d];
        if (cp) {
          const ret = stock.discovery_price
            ? formatPercent((cp.price - stock.discovery_price) / stock.discovery_price * 100)
            : { text: '--', cls: '' };
          html += `<div class="detail-item">
            <span class="detail-label">${d}-Day Price</span>
            <span class="detail-value">${formatPrice(cp.price)}</span>
            <span class="text-xs ${ret.cls}">${escapeHtml(ret.text)}</span>
          </div>`;
        } else {
          html += `<div class="detail-item">
            <span class="detail-label">${d}-Day Price</span>
            <span class="detail-value text-muted">Pending</span>
          </div>`;
        }
      }

      html += '</div>';

      // Mentions list
      if (mentions.length > 0) {
        html += '<div style="margin-top:16px;"><div class="text-xs text-muted text-uppercase mb-1">Mentions</div>';
        for (const m of mentions.slice(0, 5)) {
          html += `<div class="feed-item" style="padding:8px 0;">
            <div class="feed-meta">
              ${sentimentBadge(m.sentiment)}
              <span class="feed-sub">r/${escapeHtml(m.subreddit || '?')}</span>
              <span class="feed-overall">Score: ${escapeHtml(m.overall_score)}</span>
            </div>
            <div class="feed-title text-sm">${escapeHtml((m.title || '').substring(0, 60))}</div>
          </div>`;
        }
        html += '</div>';
      }

      html += '</td>';
      detailRow.innerHTML = html;
    } catch (err) {
      detailRow.innerHTML = `<td colspan="7"><div class="error-panel">
        <div class="error-header">Failed</div>
        <div class="error-message">${escapeHtml(err.message)}</div>
      </div></td>`;
    }
  }

  // ---- Portfolio --------------------------------------------------------

  function portfolioSortArrow(col) {
    if (portfolioState.sortBy !== col) return '';
    return portfolioState.sortDir === 'asc' ? ' &#9650;' : ' &#9660;';
  }

  async function renderPortfolio() {
    setCmdText('portfolio');

    // On first load, fetch with no filters to get the default_min_score
    if (!portfolioState._initialized) {
      const init = await api('/api/portfolio');
      if (init && init.default_min_score) {
        portfolioState.min_score = init.default_min_score;
      }
      portfolioState._initialized = true;
    }

    const params = new URLSearchParams();
    if (portfolioState.min_score > 0) params.set('min_score', portfolioState.min_score);
    if (portfolioState.min_mentions > 0) params.set('min_mentions', portfolioState.min_mentions);
    if (portfolioState.ticker) params.set('ticker', portfolioState.ticker);
    if (portfolioState.discovered_after) params.set('discovered_after', portfolioState.discovered_after);
    if (portfolioState.discovered_before) params.set('discovered_before', portfolioState.discovered_before);
    if (portfolioState.sentiment) params.set('sentiment', portfolioState.sentiment);
    params.set('checkpoint', portfolioState.checkpoint);

    const data = await api('/api/portfolio?' + params.toString());
    const content = document.getElementById('content');
    if (!content) return;

    const checkpoints = data.checkpoints || {};
    const cpKey = portfolioState.checkpoint;
    const cpData = checkpoints[cpKey];

    let html = `
    <div class="filter-bar">
      <label>Min Score</label>
      <div class="filter-range">
        <button type="button" class="score-step-btn" id="pf-score-down">&minus;</button>
        <input type="range" id="pf-min-score" min="0" max="100" step="1" value="${portfolioState.min_score}">
        <button type="button" class="score-step-btn" id="pf-score-up">&plus;</button>
        <span class="filter-range-value" id="pf-min-score-val">${portfolioState.min_score}</span>
      </div>
      <label>Min Mentions</label>
      <select id="pf-min-mentions">
        <option value="0" ${portfolioState.min_mentions === 0 ? 'selected' : ''}>Any</option>
        <option value="5" ${portfolioState.min_mentions === 5 ? 'selected' : ''}>5+</option>
        <option value="10" ${portfolioState.min_mentions === 10 ? 'selected' : ''}>10+</option>
        <option value="15" ${portfolioState.min_mentions === 15 ? 'selected' : ''}>15+</option>
        <option value="20" ${portfolioState.min_mentions === 20 ? 'selected' : ''}>20+</option>
      </select>
      <label>Sentiment</label>
      <select id="pf-sentiment">
        <option value="" ${portfolioState.sentiment === '' ? 'selected' : ''}>All</option>
        <option value="bull" ${portfolioState.sentiment === 'bull' ? 'selected' : ''}>Bull</option>
        <option value="bear" ${portfolioState.sentiment === 'bear' ? 'selected' : ''}>Bear</option>
        <option value="neutral" ${portfolioState.sentiment === 'neutral' ? 'selected' : ''}>Neutral</option>
      </select>
      <label>Ticker</label>
      <input type="text" id="pf-ticker" placeholder="e.g. AAPL" value="${escapeHtml(portfolioState.ticker)}">
      <label>From</label>
      <input type="date" id="pf-date-after" value="${escapeHtml(portfolioState.discovered_after)}"${data.earliest_date ? ' min="' + escapeHtml(data.earliest_date) + '"' : ''}${data.latest_date ? ' max="' + escapeHtml(data.latest_date) + '"' : ''}>
      <label>To</label>
      <input type="date" id="pf-date-before" value="${escapeHtml(portfolioState.discovered_before)}"${data.earliest_date ? ' min="' + escapeHtml(data.earliest_date) + '"' : ''}${data.latest_date ? ' max="' + escapeHtml(data.latest_date) + '"' : ''}>
      <span class="filter-summary">
        <span class="text-muted">${data.filtered_count}/${data.total_tracked} stocks</span>
      </span>
    </div>

    <!-- Checkpoint summary cards -->
    <div class="stats-row">`;

    for (const d of CHECKPOINT_DAYS) {
      const cp = checkpoints[String(d)];
      const isActive = portfolioState.checkpoint === String(d);
      if (cp) {
        const pnlCls = cp.pnl >= 0 ? 'green' : 'red';
        const edgeVal = cp.pnl - cp.spy_pnl;
        const edgeCls = edgeVal >= 0 ? 'green' : 'red';
        html += `<div class="stat-card checkpoint-card ${isActive ? 'checkpoint-active' : ''}" data-cp="${d}">
          <div class="stat-label">${d}-Day Checkpoint</div>
          <div class="stat-value ${pnlCls}">${formatMoney(cp.pnl)}</div>
          <div class="stat-sub">${cp.count}/${cp.total} stocks · Edge: <span class="${edgeCls}">${formatMoney(edgeVal)}</span></div>
        </div>`;
      } else {
        html += `<div class="stat-card checkpoint-card ${isActive ? 'checkpoint-active' : ''}" data-cp="${d}">
          <div class="stat-label">${d}-Day Checkpoint</div>
          <div class="stat-value text-muted">--</div>
          <div class="stat-sub">No data yet</div>
        </div>`;
      }
    }

    html += `</div>`;

    // Summary panel for selected checkpoint
    if (cpData) {
      const pnlCls = cpData.pnl >= 0 ? 'positive' : 'negative';
      const spyCls = cpData.spy_pnl >= 0 ? 'positive' : 'negative';
      const edge = cpData.pnl - cpData.spy_pnl;
      const edgeCls = edge >= 0 ? 'positive' : 'negative';
      const winCls = cpData.win_rate >= 50 ? 'green' : 'red';

      html += `
      <div class="panel full-width" style="border:none;">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> ${cpKey}-Day Summary</span>
          <span class="panel-badge">$1k/stock</span>
        </div>
        <div class="panel-body">
          <div class="portfolio-summary-row">
            <div class="portfolio-stat">
              <span class="portfolio-stat-label">Invested</span>
              <span class="portfolio-stat-value">${formatPrice(cpData.invested)}</span>
            </div>
            <div class="portfolio-stat">
              <span class="portfolio-stat-label">Portfolio Value</span>
              <span class="portfolio-stat-value">${formatPrice(cpData.portfolio_value)}</span>
            </div>
            <div class="portfolio-stat">
              <span class="portfolio-stat-label">P&L</span>
              <span class="portfolio-stat-value ${pnlCls}">${formatMoney(cpData.pnl)}</span>
            </div>
            <div class="portfolio-stat">
              <span class="portfolio-stat-label">SPY P&L</span>
              <span class="portfolio-stat-value ${spyCls}">${formatMoney(cpData.spy_pnl)}</span>
            </div>
            <div class="portfolio-stat">
              <span class="portfolio-stat-label">Edge vs SPY</span>
              <span class="portfolio-stat-value ${edgeCls}">${formatMoney(edge)}</span>
            </div>
            <div class="portfolio-stat">
              <span class="portfolio-stat-label">Win Rate</span>
              <span class="portfolio-stat-value ${winCls}">${cpData.win_rate}%</span>
            </div>
            <div class="portfolio-stat">
              <span class="portfolio-stat-label">Avg Return</span>
              <span class="portfolio-stat-value ${cpData.avg_return >= 0 ? 'positive' : 'negative'}">${formatPercent(cpData.avg_return).text}</span>
            </div>
            <div class="portfolio-stat">
              <span class="portfolio-stat-label">Avg SPY Return</span>
              <span class="portfolio-stat-value ${cpData.avg_spy_return >= 0 ? 'positive' : 'negative'}">${formatPercent(cpData.avg_spy_return).text}</span>
            </div>
          </div>
        </div>
      </div>`;

      // Score-profit curve chart
      const curveData = (data.score_profit_curve || {})[cpKey];
      if (curveData && curveData.points) {
        const bestScore = curveData.best_score;
        const bestReturn = curveData.best_return;
        const bestFmt = bestReturn != null ? formatPercent(bestReturn) : { text: '--', cls: '' };
        html += `
        <div class="panel full-width" style="border:none;">
          <div class="panel-header">
            <span class="panel-title"><span class="accent">//</span> Avg Return by Min Score Threshold (${cpKey}d)</span>
            <span class="panel-badge">In-sample maximum: <span class="${bestFmt.cls}">${bestFmt.text}</span> at score ${bestScore}</span>
          </div>
          <div class="panel-body">
            <div class="chart-area" style="height:260px;"><canvas id="score-profit-chart"></canvas></div>
          </div>
        </div>`;
      }

      // Per-stock breakdown table (collapsible)
      const cpStocks = cpData.stocks || [];
      html += `
      <div class="panel full-width collapsible-panel" style="border:none;">
        <div class="panel-header collapsible-header" data-collapse="stock-breakdown">
          <span class="panel-title"><span class="accent">//</span> Stock Breakdown <span class="collapse-arrow">&#9660;</span></span>
          <span class="panel-badge">${cpStocks.length} stocks</span>
        </div>
        <div class="panel-body collapsible-body hidden" id="stock-breakdown">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th class="sortable" data-pf-sort="ticker">Ticker${portfolioSortArrow('ticker')}</th>
                <th class="sortable" data-pf-sort="stock_return">Return %${portfolioSortArrow('stock_return')}</th>
                <th class="sortable" data-pf-sort="spy_return">SPY Return %${portfolioSortArrow('spy_return')}</th>
                <th class="sortable" data-pf-sort="alpha">Excess vs SPY %${portfolioSortArrow('alpha')}</th>
                <th>P&L ($1k)</th>
              </tr></thead>
              <tbody>`;

      // Sort the stocks
      const sorted = cpStocks.slice().sort(function (a, b) {
        let va = a[portfolioState.sortBy], vb = b[portfolioState.sortBy];
        if (va == null) va = portfolioState.sortDir === 'asc' ? Infinity : -Infinity;
        if (vb == null) vb = portfolioState.sortDir === 'asc' ? Infinity : -Infinity;
        if (typeof va === 'string') { va = va.toLowerCase(); vb = (vb || '').toLowerCase(); }
        if (va < vb) return portfolioState.sortDir === 'asc' ? -1 : 1;
        if (va > vb) return portfolioState.sortDir === 'asc' ? 1 : -1;
        return 0;
      });

      for (const s of sorted) {
        const retFmt = formatPercent(s.stock_return);
        const spyFmt = formatPercent(s.spy_return);
        const alphaFmt = formatPercent(s.alpha);
        const stockPnl = s.stock_return / 100 * 1000;
        html += `<tr>
          <td class="ticker">${escapeHtml(s.ticker)}</td>
          <td class="${retFmt.cls}">${retFmt.text}</td>
          <td class="${spyFmt.cls}">${spyFmt.text}</td>
          <td class="${alphaFmt.cls}">${alphaFmt.text}</td>
          <td class="${stockPnl >= 0 ? 'positive' : 'negative'}">${formatMoney(stockPnl)}</td>
        </tr>`;
      }

      html += '</tbody></table></div></div></div>';
    } else {
      // Show all stocks table even when no checkpoint data
      html += `
      <div class="panel full-width" style="border:none;">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> ${cpKey}-Day Summary</span>
        </div>
        <div class="panel-body">
          <div class="text-muted text-center p-2">No stocks have reached the ${cpKey}-day checkpoint yet with current filters</div>
        </div>
      </div>`;
    }

    // ---- Insights section ----
    const insights = data.insights || {};

    if (insights.return_distribution || insights.statistics) {
      html += `<div class="insights-divider"><span class="accent">//</span> Insights &amp; Analysis</div>`;

      // Row 1: Return Distribution + Statistical Significance
      html += '<div class="main">';

      // Return distribution chart
      if (insights.return_distribution) {
        html += `
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><span class="accent">//</span> Return Distribution</span>
            <span class="info-toggle" data-info="return-dist">?</span>
          </div>
          <div class="info-box hidden" id="info-return-dist">
            <strong>What is this?</strong> Distribution of recorded stock returns at the selected nominal horizon. This describes the observed sample; it does not estimate future profitability.
          </div>
          <div class="panel-body">
            <div class="chart-area"><canvas id="return-dist-chart"></canvas></div>
          </div>
        </div>`;
      }

      if (insights.statistics) {
        const stats = insights.statistics;
        html += `<div class="panel"><div class="panel-header"><span class="panel-title">Descriptive results · ${data.checkpoint_days}d nominal horizon</span></div>
          <div class="panel-body"><p>${escapeHtml(data.measurement_note)}</p>
          <div class="portfolio-summary-row">
          <div class="portfolio-stat"><span class="portfolio-stat-label">Observations</span><span class="portfolio-stat-value">${stats.n}</span></div>
          <div class="portfolio-stat"><span class="portfolio-stat-label">Median return</span><span class="portfolio-stat-value">${formatPercent(stats.median_return).text}</span></div>
          <div class="portfolio-stat"><span class="portfolio-stat-label">Mean excess vs SPY</span><span class="portfolio-stat-value">${formatPercent(stats.mean_alpha).text}</span></div>
          </div></div></div>`;
      }

      html += '</div>';

      // Row 2: Score Validation + Mention Count
      html += '<div class="main">';

      if (insights.score_vs_return) {
        html += `
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><span class="accent">//</span> Score vs Return</span>
            <span class="info-toggle" data-info="score-val">?</span>
          </div>
          <div class="info-box hidden" id="info-score-val">
            <strong>What is this?</strong> This chart groups discoveries by their stored quality score at the selected nominal horizon. Groups are small and selected by tracking thresholds. Differences are exploratory and do not establish predictive value.
          </div>
          <div class="panel-body">
            <div class="chart-area"><canvas id="score-val-chart"></canvas></div>
            <div class="table-wrap" style="margin-top:12px;">
              <table>
                <thead><tr><th>Score Range</th><th>Stocks</th><th>Avg Return</th><th>Excess vs SPY</th><th>Win Rate</th></tr></thead>
                <tbody>`;
        for (const b of insights.score_vs_return) {
          const retFmt = b.avg_return != null ? formatPercent(b.avg_return) : { text: '--', cls: '' };
          const alpFmt = b.avg_alpha != null ? formatPercent(b.avg_alpha) : { text: '--', cls: '' };
          html += `<tr>
            <td>${escapeHtml(b.range)}</td>
            <td>${b.count}</td>
            <td class="${retFmt.cls}">${retFmt.text}</td>
            <td class="${alpFmt.cls}">${alpFmt.text}</td>
            <td>${b.win_rate != null ? b.win_rate + '%' : '--'}</td>
          </tr>`;
        }
        html += '</tbody></table></div></div></div>';
      }

      if (insights.mentions_vs_return) {
        html += `
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><span class="accent">//</span> Mentions vs Return</span>
            <span class="info-toggle" data-info="mentions-val">?</span>
          </div>
          <div class="info-box hidden" id="info-mentions-val">
            <strong>What is this?</strong> Does more Reddit buzz = better picks? Stocks are grouped by how many times they were mentioned. If heavily-mentioned stocks do worse, the crowd may be piling into overhyped plays. If they do better, consensus is adding signal. Watch for the "wisdom of crowds" effect — moderate mention counts often outperform extremes.
          </div>
          <div class="panel-body">
            <div class="chart-area"><canvas id="mentions-val-chart"></canvas></div>
            <div class="table-wrap" style="margin-top:12px;">
              <table>
                <thead><tr><th>Mentions</th><th>Stocks</th><th>Avg Return</th><th>Excess vs SPY</th></tr></thead>
                <tbody>`;
        for (const b of insights.mentions_vs_return) {
          const retFmt = b.avg_return != null ? formatPercent(b.avg_return) : { text: '--', cls: '' };
          const alpFmt = b.avg_alpha != null ? formatPercent(b.avg_alpha) : { text: '--', cls: '' };
          html += `<tr>
            <td>${escapeHtml(b.range)}</td>
            <td>${b.count}</td>
            <td class="${retFmt.cls}">${retFmt.text}</td>
            <td class="${alpFmt.cls}">${alpFmt.text}</td>
          </tr>`;
        }
        html += '</tbody></table></div></div></div>';
      }

      html += '</div>';

      // Row 3: Sentiment Accuracy + Sector Concentration
      html += '<div class="main">';

      if (insights.sentiment_accuracy) {
        const sa = insights.sentiment_accuracy;
        html += `
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><span class="accent">//</span> Sentiment Accuracy</span>
            <span class="info-toggle" data-info="sent-acc">?</span>
          </div>
          <div class="info-box hidden" id="info-sent-acc">
            <strong>What is this?</strong> Sentiment is saved at discovery. Directional agreement means a bullish stock rose or a bearish stock fell at the selected nominal horizon. Neutral and unknown sentiments have no directional accuracy. This is descriptive, not evidence of predictive value.
          </div>
          <div class="panel-body">
            <div class="table-wrap">
              <table>
                <thead><tr><th>Sentiment</th><th>Stocks</th><th>Avg Return</th><th>Direction Accuracy</th></tr></thead>
                <tbody>`;
        for (const sent of ['bull', 'bear', 'neutral', 'unknown']) {
          const d = sa[sent] || {};
          const retFmt = d.avg_return != null ? formatPercent(d.avg_return) : { text: '--', cls: '' };
          const accCls = d.accuracy != null ? (d.accuracy >= 50 ? 'positive' : 'negative') : '';
          html += `<tr>
            <td>${sentimentBadge(sent)}</td>
            <td>${d.count || 0}</td>
            <td class="${retFmt.cls}">${retFmt.text}</td>
            <td class="${accCls}">${d.accuracy != null ? d.accuracy + '%' : '--'}</td>
          </tr>`;
        }
        html += '</tbody></table></div></div></div>';
      }

      if (insights.sector_breakdown && insights.sector_breakdown.length > 0) {
        html += `
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title"><span class="accent">//</span> Sector Concentration</span>
            <span class="info-toggle" data-info="sector-conc">?</span>
          </div>
          <div class="info-box hidden" id="info-sector-conc">
            <strong>What is this?</strong> Shows how concentrated your picks are across sectors (identified by their sector ETF). If 70% of picks are tech (XLK), you're not really testing "can Reddit pick stocks" — you're testing "does Reddit like tech." Heavy concentration means your results are more about sector performance than stock-picking skill. A diversified breakdown gives more confidence that returns come from actual stock selection. Hover the chart for per-sector average returns.
          </div>
          <div class="panel-body">
            <div class="chart-area"><canvas id="sector-chart"></canvas></div>
            <div class="table-wrap" style="margin-top:12px;">
              <table>
                <thead><tr><th>Sector ETF</th><th>Stocks</th><th>% of Portfolio</th><th>Avg Return</th></tr></thead>
                <tbody>`;
        for (const s of insights.sector_breakdown) {
          const retFmt = s.avg_return != null ? formatPercent(s.avg_return) : { text: '--', cls: '' };
          html += `<tr>
            <td class="ticker">${escapeHtml(s.sector_etf)}</td>
            <td>${s.count}</td>
            <td>${s.pct_of_portfolio}%</td>
            <td class="${retFmt.cls}">${retFmt.text}</td>
          </tr>`;
        }
        html += '</tbody></table></div></div></div>';
      }

      html += '</div>';
    }

    // All filtered stocks table (collapsible)
    const stocks = data.stocks || [];
    html += `
    <div class="panel full-width collapsible-panel" style="border:none;">
      <div class="panel-header collapsible-header" data-collapse="all-stocks">
        <span class="panel-title"><span class="accent">//</span> All Filtered Stocks <span class="collapse-arrow">&#9660;</span></span>
        <span class="panel-badge">${stocks.length} stocks</span>
      </div>
      <div class="panel-body collapsible-body hidden" id="all-stocks">
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>Ticker</th><th>Entry</th><th>Score</th><th>Mentions</th><th>Return %</th><th>Excess vs SPY %</th><th>Checkpoint</th><th>Status</th>
            </tr></thead>
            <tbody>`;

    if (stocks.length === 0) {
      html += '<tr><td colspan="8" class="text-muted text-center">No stocks match filters</td></tr>';
    }
    for (const s of stocks) {
      const retFmt = formatPercent(s.return_pct);
      const alphaFmt = formatPercent(s.alpha_pct);
      html += `<tr>
        <td class="ticker">${escapeHtml(s.ticker)}</td>
        <td>${formatPrice(s.discovery_price)}</td>
        <td>${s.avg_quality_score != null ? scoreBarHtml(Math.round(s.avg_quality_score)) : '--'}</td>
        <td>${escapeHtml(s.mention_count || '--')}</td>
        <td class="${retFmt.cls}">${retFmt.text}</td>
        <td class="${alphaFmt.cls}">${alphaFmt.text}</td>
        <td>${s.checkpoint_days ? s.checkpoint_days + 'd' : '<span class="text-muted">Pending</span>'}</td>
        <td>${s.status === 'active' ? '<span class="sentiment-badge bull">ACTIVE</span>' : '<span class="sentiment-badge neutral">DONE</span>'}</td>
      </tr>`;
    }

    html += '</tbody></table></div></div></div>';

    content.classList.remove('loading');
    content.innerHTML = html;

    setupPortfolioListeners();

    // Render insight charts
    requestAnimationFrame(function () {
      if (insights.return_distribution && typeof window.renderReturnDistribution === 'function') {
        window.renderReturnDistribution('return-dist-chart', insights.return_distribution);
      }
      if (insights.score_vs_return && typeof window.renderScoreVsReturn === 'function') {
        window.renderScoreVsReturn('score-val-chart', insights.score_vs_return);
      }
      if (insights.mentions_vs_return && typeof window.renderMentionsVsReturn === 'function') {
        window.renderMentionsVsReturn('mentions-val-chart', insights.mentions_vs_return);
      }
      if (insights.sector_breakdown && typeof window.renderSectorBreakdown === 'function') {
        window.renderSectorBreakdown('sector-chart', insights.sector_breakdown);
      }
      // Score-profit curve chart
      var curveData = (data.score_profit_curve || {})[portfolioState.checkpoint];
      if (curveData && curveData.points && typeof window.renderScoreProfitCurve === 'function') {
        window.renderScoreProfitCurve('score-profit-chart', curveData, portfolioState.min_score);
      }
    });
  }

  function setupPortfolioListeners() {
    const content = document.getElementById('content');
    if (!content) return;

    // Score slider
    const scoreRange = document.getElementById('pf-min-score');
    const scoreVal = document.getElementById('pf-min-score-val');
    if (scoreRange) scoreRange.addEventListener('input', function () {
      if (scoreVal) scoreVal.textContent = this.value;
    });
    if (scoreRange) scoreRange.addEventListener('change', function () {
      portfolioState.min_score = parseInt(this.value, 10);
      renderPortfolio().catch(showError);
    });

    // Score +/- buttons
    function stepScore(delta) {
      if (!scoreRange) return;
      var v = Math.min(100, Math.max(0, parseInt(scoreRange.value, 10) + delta));
      scoreRange.value = v;
      if (scoreVal) scoreVal.textContent = v;
      portfolioState.min_score = v;
      renderPortfolio().catch(showError);
    }
    var scoreDown = document.getElementById('pf-score-down');
    var scoreUp = document.getElementById('pf-score-up');
    if (scoreDown) scoreDown.addEventListener('click', function () { stepScore(-1); });
    if (scoreUp) scoreUp.addEventListener('click', function () { stepScore(1); });

    // Min mentions
    const mentionsSelect = document.getElementById('pf-min-mentions');
    if (mentionsSelect) mentionsSelect.addEventListener('change', function () {
      portfolioState.min_mentions = parseInt(this.value, 10);
      renderPortfolio().catch(showError);
    });

    // Sentiment filter
    const sentimentSelect = document.getElementById('pf-sentiment');
    if (sentimentSelect) sentimentSelect.addEventListener('change', function () {
      portfolioState.sentiment = this.value;
      renderPortfolio().catch(showError);
    });

    // Ticker filter
    const tickerInput = document.getElementById('pf-ticker');
    let tickerTimeout;
    if (tickerInput) tickerInput.addEventListener('input', function () {
      clearTimeout(tickerTimeout);
      tickerTimeout = setTimeout(function () {
        portfolioState.ticker = tickerInput.value.trim().toUpperCase();
        renderPortfolio().catch(showError);
      }, 400);
    });

    // Date range filters
    const dateAfter = document.getElementById('pf-date-after');
    if (dateAfter) dateAfter.addEventListener('change', function () {
      portfolioState.discovered_after = this.value;
      renderPortfolio().catch(showError);
    });
    const dateBefore = document.getElementById('pf-date-before');
    if (dateBefore) dateBefore.addEventListener('change', function () {
      portfolioState.discovered_before = this.value;
      renderPortfolio().catch(showError);
    });

    // Remove previous listener
    if (content._portfolioHandler) {
      content.removeEventListener('click', content._portfolioHandler);
    }

    content._portfolioHandler = function (e) {
      // Checkpoint card click
      const cpCard = e.target.closest('[data-cp]');
      if (cpCard) {
        portfolioState.checkpoint = cpCard.getAttribute('data-cp');
        renderPortfolio().catch(showError);
        return;
      }

      // Sort headers
      const sortHeader = e.target.closest('[data-pf-sort]');
      if (sortHeader) {
        const col = sortHeader.getAttribute('data-pf-sort');
        if (portfolioState.sortBy === col) {
          portfolioState.sortDir = portfolioState.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          portfolioState.sortBy = col;
          portfolioState.sortDir = col === 'ticker' ? 'asc' : 'desc';
        }
        renderPortfolio().catch(showError);
        return;
      }

      // Collapsible panels
      const collapseHeader = e.target.closest('.collapsible-header');
      if (collapseHeader) {
        const targetId = collapseHeader.getAttribute('data-collapse');
        const body = document.getElementById(targetId);
        if (body) {
          body.classList.toggle('hidden');
          const arrow = collapseHeader.querySelector('.collapse-arrow');
          if (arrow) arrow.classList.toggle('open');
        }
        return;
      }

      // Info toggle (? buttons)
      const infoBtn = e.target.closest('.info-toggle');
      if (infoBtn) {
        const targetId = 'info-' + infoBtn.getAttribute('data-info');
        const box = document.getElementById(targetId);
        if (box) box.classList.toggle('hidden');
        return;
      }
    };
    content.addEventListener('click', content._portfolioHandler);
  }

  // ---- Analytics --------------------------------------------------------

  async function renderAnalytics() {
    const data = await cachedFetch('/api/analytics');
    const content = document.getElementById('content');
    if (!content) return;

    let html = `<div class="main">
      <!-- Score distribution -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Score Distribution</span>
        </div>
        <div class="panel-body">
          <div class="chart-area"><canvas id="score-dist-chart"></canvas></div>
        </div>
      </div>

      <!-- Sentiment by subreddit -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Sentiment by Subreddit</span>
        </div>
        <div class="panel-body">
          <div class="chart-area"><canvas id="sentiment-chart"></canvas></div>
        </div>
      </div>

      <!-- Daily volume -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Daily Post Volume</span>
        </div>
        <div class="panel-body">
          <div class="chart-area"><canvas id="volume-chart"></canvas></div>
        </div>
      </div>

      <!-- Daily comment volume -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Daily Comment Volume</span>
        </div>
        <div class="panel-body">
          <div class="chart-area"><canvas id="comment-volume-chart"></canvas></div>
        </div>
      </div>

      <!-- Subreddit leaderboard -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Subreddit Leaderboard</span>
        </div>
        <div class="panel-body">
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Subreddit</th><th>Avg Score</th><th>Picks</th><th>Score</th>
              </tr></thead>
              <tbody>`;

    const leaderboard = data.subreddit_leaderboard || [];
    if (leaderboard.length === 0) {
      html += '<tr><td colspan="4" class="text-muted text-center">No data yet</td></tr>';
    }
    for (const r of leaderboard) {
      html += `<tr>
        <td class="text-purple">r/${escapeHtml(r.subreddit)}</td>
        <td>${escapeHtml(r.avg_score)}</td>
        <td>${escapeHtml(r.pick_count)}</td>
        <td>${scoreBarHtml(r.avg_score)}</td>
      </tr>`;
    }

    html += `</tbody></table></div></div></div>

      <!-- Accuracy by score range -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title"><span class="accent">//</span> Score vs Return</span>
        </div>
        <div class="panel-body">
          <div class="chart-area"><canvas id="accuracy-chart"></canvas></div>
        </div>
      </div>
    </div>`;

    content.classList.remove('loading');
    content.innerHTML = html;

    // Defer chart rendering to next frame so DOM layout is complete
    requestAnimationFrame(() => {
      if (typeof window.renderScoreDistribution === 'function') {
        window.renderScoreDistribution('score-dist-chart', data.score_distribution);
      }
      if (typeof window.renderSentimentChart === 'function') {
        window.renderSentimentChart('sentiment-chart', data.sentiment_by_subreddit);
      }
      if (typeof window.renderDailyVolume === 'function') {
        window.renderDailyVolume('volume-chart', data.daily_volume);
      }
      if (typeof window.renderDailyCommentVolume === 'function') {
        window.renderDailyCommentVolume('comment-volume-chart', data.daily_comment_volume);
      }
      if (typeof window.renderAccuracyChart === 'function') {
        window.renderAccuracyChart('accuracy-chart', data.accuracy_by_score);
      }
    });
  }

  // ---- Settings ---------------------------------------------------------

  function renderProject() {
    const content = document.getElementById('content');
    if (!content) return;

    content.classList.remove('loading');
    content.innerHTML = `
    <div class="settings-container">
      <div class="settings-section">
        <div class="settings-section-header"><span class="accent">//</span> What Is This</div>
        <div class="project-text">
          <p>A daily pipeline that scrapes Reddit for stock mentions, scores them for quality
          using LLM-based analysis, and tracks whether Reddit's picks actually beat the market.</p>
          <p>The goal is to answer a simple question: <strong>can crowd-sourced investment
          discussion on Reddit reliably identify stocks that outperform the S&amp;P 500?</strong></p>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-section-header"><span class="accent">//</span> Pipeline</div>
        <div class="project-steps">
          <div class="project-step">
            <div class="project-step-num">01</div>
            <div class="project-step-body">
              <strong>Scrape</strong>
              <span>Collects posts and comments from 9 investing subreddits via Reddit's
              public JSON endpoints. Collects configured hot and new listings and eligible top-level comments.</span>
            </div>
          </div>
          <div class="project-step">
            <div class="project-step-num">02</div>
            <div class="project-step-body">
              <strong>Analyze</strong>
              <span>Extracts ticker symbols, filters noise with heuristic checks (length,
              keyword, ticker presence), then scores each mention via LLM across four dimensions:
              reasoning, specificity, novelty, and credibility.</span>
            </div>
          </div>
          <div class="project-step">
            <div class="project-step-num">03</div>
            <div class="project-step-body">
              <strong>Track</strong>
              <span>Stocks with 5+ quality mentions (avg score &ge; 65) are tracked at
              7, 14, 30, and 90-day checkpoints. Returns are compared against the S&amp;P 500
              and sector ETFs to measure alpha.</span>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-section-header"><span class="accent">//</span> Scoring Dimensions</div>
        <div class="project-table-wrap">
          <table>
            <thead><tr>
              <th>Dimension</th><th>Weight</th><th>Measures</th>
            </tr></thead>
            <tbody>
              <tr><td class="ticker">Reasoning</td><td>30%</td><td>Quality of the investment thesis</td></tr>
              <tr><td class="ticker">Specificity</td><td>25%</td><td>Concrete data points, price targets, catalysts</td></tr>
              <tr><td class="ticker">Novelty</td><td>25%</td><td>Information not already priced in</td></tr>
              <tr><td class="ticker">Credibility</td><td>20%</td><td>Realistic claims, acknowledged risks</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-section-header"><span class="accent">//</span> Tech Stack</div>
        <div class="project-table-wrap">
          <table>
            <thead><tr>
              <th>Component</th><th>Technology</th>
            </tr></thead>
            <tbody>
              <tr><td>Language</td><td>Python 3.11+</td></tr>
              <tr><td>Web</td><td>FastAPI + uvicorn</td></tr>
              <tr><td>LLM Scoring</td><td>Google Gemini / Anthropic Claude / Ollama</td></tr>
              <tr><td>Market Data</td><td>yfinance</td></tr>
              <tr><td>Database</td><td>SQLite (WAL mode)</td></tr>
              <tr><td>Frontend</td><td>Vanilla JS, Chart.js</td></tr>
              <tr><td>CI/CD</td><td>GitHub Actions</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-section-header"><span class="accent">//</span> Source &amp; Subreddits</div>
        <div class="project-text">
          <p>Data is collected from:
          <strong>r/wallstreetbets</strong>, <strong>r/stocks</strong>, <strong>r/investing</strong>,
          <strong>r/ValueInvesting</strong>, <strong>r/StockMarket</strong>, <strong>r/SecurityAnalysis</strong>,
          <strong>r/smallstreetbets</strong>, <strong>r/pennystocks</strong>, <strong>r/Undervalued</strong></p>
        </div>
      </div>

      <div class="settings-info">
        This project is for educational and research purposes. Not financial advice.
      </div>
    </div>`;
  }

  // -----------------------------------------------------------------------
  // 8. HTTPS Warning
  // -----------------------------------------------------------------------

  function checkHttps() {
    const hostname = location.hostname;
    const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';
    if (location.protocol !== 'https:' && !isLocal) {
      const warning = document.getElementById('https-warning');
      if (warning) warning.classList.remove('hidden');
    }
  }

  // -----------------------------------------------------------------------
  // 9. Init
  // -----------------------------------------------------------------------

  function init() {
    // Apply saved theme
    setTheme(getTheme());

    // HTTPS check
    checkHttps();

    // Auth check
    const key = getApiKey();
    if (!key) {
      showAuth();
    } else {
      hideAuth();
    }

    // Auth form
    setupAuthForm();

    // Logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', function (e) {
        e.preventDefault();
        logout();
      });
    }

    // Theme toggle button
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) {
      themeBtn.addEventListener('click', function (e) {
        e.preventDefault();
        toggleTheme();
      });
    }

    // HTTPS warning dismiss
    const httpsWarning = document.getElementById('https-warning');
    if (httpsWarning) {
      const dismissBtn = httpsWarning.querySelector('.dismiss');
      if (dismissBtn) {
        dismissBtn.addEventListener('click', function () {
          httpsWarning.classList.add('hidden');
        });
      }
    }

    // Nav
    setupNav();

    // Initial route
    route();
  }

  // Expose logout globally for topbar button
  window.appLogout = logout;

  document.addEventListener('DOMContentLoaded', init);
})();

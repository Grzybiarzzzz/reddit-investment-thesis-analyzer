/* charts.js — Chart.js integration for the themed dashboard */

// ---------------------------------------------------------------------------
// Theme color palettes
// ---------------------------------------------------------------------------
const THEME_COLORS = {
    terminal: {
        green: '#00ff9f',
        greenGlow: 'rgba(0, 255, 159, 0.15)',
        red: '#ff3366',
        amber: '#ffb800',
        cyan: '#00d4ff',
        border: '#1e2a3a',
        text: '#6b7d93',
        muted: '#3d4f63',
        bg: '#0d1117',
        accent: '#00ff9f',
    },
    broadsheet: {
        green: '#3a7d5c',
        greenGlow: 'rgba(58, 125, 92, 0.12)',
        red: '#b33a3a',
        amber: '#b8860b',
        cyan: '#c45d3e',
        border: '#e0d6c8',
        text: '#5c5470',
        muted: '#9b8e7e',
        bg: '#ffffff',
        accent: '#c45d3e',
    },
};

function currentTheme() {
    return document.documentElement.getAttribute('data-theme') || 'terminal';
}

let COLORS = Object.assign({}, THEME_COLORS.terminal);

window.updateChartTheme = function (theme) {
    const palette = THEME_COLORS[theme] || THEME_COLORS.terminal;
    Object.assign(COLORS, palette);
    Chart.defaults.color = COLORS.text;
};

// ---------------------------------------------------------------------------
// Chart.js global defaults
// ---------------------------------------------------------------------------
Chart.defaults.color = COLORS.text;
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;

// ---------------------------------------------------------------------------
// Instance management
// ---------------------------------------------------------------------------
const chartInstances = {};

function destroyChart(canvasId) {
    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
        delete chartInstances[canvasId];
    }
}
window.destroyChart = destroyChart;

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
function baseScales(xGrid, yGrid) {
    const base = (show) => ({
        grid: { color: COLORS.border, drawBorder: false, display: show },
        ticks: { color: COLORS.text, font: { family: "'JetBrains Mono', monospace", size: 11 } },
    });
    return { x: base(xGrid !== false), y: base(yGrid !== false) };
}

function baseOptions(extra) {
    return Object.assign(
        {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
        },
        extra,
    );
}

function refreshColors() {
    const palette = THEME_COLORS[currentTheme()] || THEME_COLORS.terminal;
    Object.assign(COLORS, palette);
    Chart.defaults.color = COLORS.text;
}

function createChart(canvasId, config) {
    refreshColors();
    // Destroy any existing chart on this canvas
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
    // Also clean our local map
    if (chartInstances[canvasId]) {
        delete chartInstances[canvasId];
    }
    const chart = new Chart(canvas, config);
    chartInstances[canvasId] = chart;
    return chart;
}

// ---------------------------------------------------------------------------
// renderPerformanceChart
// ---------------------------------------------------------------------------
window.renderPerformanceChart = function (canvasId, activeStocks) {
    const checkpointLabels = ['Discovery', '7d', '14d', '30d', '90d'];
    const checkpointKeys = [null, 7, 14, 30, 90];

    // Gather stocks that have at least one checkpoint return
    const eligible = (activeStocks || []).filter((s) => {
        if (!s.checkpoints || s.checkpoints.length === 0) return false;
        return s.checkpoints.some((c) => c.stock_return !== null && c.stock_return !== undefined);
    });

    if (eligible.length === 0) {
        // Show placeholder message on the canvas
        destroyChart(canvasId);
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = COLORS.text;
        var bodyFont = getComputedStyle(document.body).getPropertyValue('--font-body').trim() || "'JetBrains Mono', monospace";
        ctx.font = "13px " + bodyFont;
        ctx.textAlign = 'center';
        ctx.fillText('No performance data yet', canvas.width / 2, canvas.height / 2);
        return;
    }

    // Compute average stock return and average SPY return at each checkpoint
    const avgStockReturns = checkpointKeys.map((days) => {
        if (days === null) return 0; // Discovery = 0%
        let sum = 0;
        let count = 0;
        eligible.forEach((s) => {
            const cp = s.checkpoints.find((c) => c.days === days);
            if (cp && cp.stock_return !== null && cp.stock_return !== undefined) {
                sum += cp.stock_return;
                count++;
            }
        });
        return count > 0 ? sum / count : null;
    });

    const avgSpyReturns = checkpointKeys.map((days) => {
        if (days === null) return 0;
        let sum = 0;
        let count = 0;
        eligible.forEach((s) => {
            const cp = s.checkpoints.find((c) => c.days === days);
            if (cp && cp.benchmark_return !== null && cp.benchmark_return !== undefined) {
                sum += cp.benchmark_return;
                count++;
            }
        });
        return count > 0 ? sum / count : null;
    });

    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    // Green gradient fill
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.parentElement.clientHeight || 300);
    gradient.addColorStop(0, COLORS.greenGlow);
    gradient.addColorStop(1, 'transparent');

    createChart(canvasId, {
        type: 'line',
        data: {
            labels: checkpointLabels,
            datasets: [
                {
                    label: 'Avg Stock Return',
                    data: avgStockReturns,
                    borderColor: COLORS.green,
                    backgroundColor: gradient,
                    borderWidth: 2.5,
                    tension: 0.3,
                    fill: true,
                    pointRadius: 4,
                    pointBackgroundColor: COLORS.green,
                    pointBorderColor: COLORS.green,
                    pointHoverRadius: 6,
                    pointStyle: 'circle',
                    pointShadowOffsetX: 0,
                    pointShadowOffsetY: 0,
                    pointShadowBlur: 8,
                    pointShadowColor: COLORS.greenGlow,
                },
                {
                    label: 'SPY Return',
                    data: avgSpyReturns,
                    borderColor: COLORS.muted,
                    borderWidth: 2,
                    borderDash: [6, 4],
                    tension: 0.3,
                    fill: false,
                    pointRadius: 3,
                    pointBackgroundColor: COLORS.muted,
                    pointBorderColor: COLORS.muted,
                },
            ],
        },
        options: baseOptions({
            scales: {
                x: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text },
                },
                y: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: {
                        color: COLORS.text,
                        callback: (v) => v.toFixed(1) + '%',
                    },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) =>
                            ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) + '%' : 'N/A'),
                    },
                },
            },
        }),
    });
};

// ---------------------------------------------------------------------------
// renderScoreDistribution
// ---------------------------------------------------------------------------
window.renderScoreDistribution = function (canvasId, data) {
    if (!data || data.length === 0) return;

    createChart(canvasId, {
        type: 'bar',
        data: {
            labels: data.map((d) => d.bucket),
            datasets: [
                {
                    data: data.map((d) => d.count),
                    backgroundColor: 'rgba(0, 255, 159, 0.7)',
                    borderColor: COLORS.green,
                    borderWidth: 1,
                    borderRadius: 2,
                },
            ],
        },
        options: baseOptions({
            indexAxis: 'y',
            scales: {
                x: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, precision: 0 },
                },
                y: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => 'Count: ' + ctx.parsed.x,
                    },
                },
                datalabels: undefined, // in case plugin is loaded
            },
        }),
        plugins: [
            {
                id: 'barEndLabels',
                afterDatasetsDraw(chart) {
                    const { ctx: c } = chart;
                    chart.data.datasets[0].data.forEach((value, i) => {
                        const meta = chart.getDatasetMeta(0);
                        const bar = meta.data[i];
                        c.save();
                        c.fillStyle = COLORS.text;
                        c.font = "11px 'JetBrains Mono', monospace";
                        c.textAlign = 'left';
                        c.textBaseline = 'middle';
                        c.fillText(value, bar.x + 6, bar.y);
                        c.restore();
                    });
                },
            },
        ],
    });
};

// ---------------------------------------------------------------------------
// renderSentimentChart
// ---------------------------------------------------------------------------
window.renderSentimentChart = function (canvasId, data) {
    if (!data || data.length === 0) return;

    const labels = data.map((d) => {
        const name = d.subreddit || '';
        return name.replace(/^r\//, '');
    });

    createChart(canvasId, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Bull',
                    data: data.map((d) => d.bull),
                    backgroundColor: COLORS.green,
                    borderRadius: 2,
                },
                {
                    label: 'Bear',
                    data: data.map((d) => d.bear),
                    backgroundColor: COLORS.red,
                    borderRadius: 2,
                },
                {
                    label: 'Neutral',
                    data: data.map((d) => d.neutral),
                    backgroundColor: COLORS.muted,
                    borderRadius: 2,
                },
            ],
        },
        options: baseOptions({
            indexAxis: 'y',
            scales: {
                x: {
                    stacked: true,
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, precision: 0 },
                },
                y: {
                    stacked: true,
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text },
                },
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: COLORS.text,
                        font: { family: "'JetBrains Mono', monospace", size: 11 },
                        boxWidth: 12,
                        padding: 16,
                    },
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ctx.dataset.label + ': ' + ctx.parsed.x,
                    },
                },
            },
        }),
    });
};

// ---------------------------------------------------------------------------
// renderDailyVolume
// ---------------------------------------------------------------------------
window.renderDailyVolume = function (canvasId, data) {
    if (!data || data.length === 0) return;

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const labels = data.map((d) => {
        const dt = new Date(d.date);
        return months[dt.getMonth()] + ' ' + dt.getDate();
    });

    createChart(canvasId, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    data: data.map((d) => d.posts),
                    backgroundColor: COLORS.amber,
                    borderRadius: 2,
                },
            ],
        },
        options: baseOptions({
            scales: {
                x: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, maxRotation: 45 },
                },
                y: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, precision: 0 },
                    beginAtZero: true,
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => 'Posts: ' + ctx.parsed.y,
                    },
                },
            },
        }),
    });
};

// ---------------------------------------------------------------------------
// renderDailyCommentVolume
// ---------------------------------------------------------------------------
window.renderDailyCommentVolume = function (canvasId, data) {
    if (!data || data.length === 0) return;

    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const labels = data.map((d) => {
        const dt = new Date(d.date);
        return months[dt.getMonth()] + ' ' + dt.getDate();
    });

    createChart(canvasId, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    data: data.map((d) => d.comments),
                    backgroundColor: COLORS.cyan,
                    borderRadius: 2,
                },
            ],
        },
        options: baseOptions({
            scales: {
                x: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, maxRotation: 45 },
                },
                y: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, precision: 0 },
                    beginAtZero: true,
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => 'Comments: ' + ctx.parsed.y,
                    },
                },
            },
        }),
    });
};

// ---------------------------------------------------------------------------
// renderAccuracyChart
// ---------------------------------------------------------------------------
window.renderAccuracyChart = function (canvasId, data) {
    if (!data || data.length === 0) return;

    const colors = data.map((d) => (d.avg_return >= 0 ? COLORS.green : COLORS.red));

    createChart(canvasId, {
        type: 'bar',
        data: {
            labels: data.map((d) => d.score_range),
            datasets: [
                {
                    data: data.map((d) => d.avg_return),
                    backgroundColor: colors,
                    borderRadius: 2,
                },
            ],
        },
        options: baseOptions({
            scales: {
                x: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text },
                },
                y: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: {
                        color: COLORS.text,
                        callback: (v) => v.toFixed(1) + '%',
                    },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (items) => items[0].label,
                        label: (ctx) => {
                            const item = data[ctx.dataIndex];
                            return [
                                'Avg Return: ' + ctx.parsed.y.toFixed(2) + '%',
                                'Count: ' + item.count,
                            ];
                        },
                    },
                },
            },
        }),
    });
};

// ---------------------------------------------------------------------------
// Portfolio Insight Charts
// ---------------------------------------------------------------------------

window.renderReturnDistribution = function (canvasId, data) {
    if (!data || data.length === 0) return;

    createChart(canvasId, {
        type: 'bar',
        data: {
            labels: data.map((d) => d.label),
            datasets: [{
                data: data.map((d) => d.count),
                backgroundColor: data.map((d) => {
                    if (d.label.includes('+') || d.label.startsWith('>')) return COLORS.green;
                    if (d.label.includes('-') || d.label.startsWith('<')) return COLORS.red;
                    return COLORS.muted;
                }),
                borderRadius: 2,
            }],
        },
        options: baseOptions({
            scales: {
                x: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, maxRotation: 45, font: { size: 10 } },
                },
                y: {
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, precision: 0 },
                    beginAtZero: true,
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: (ctx) => ctx.parsed.y + ' stocks' } },
            },
        }),
    });
};

window.renderScoreVsReturn = function (canvasId, data) {
    if (!data || data.length === 0) return;

    createChart(canvasId, {
        type: 'bar',
        data: {
            labels: data.map((d) => d.range),
            datasets: [
                {
                    label: 'Avg Return',
                    data: data.map((d) => d.avg_return),
                    backgroundColor: COLORS.green,
                    borderRadius: 2,
                },
                {
                    label: 'Avg Excess vs SPY',
                    data: data.map((d) => d.avg_alpha),
                    backgroundColor: COLORS.cyan,
                    borderRadius: 2,
                },
            ],
        },
        options: baseOptions({
            scales: {
                x: { grid: { color: COLORS.border, drawBorder: false }, ticks: { color: COLORS.text } },
                y: { grid: { color: COLORS.border, drawBorder: false }, ticks: { color: COLORS.text, callback: (v) => v.toFixed(1) + '%' } },
            },
            plugins: {
                legend: { display: true, position: 'top', labels: { color: COLORS.text, boxWidth: 12, padding: 16, font: { family: "'JetBrains Mono', monospace", size: 11 } } },
                tooltip: { callbacks: { label: (ctx) => { var item = data[ctx.dataIndex]; return ctx.dataset.label + ': ' + (ctx.parsed.y != null ? ctx.parsed.y.toFixed(2) + '%' : 'N/A') + ' (' + item.count + ' stocks)'; } } },
            },
        }),
    });
};

window.renderMentionsVsReturn = function (canvasId, data) {
    if (!data || data.length === 0) return;

    createChart(canvasId, {
        type: 'bar',
        data: {
            labels: data.map((d) => d.range + ' mentions'),
            datasets: [
                { label: 'Avg Return', data: data.map((d) => d.avg_return), backgroundColor: COLORS.green, borderRadius: 2 },
                { label: 'Avg Excess vs SPY', data: data.map((d) => d.avg_alpha), backgroundColor: COLORS.cyan, borderRadius: 2 },
            ],
        },
        options: baseOptions({
            scales: {
                x: { grid: { color: COLORS.border, drawBorder: false }, ticks: { color: COLORS.text } },
                y: { grid: { color: COLORS.border, drawBorder: false }, ticks: { color: COLORS.text, callback: (v) => v.toFixed(1) + '%' } },
            },
            plugins: {
                legend: { display: true, position: 'top', labels: { color: COLORS.text, boxWidth: 12, padding: 16, font: { family: "'JetBrains Mono', monospace", size: 11 } } },
                tooltip: { callbacks: { label: (ctx) => { var item = data[ctx.dataIndex]; return ctx.dataset.label + ': ' + (ctx.parsed.y != null ? ctx.parsed.y.toFixed(2) + '%' : 'N/A') + ' (' + item.count + ' stocks)'; } } },
            },
        }),
    });
};

window.renderScoreProfitCurve = function (canvasId, curveData, currentScore) {
    if (!curveData || !curveData.points || curveData.points.length === 0) return;

    var points = curveData.points;
    var labels = points.map(function (p) { return p.min_score; });
    var returns = points.map(function (p) { return p.avg_return; });
    var counts = points.map(function (p) { return p.count; });
    var bestIdx = points.findIndex(function (p) { return p.min_score === curveData.best_score; });

    // Color points: best = amber, current = cyan, rest = green
    var pointColors = points.map(function (p, i) {
        if (i === bestIdx) return COLORS.amber;
        if (p.min_score === currentScore) return COLORS.cyan;
        return COLORS.green;
    });
    var pointRadii = points.map(function (p, i) {
        if (i === bestIdx || p.min_score === currentScore) return 6;
        return 3;
    });

    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext('2d');

    // Segment coloring: green above 0%, red below
    var segmentColor = function (ctx2) {
        var yVal = ctx2.p1.parsed.y;
        return yVal < 0 ? COLORS.red : COLORS.green;
    };

    createChart(canvasId, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Avg Return %',
                data: returns,
                borderColor: COLORS.green,
                segment: {
                    borderColor: segmentColor,
                },
                borderWidth: 2,
                tension: 0.3,
                fill: {
                    target: 'origin',
                    above: COLORS.greenGlow,
                    below: 'rgba(255, 51, 102, 0.15)',
                },
                pointRadius: pointRadii,
                pointBackgroundColor: pointColors,
                pointBorderColor: pointColors,
                pointHoverRadius: 7,
            }],
        },
        options: baseOptions({
            scales: {
                x: {
                    title: { display: true, text: 'Min Score Threshold', color: COLORS.text },
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text },
                },
                y: {
                    title: { display: true, text: 'Avg Return %', color: COLORS.text },
                    grid: { color: COLORS.border, drawBorder: false },
                    ticks: { color: COLORS.text, callback: function (v) { return v.toFixed(1) + '%'; } },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: function (items) { return 'Min Score: ' + items[0].label; },
                        label: function (ctx) {
                            var idx = ctx.dataIndex;
                            var ret = returns[idx];
                            var n = counts[idx];
                            var parts = ['Avg Return: ' + (ret != null ? ret.toFixed(2) + '%' : 'N/A'), 'Stocks: ' + n];
                            if (idx === bestIdx) parts.push('*** BEST ***');
                            return parts;
                        },
                    },
                },
                annotation: undefined,
            },
        }),
        plugins: [{
            id: 'bestScoreLine',
            afterDraw: function (chart) {
                if (bestIdx < 0) return;
                var meta = chart.getDatasetMeta(0);
                var point = meta.data[bestIdx];
                if (!point) return;
                var c = chart.ctx;
                var yAxis = chart.scales.y;
                c.save();
                c.strokeStyle = COLORS.amber;
                c.lineWidth = 1;
                c.setLineDash([4, 4]);
                c.beginPath();
                c.moveTo(point.x, yAxis.top);
                c.lineTo(point.x, yAxis.bottom);
                c.stroke();
                c.restore();
            },
        }],
    });
};

window.renderSectorBreakdown = function (canvasId, data) {
    if (!data || data.length === 0) return;

    createChart(canvasId, {
        type: 'doughnut',
        data: {
            labels: data.map((d) => d.sector_etf),
            datasets: [{
                data: data.map((d) => d.count),
                backgroundColor: [COLORS.green, COLORS.cyan, COLORS.amber, COLORS.red, COLORS.accent, '#7c4dff', '#ff6e40', '#64ffda', '#eeff41', '#ff80ab'],
                borderColor: COLORS.bg,
                borderWidth: 2,
            }],
        },
        options: baseOptions({
            plugins: {
                legend: { display: true, position: 'right', labels: { color: COLORS.text, boxWidth: 12, padding: 8, font: { family: "'JetBrains Mono', monospace", size: 10 } } },
                tooltip: { callbacks: { label: (ctx) => { var item = data[ctx.dataIndex]; return item.sector_etf + ': ' + item.count + ' (' + item.pct_of_portfolio + '%)' + (item.avg_return != null ? ' · Avg: ' + item.avg_return.toFixed(1) + '%' : ''); } } },
            },
        }),
    });
};

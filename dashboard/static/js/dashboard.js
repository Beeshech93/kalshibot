// BTC SCALPING AI - Dashboard Controller
let priceChart = null;
let currentTf = '15m';
let currentSpotPrice = 0.0;
let currentStrikePrice = 0.0;
let targetCloseTimestampMs = 0;

document.addEventListener('DOMContentLoaded', () => {
    initChart();
    fetchAllData();
    setInterval(fetchAllData, 3000); // 3s polling for real-time market data
    setInterval(updateLiveCountdown, 1000); // 1s tick for countdown timer

    const triggerBtn = document.getElementById('btn-trigger-cycle');
    if (triggerBtn) {
        triggerBtn.addEventListener('click', triggerManualCycle);
    }
});

function initChart() {
    const ctx = document.getElementById('btcPriceChart').getContext('2d');
    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'BTC Spot ($)',
                    data: [],
                    borderColor: '#f7931a',
                    backgroundColor: 'rgba(247, 147, 26, 0.05)',
                    borderWidth: 2,
                    tension: 0.1,
                    pointRadius: 1,
                    fill: true
                },
                {
                    label: 'EMA 9',
                    data: [],
                    borderColor: '#00e5ff',
                    borderWidth: 1.2,
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'EMA 21',
                    data: [],
                    borderColor: '#ffd600',
                    borderWidth: 1.2,
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'EMA 50',
                    data: [],
                    borderColor: '#ff5252',
                    borderWidth: 1.2,
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'TARGET (To Beat)',
                    data: [],
                    borderColor: '#00e676',
                    borderWidth: 2,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    grid: { color: '#161c28' },
                    ticks: { color: '#687790', maxTicksLimit: 8 }
                },
                y: {
                    grid: { color: '#161c28' },
                    ticks: {
                        color: '#687790',
                        callback: val => '$' + val.toLocaleString()
                    }
                }
            },
            plugins: {
                legend: {
                    labels: { color: '#8a99b5', font: { size: 11 } }
                }
            }
        }
    });
}

async function fetchAllData() {
    try {
        await Promise.all([
            fetchOverview(),
            fetchCandles(),
            fetchIndicators(),
            fetchSignals(),
            fetchMarket(),
            fetchPerformance(),
            fetchLogs()
        ]);
    } catch (err) {
        console.error('Data refresh error:', err);
    }
}

async function fetchOverview() {
    const res = await fetch('/api/overview');
    if (!res.ok) return;
    const data = await res.json();

    if (data.btc_price) {
        currentSpotPrice = data.btc_price;
        document.getElementById('btc-live-price').textContent = '$' + data.btc_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        document.getElementById('mkt-now-price').textContent = '$' + data.btc_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        updateDiffBadge();
    }

    if (data.latest_signal) {
        renderLatestSignal(data.latest_signal);
    }
}

function updateDiffBadge() {
    if (!currentSpotPrice || !currentStrikePrice) return;
    const diff = currentSpotPrice - currentStrikePrice;
    const pct = (diff / currentStrikePrice) * 100;
    const sign = diff >= 0 ? '+' : '';
    const badge = document.getElementById('mkt-diff-badge');
    const nowEl = document.getElementById('mkt-now-price');

    badge.textContent = `${sign}$${diff.toFixed(2)} (${sign}${pct.toFixed(3)}%)`;

    if (diff >= 0) {
        badge.style.color = 'var(--color-yes)';
        nowEl.style.color = 'var(--color-yes)';
    } else {
        badge.style.color = 'var(--color-no)';
        nowEl.style.color = 'var(--color-no)';
    }
}

function updateLiveCountdown() {
    if (!targetCloseTimestampMs) return;
    const now = Date.now();
    const remainingSec = Math.max(0, Math.floor((targetCloseTimestampMs - now) / 1000));
    const mins = Math.floor(remainingSec / 60);
    const secs = remainingSec % 60;
    const formatted = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')} ⏳`;
    const el = document.getElementById('mkt-time-rem');
    if (el) {
        el.textContent = formatted;
        if (remainingSec < 120) {
            el.style.color = 'var(--color-no)';
        } else {
            el.style.color = 'var(--color-btc)';
        }
    }
}

function renderLatestSignal(sig) {
    const banner = document.getElementById('signal-banner');
    if (!banner) return;

    banner.className = `signal-banner sig-${sig.signal_type}`;

    let label = sig.signal_type;
    if (sig.signal_type === 'YES') {
        label = '▲ ALTO (SUBIDA / YES)';
    } else if (sig.signal_type === 'NO') {
        label = '▼ BAJO (BAJADA / NO)';
    } else {
        label = '● ESPERA (WAIT)';
    }

    document.getElementById('sig-type-tag').textContent = label;
    document.getElementById('sig-conf-val').textContent = `${sig.confidence_score.toFixed(1)}%`;
    document.getElementById('sig-justification').textContent = sig.technical_justification || 'Sin justificación técnica disponible.';
    document.getElementById('sig-market-target').textContent = sig.market_ticker || 'N/A';
}

async function fetchCandles() {
    const res = await fetch(`/api/candles?timeframe=${currentTf}&limit=40`);
    if (!res.ok) return;
    const json = await res.json();
    const candles = json.candles || [];

    if (candles.length > 0 && priceChart) {
        const labels = candles.map(c => c.timestamp.substring(11, 16));
        const closes = candles.map(c => c.close);

        priceChart.data.labels = labels;
        priceChart.data.datasets[0].data = closes;

        // Calculate simple on-the-fly EMAs for chart overlay
        priceChart.data.datasets[1].data = calculateEMAArray(closes, 9);
        priceChart.data.datasets[2].data = calculateEMAArray(closes, 21);
        priceChart.data.datasets[3].data = calculateEMAArray(closes, 50);

        // Target / To Beat dashed reference line
        if (currentStrikePrice > 0) {
            priceChart.data.datasets[4].data = labels.map(() => currentStrikePrice);
        } else {
            priceChart.data.datasets[4].data = [];
        }

        priceChart.update();
    }
}

function calculateEMAArray(values, period) {
    if (values.length === 0) return [];
    const k = 2 / (period + 1);
    let ema = values[0];
    const result = [ema];
    for (let i = 1; i < values.length; i++) {
        ema = (values[i] * k) + (ema * (1 - k));
        result.push(ema);
    }
    return result;
}

async function fetchIndicators() {
    const res = await fetch('/api/indicators');
    if (!res.ok) return;
    const data = await res.json();
    const ind15 = data['15m'];
    if (!ind15) return;

    document.getElementById('ind-ema9').textContent = '$' + ind15.ema_9.toLocaleString();
    document.getElementById('ind-ema21').textContent = '$' + ind15.ema_21.toLocaleString();
    document.getElementById('ind-ema50').textContent = '$' + ind15.ema_50.toLocaleString();
    document.getElementById('ind-rsi').textContent = ind15.rsi_14.toFixed(1);
    document.getElementById('ind-macd').textContent = ind15.macd_histogram.toFixed(2);
    document.getElementById('ind-vol-conf').textContent = ind15.volume_confirmed ? 'Confirmado' : 'Bajo';
    if (ind15.volume_abnormal) {
        document.getElementById('ind-vol-conf').textContent += ' (ANORMAL)';
        document.getElementById('ind-vol-conf').style.color = '#ffd600';
    } else {
        document.getElementById('ind-vol-conf').style.color = ind15.volume_confirmed ? '#00e676' : '#8a99b5';
    }
}

async function fetchMarket() {
    const res = await fetch('/api/market');
    if (!res.ok) return;
    const data = await res.json();
    const m = data.market;

    if (m) {
        document.getElementById('mkt-title').textContent = m.title || 'BTC 15 min';
        document.getElementById('mkt-ticker').textContent = m.ticker;

        if (m.strike_price) {
            currentStrikePrice = m.strike_price;
            document.getElementById('mkt-to-beat').textContent = '$' + m.strike_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            updateDiffBadge();
        }

        if (m.close_time) {
            targetCloseTimestampMs = new Date(m.close_time).getTime();
            updateLiveCountdown();
        }

        document.getElementById('mkt-yes-price').textContent = m.yes_ask !== null ? `${Math.round(m.yes_ask)}¢` : '--';
        document.getElementById('mkt-no-price').textContent = m.no_ask !== null ? `${Math.round(m.no_ask)}¢` : '--';
        document.getElementById('mkt-status').textContent = (m.status || 'ACTIVE').toUpperCase();
    } else {
        document.getElementById('mkt-title').textContent = 'Sin contrato activo actualmente';
        document.getElementById('mkt-ticker').textContent = 'Consultando Kalshi API...';
    }
}

async function fetchSignals() {
    const res = await fetch('/api/signals?limit=15');
    if (!res.ok) return;
    const data = await res.json();
    const tbody = document.getElementById('signals-tbody');
    tbody.innerHTML = '';

    (data.signals || []).forEach(sig => {
        const tr = document.createElement('tr');
        const timeStr = sig.timestamp.replace('T', ' ').substring(5, 19);
        const btcFmt = '$' + Number(sig.btc_price).toLocaleString(undefined, {maximumFractionDigits: 0});
        
        let badgeHtml = '';
        if (sig.signal_type === 'YES') {
            badgeHtml = '<span class="badge badge-yes">▲ ALTO (YES)</span>';
        } else if (sig.signal_type === 'NO') {
            badgeHtml = '<span class="badge badge-no">▼ BAJO (NO)</span>';
        } else {
            badgeHtml = '<span class="badge badge-wait">● ESPERA</span>';
        }

        const outcomeBadge = getOutcomeBadge(sig.post_outcome);

        tr.innerHTML = `
            <td>#${sig.id}</td>
            <td style="font-family: var(--font-mono);">${timeStr}</td>
            <td style="font-family: var(--font-mono);">${sig.market_ticker}</td>
            <td style="font-family: var(--font-mono);">${btcFmt}</td>
            <td>${badgeHtml}</td>
            <td style="font-family: var(--font-mono); font-weight:600;">${sig.confidence_score.toFixed(0)}%</td>
            <td>${outcomeBadge}</td>
            <td style="color: var(--text-muted); font-size: 0.75rem; max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${sig.technical_justification}">
                ${sig.technical_justification}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function getOutcomeBadge(outcome) {
    if (outcome === 'WIN') return '<span class="badge badge-win">WIN</span>';
    if (outcome === 'LOSS') return '<span class="badge badge-loss">LOSS</span>';
    return '<span class="badge badge-pending">PENDIENTE</span>';
}

async function fetchPerformance() {
    const res = await fetch('/api/performance');
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById('stat-total-signals').textContent = data.total_signals;
    document.getElementById('stat-yes-signals').textContent = data.yes_signals;
    document.getElementById('stat-no-signals').textContent = data.no_signals;
    document.getElementById('stat-wait-signals').textContent = data.wait_signals;
    document.getElementById('stat-wins').textContent = data.wins;
    document.getElementById('stat-losses').textContent = data.losses;
    document.getElementById('stat-pending').textContent = data.pending_evaluations;
    document.getElementById('stat-winrate').textContent = `${data.win_rate_percent.toFixed(1)}%`;
}

async function fetchLogs() {
    const res = await fetch('/api/logs');
    if (!res.ok) return;
    const data = await res.json();
    const container = document.getElementById('logs-container');
    container.innerHTML = '';

    (data.logs || []).slice(0, 15).forEach(l => {
        const div = document.createElement('div');
        div.className = 'log-entry';
        const time = l.timestamp.substring(11, 19);
        div.innerHTML = `
            <span class="log-time">[${time}]</span>
            <span class="log-${l.level}">[${l.level}]</span>
            <span>(${l.module}): ${l.message}</span>
        `;
        container.appendChild(div);
    });
}

async function triggerManualCycle() {
    const btn = document.getElementById('btn-trigger-cycle');
    btn.disabled = true;
    btn.textContent = 'Analizando...';
    try {
        const res = await fetch('/api/trigger_cycle', { method: 'POST' });
        const json = await res.json();
        alert(json.message || 'Ciclo completado.');
        fetchAllData();
    } catch (e) {
        alert('Error ejecutando ciclo: ' + e);
    } finally {
        btn.disabled = false;
        btn.textContent = '⚡ Analizar Ahora';
    }
}


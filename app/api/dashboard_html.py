DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="da" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrackAnything | OpsCenter</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace'],
                    },
                    colors: {
                        gray: {
                            850: '#1f2937',
                            900: '#111827',
                            950: '#030712',
                        },
                        brand: {
                            500: '#3b82f6',
                            600: '#2563eb',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #030712; color: #f3f4f6; } /* gray-950 */
        .glass-panel {
            background: rgba(31, 41, 55, 0.4);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        .stat-value { font-family: 'JetBrains Mono', monospace; letter-spacing: -0.05em; }
        .chart-container { position: relative; height: 100%; width: 100%; }
    </style>
</head>
<body class="min-h-screen font-sans antialiased selection:bg-brand-500 selection:text-white pb-12">
    
    <!-- Top Bar -->
    <div class="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex h-16 items-center justify-between">
                <div class="flex items-center gap-3">
                    <div class="h-8 w-8 rounded-lg bg-gradient-to-br from-brand-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-brand-500/20">
                        <svg class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                    </div>
                    <div>
                        <h1 class="text-lg font-bold tracking-tight text-white">TrackAnything <span class="text-gray-500 font-normal">| OpsCenter</span></h1>
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <div class="hidden md:flex items-center px-3 py-1 rounded-full bg-gray-800/50 border border-gray-700/50">
                        <div class="w-2 h-2 rounded-full bg-green-500 animate-pulse mr-2"></div>
                        <span class="text-xs font-medium text-gray-300">System Healthy</span>
                    </div>
                    <button onclick="updateData()" class="group relative inline-flex items-center justify-center rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 focus:ring-offset-gray-900 transition-all active:scale-95">
                        <svg class="mr-2 -ml-1 h-4 w-4 animate-spin hidden group-hover:block" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <svg class="mr-2 -ml-1 h-4 w-4 group-hover:hidden" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        Refresh
                    </button>
                </div>
            </div>
        </div>
    </div>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        
        <!-- KPI Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <!-- Total Runs -->
            <div class="glass-panel rounded-xl p-6 relative overflow-hidden group hover:border-brand-500/30 transition-colors">
                <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <svg class="h-16 w-16 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </div>
                <p class="text-sm font-medium text-gray-400">Total Scrape Runs</p>
                <p class="mt-2 text-3xl font-bold text-white stat-value" id="stat-total-runs">-</p>
                <div class="mt-4 flex items-center text-xs text-green-400">
                    <span class="flex items-center">
                        <svg class="h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
                        Active
                    </span>
                    <span class="text-gray-500 mx-2">•</span>
                    <span class="text-gray-500">All providers</span>
                </div>
            </div>

            <!-- Articles Found -->
            <div class="glass-panel rounded-xl p-6 relative overflow-hidden group hover:border-emerald-500/30 transition-colors">
                <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <svg class="h-16 w-16 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
                    </svg>
                </div>
                <p class="text-sm font-medium text-gray-400">Articles Found</p>
                <p class="mt-2 text-3xl font-bold text-white stat-value" id="stat-total-articles">-</p>
                <div class="mt-4 flex items-center text-xs text-emerald-400">
                    <span class="flex items-center">
                        Successful Extractions
                    </span>
                </div>
            </div>

            <!-- Error Rate -->
            <div class="glass-panel rounded-xl p-6 relative overflow-hidden group hover:border-red-500/30 transition-colors">
                <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <svg class="h-16 w-16 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                </div>
                <p class="text-sm font-medium text-gray-400">HTTP Errors</p>
                <p class="mt-2 text-3xl font-bold text-white stat-value" id="stat-total-errors">-</p>
                <div class="mt-4 flex items-center text-xs" id="error-rate-container">
                    <!-- JS injects dynamic color/text here -->
                    <span class="text-gray-500">Calculating rate...</span>
                </div>
            </div>

            <!-- Duplicates -->
            <div class="glass-panel rounded-xl p-6 relative overflow-hidden group hover:border-amber-500/30 transition-colors">
                <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <svg class="h-16 w-16 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />
                    </svg>
                </div>
                <p class="text-sm font-medium text-gray-400">Duplicates Filtered</p>
                <p class="mt-2 text-3xl font-bold text-white stat-value" id="stat-duplicates">-</p>
                <div class="mt-4 flex items-center text-xs text-amber-400">
                    Saved resources
                </div>
            </div>
        </div>

        <!-- Charts Row 1 -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Articles Bar Chart -->
            <div class="glass-panel rounded-xl p-6 lg:col-span-2 flex flex-col">
                <div class="flex items-center justify-between mb-6">
                    <h3 class="text-lg font-semibold text-white">Articles by Provider</h3>
                    <select class="bg-gray-800 border-gray-700 text-xs rounded text-gray-400 p-1">
                        <option>All Time</option>
                    </select>
                </div>
                <div class="flex-grow h-72">
                    <canvas id="articlesChart"></canvas>
                </div>
            </div>

            <!-- Status Doughnut -->
            <div class="glass-panel rounded-xl p-6 flex flex-col">
                <h3 class="text-lg font-semibold text-white mb-2">System Health</h3>
                <p class="text-sm text-gray-500 mb-6">Success vs Error distribution across all tasks</p>
                <div class="flex-grow h-64 relative flex items-center justify-center">
                    <canvas id="statusChart"></canvas>
                    <!-- Center Text Overlay -->
                    <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                        <p class="text-3xl font-bold text-white stat-value" id="success-rate-center">-</p>
                        <p class="text-xs text-gray-500 uppercase tracking-widest">Success</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Live Feed / Latency Chart (Mocked history for demo feel) -->
        <div class="glass-panel rounded-xl p-6">
            <div class="flex items-center justify-between mb-4">
                <div>
                    <h3 class="text-lg font-semibold text-white">Live Activity</h3>
                    <p class="text-sm text-gray-500">Real-time scrape event ingestion (client-side accumulation)</p>
                </div>
                <div class="flex items-center gap-2">
                    <span class="flex h-2 w-2 rounded-full bg-red-500 animate-pulse"></span>
                    <span class="text-xs text-gray-400 font-mono">LIVE_STREAM</span>
                </div>
            </div>
            <div class="h-64">
                <canvas id="liveActivityChart"></canvas>
            </div>
        </div>

        <!-- Detailed Table -->
        <div class="glass-panel rounded-xl overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-800 bg-gray-900/30">
                <h3 class="text-lg font-semibold text-white">Provider Breakdown</h3>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm">
                    <thead>
                        <tr class="text-gray-500 border-b border-gray-800 bg-gray-900/20 uppercase text-xs tracking-wider">
                            <th class="px-6 py-3 font-medium">Provider</th>
                            <th class="px-6 py-3 font-medium">Runs</th>
                            <th class="px-6 py-3 font-medium">Articles</th>
                            <th class="px-6 py-3 font-medium">Avg. Articles/Run</th>
                            <th class="px-6 py-3 font-medium text-right">Last Status</th>
                        </tr>
                    </thead>
                    <tbody id="provider-table-body" class="divide-y divide-gray-800/50">
                        <!-- JS content -->
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <script>
        // --- Configuration & Globals ---
        Chart.defaults.color = '#6b7280';
        Chart.defaults.borderColor = '#1f2937';
        Chart.defaults.font.family = "'Inter', sans-serif";
        
        let articlesChart, statusChart, liveActivityChart;
        // Store historical data points for the live chart
        const liveHistory = {
            labels: [],
            data: []
        };
        const MAX_HISTORY_POINTS = 20;

        // --- Core Fetching Logic ---
        async function fetchMetrics() {
            try {
                const response = await fetch('/metrics/scraping');
                if (!response.ok) throw new Error('Network response was not ok');
                const text = await response.text();
                return parsePrometheus(text);
            } catch (error) {
                console.error("Failed to fetch metrics:", error);
                return null;
            }
        }

        function parsePrometheus(text) {
            const lines = text.split('\\n');
            const metrics = {};
            
            lines.forEach(line => {
                if (line.startsWith('#') || !line.trim()) return;
                const match = line.match(/^([a-z0-9_]+)(\\{.*\\})?\\s+([0-9.e+-]+)$/);
                if (!match) return;
                
                const [_, name, labelsStr, value] = match;
                const labels = {};
                if (labelsStr) {
                    const labelMatches = labelsStr.matchAll(/([a-z0-9_]+)="([^"]*)"/g);
                    for (const lm of labelMatches) {
                        labels[lm[1]] = lm[2];
                    }
                }
                
                if (!metrics[name]) metrics[name] = [];
                metrics[name].push({ labels, value: parseFloat(value) });
            });
            return metrics;
        }

        // --- Update UI ---
        async function updateData() {
            const data = await fetchMetrics();
            if (!data) return;

            // 1. Calculate Aggregates
            const totalRuns = (data['scrape_runs_total'] || []).reduce((acc, m) => acc + m.value, 0);
            const totalArticles = (data['scrape_provider_articles_total'] || []).reduce((acc, m) => acc + m.value, 0);
            const totalErrors = (data['scrape_http_errors_total'] || []).reduce((acc, m) => acc + m.value, 0);
            const totalDuplicates = (data['scrape_duplicates_removed_total'] || []).reduce((acc, m) => acc + m.value, 0);

            // 2. Update KPI Cards
            animateValue('stat-total-runs', totalRuns);
            animateValue('stat-total-articles', totalArticles);
            animateValue('stat-total-errors', totalErrors);
            animateValue('stat-duplicates', totalDuplicates);

            // Error Rate Calculation
            const errorRate = totalRuns > 0 ? ((totalErrors / (totalRuns * 5)) * 100) : 0; // heuristic: approx 5 reqs per run
            const errorEl = document.getElementById('error-rate-container');
            if (errorRate < 1) {
                errorEl.innerHTML = `<span class="text-green-400 font-medium">Healthy</span><span class="text-gray-500 ml-2">Low error rate</span>`;
            } else {
                errorEl.innerHTML = `<span class="text-red-400 font-medium">${errorRate.toFixed(1)}%</span><span class="text-gray-500 ml-2">Check logs</span>`;
            }

            // 3. Update Charts
            updateArticlesChart(data['scrape_provider_articles_total'] || []);
            updateStatusChart(data['scrape_runs_total'] || []);
            updateLiveChart(totalRuns); // Use total runs as a proxy for activity

            // 4. Update Table
            updateTable(data);
        }

        function animateValue(id, value) {
            // Simple direct update for now, could add tweening later
            document.getElementById(id).innerText = value.toLocaleString();
        }

        // --- Chart Logic ---

        function updateArticlesChart(metrics) {
            const labels = metrics.map(m => m.labels.provider);
            const values = metrics.map(m => m.value);
            
            // Create Gradient
            const ctx = document.getElementById('articlesChart').getContext('2d');
            let gradient = ctx.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, '#3b82f6'); // brand-500
            gradient.addColorStop(1, '#1e1b4b'); // deep indigo

            if (articlesChart) {
                articlesChart.data.labels = labels;
                articlesChart.data.datasets[0].data = values;
                articlesChart.update();
            } else {
                articlesChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Articles Found',
                            data: values,
                            backgroundColor: gradient,
                            borderRadius: 6,
                            borderWidth: 0,
                            barPercentage: 0.6,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: { grid: { color: 'rgba(255,255,255,0.05)' }, border: { display: false } },
                            x: { grid: { display: false }, border: { display: false } }
                        },
                        plugins: { legend: { display: false } }
                    }
                });
            }
        }

        function updateStatusChart(metrics) {
            const statusMap = {};
            metrics.forEach(m => {
                const s = m.labels.status || 'unknown';
                statusMap[s] = (statusMap[s] || 0) + m.value;
            });
            
            const total = Object.values(statusMap).reduce((a, b) => a + b, 0);
            const successCount = statusMap['success'] || 0;
            const successRate = total > 0 ? Math.round((successCount / total) * 100) : 0;
            
            document.getElementById('success-rate-center').innerText = `${successRate}%`;
            document.getElementById('success-rate-center').className = `text-3xl font-bold stat-value ${successRate > 90 ? 'text-green-400' : 'text-yellow-400'}`;

            const labels = Object.keys(statusMap);
            const data = Object.values(statusMap);
            const colors = labels.map(l => l === 'success' ? '#10b981' : (l === 'error' ? '#ef4444' : '#f59e0b'));

            if (statusChart) {
                statusChart.data.labels = labels;
                statusChart.data.datasets[0].data = data;
                statusChart.data.datasets[0].backgroundColor = colors;
                statusChart.update();
            } else {
                const ctx = document.getElementById('statusChart').getContext('2d');
                statusChart = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: data,
                            backgroundColor: colors,
                            borderWidth: 0,
                            cutout: '75%',
                            hoverOffset: 4
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, padding: 20 } } }
                    }
                });
            }
        }

        function updateLiveChart(currentTotal) {
            const now = new Date().toLocaleTimeString('da-DK', { hour12: false });
            
            // Initial load handling
            if (liveHistory.lastTotal === undefined) {
                liveHistory.lastTotal = currentTotal;
                return; 
            }

            const diff = currentTotal - liveHistory.lastTotal;
            liveHistory.lastTotal = currentTotal;

            liveHistory.labels.push(now);
            liveHistory.data.push(diff);

            if (liveHistory.labels.length > MAX_HISTORY_POINTS) {
                liveHistory.labels.shift();
                liveHistory.data.shift();
            }

            const ctx = document.getElementById('liveActivityChart').getContext('2d');
            
            if (liveActivityChart) {
                liveActivityChart.data.labels = liveHistory.labels;
                liveActivityChart.data.datasets[0].data = liveHistory.data;
                liveActivityChart.update('none'); // 'none' mode for smoother animation
            } else {
                let gradient = ctx.createLinearGradient(0, 0, 0, 300);
                gradient.addColorStop(0, 'rgba(59, 130, 246, 0.5)'); // brand-500 alpha
                gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');

                liveActivityChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: liveHistory.labels,
                        datasets: [{
                            label: 'New Scrapes (30s interval)',
                            data: liveHistory.data,
                            borderColor: '#3b82f6',
                            backgroundColor: gradient,
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#111827',
                            pointBorderColor: '#3b82f6',
                            pointBorderWidth: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                            x: { grid: { display: false } }
                        },
                        plugins: { legend: { display: false } },
                        interaction: { intersect: false, mode: 'index' },
                    }
                });
            }
        }

        function updateTable(data) {
            const providers = (data['scrape_provider_runs_total'] || []);
            const articles = (data['scrape_provider_articles_total'] || []);
            
            const tbody = document.getElementById('provider-table-body');
            tbody.innerHTML = '';
            
            // Get unique provider names
            const providerNames = [...new Set(providers.map(p => p.labels.provider))].sort();

            providerNames.forEach(provName => {
                // Aggregate counts per provider
                const provRuns = providers
                    .filter(p => p.labels.provider === provName)
                    .reduce((a, b) => a + b.value, 0);
                
                const artCount = articles.find(a => a.labels.provider === provName)?.value || 0;
                
                // Determine last status (simple heuristic: if any failure exists, mark warning, else success)
                const hasErrors = providers.some(p => p.labels.provider === provName && p.labels.status !== 'success' && p.value > 0);
                const statusBadge = !hasErrors 
                    ? '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-700/30">Healthy</span>'
                    : '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400 border border-red-700/30">Errors</span>';

                const avg = provRuns > 0 ? (artCount / provRuns).toFixed(1) : '0.0';

                const tr = document.createElement('tr');
                tr.className = 'group hover:bg-gray-800/50 transition-colors';
                tr.innerHTML = `
                    <td class="px-6 py-4 whitespace-nowrap font-medium text-gray-200">${provName}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-gray-400">${provRuns}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-gray-400">${artCount}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-gray-400">${avg}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-right">${statusBadge}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        // --- Init ---
        // Initial fetch
        updateData();
        // Polling interval (30 seconds)
        setInterval(updateData, 30000);
    </script>
</body>
</html>
"""

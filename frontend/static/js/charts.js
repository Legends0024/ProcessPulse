(function() {
    'use strict';

    const COLORS = {
        cpu: '#3b82f6',
        cpuLight: 'rgba(59, 130, 246, 0.15)',
        memory: '#8b5cf6',
        memoryLight: 'rgba(139, 92, 246, 0.15)',
        disk: '#f59e0b',
        diskLight: 'rgba(245, 158, 11, 0.15)',
        grid: 'rgba(255, 255, 255, 0.08)',
        text: 'rgba(255, 255, 255, 0.5)',
        tooltipBg: '#161e2e',
        tooltipBorder: '#2a3a52',
        tooltipText: '#f1f5f9'
    };

    const charts = {};
    let currentTheme = 'dark';

    function updateColorsForTheme(theme) {
        currentTheme = theme;
        if (theme === 'light') {
            COLORS.grid = 'rgba(15, 23, 42, 0.08)';
            COLORS.text = 'rgba(15, 23, 42, 0.5)';
            COLORS.tooltipBg = '#ffffff';
            COLORS.tooltipBorder = '#e2e8f0';
            COLORS.tooltipText = '#0f172a';
        } else {
            COLORS.grid = 'rgba(255, 255, 255, 0.08)';
            COLORS.text = 'rgba(255, 255, 255, 0.5)';
            COLORS.tooltipBg = '#161e2e';
            COLORS.tooltipBorder = '#2a3a52';
            COLORS.tooltipText = '#f1f5f9';
        }
    }

    function getCommonOptions(title) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: COLORS.tooltipBg,
                    borderColor: COLORS.tooltipBorder,
                    borderWidth: 1,
                    titleColor: COLORS.tooltipText,
                    bodyColor: COLORS.tooltipText,
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: true,
                    usePointStyle: true
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: COLORS.text, font: { size: 11 } }
                },
                y: {
                    grid: { color: COLORS.grid },
                    ticks: { color: COLORS.text, font: { size: 11 }, stepSize: 20 },
                    min: 0,
                    max: 100
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            animation: {
                duration: 300,
                easing: 'easeOutQuart'
            }
        };
    }

    function createGradient(ctx, color, lightColor) {
        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, lightColor);
        gradient.addColorStop(1, 'rgba(0,0,0,0)');
        return gradient;
    }

    function createLineDataset(label, color, lightColor, data, options = {}) {
        return {
            label,
            data,
            borderColor: color,
            backgroundColor: (ctx) => createGradient(ctx.chart.ctx, color, lightColor),
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: color,
            pointHoverBorderColor: '#fff',
            pointHoverBorderWidth: 2,
            ...options
        };
    }

    function initChart(canvasId, config) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return null;

        const ctx = canvas.getContext('2d');
        const chart = new Chart(ctx, config);
        charts[canvasId] = chart;
        return chart;
    }

    function updateChart(canvasId, data, labels) {
        const chart = charts[canvasId];
        if (!chart) return;

        if (labels) chart.data.labels = labels;
        if (data) {
            if (Array.isArray(data[0])) {
                data.forEach((d, i) => {
                    if (chart.data.datasets[i]) chart.data.datasets[i].data = d;
                });
            } else {
                chart.data.datasets[0].data = data;
            }
        }
        chart.update('none');
    }

    function destroyChart(canvasId) {
        const chart = charts[canvasId];
        if (chart) {
            chart.destroy();
            delete charts[canvasId];
        }
    }

    function destroyAllCharts() {
        Object.keys(charts).forEach(destroyChart);
    }

    function createOverviewCharts() {
        initChart('cpuHistoryChart', {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    createLineDataset('CPU %', COLORS.cpu, COLORS.cpuLight, [])
                ]
            },
            options: getCommonOptions()
        });

        initChart('memoryHistoryChart', {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    createLineDataset('Memory %', COLORS.memory, COLORS.memoryLight, [])
                ]
            },
            options: getCommonOptions()
        });
    }

    function createLiveCharts() {
        initChart('liveCpuChart', {
            type: 'line',
            data: { labels: [], datasets: [createLineDataset('CPU', COLORS.cpu, COLORS.cpuLight, [], { borderWidth: 1.5 })] },
            options: { ...getCommonOptions(), plugins: { legend: { display: false }, tooltip: { enabled: false } }, scales: { x: { display: false }, y: { display: false, min: 0, max: 100 } }, elements: { point: { radius: 0 } } }
        });

        initChart('liveMemoryChart', {
            type: 'line',
            data: { labels: [], datasets: [createLineDataset('Memory', COLORS.memory, COLORS.memoryLight, [], { borderWidth: 1.5 })] },
            options: { ...getCommonOptions(), plugins: { legend: { display: false }, tooltip: { enabled: false } }, scales: { x: { display: false }, y: { display: false, min: 0, max: 100 } }, elements: { point: { radius: 0 } } }
        });

        initChart('liveDiskChart', {
            type: 'line',
            data: { labels: [], datasets: [createLineDataset('Disk', COLORS.disk, COLORS.diskLight, [], { borderWidth: 1.5 })] },
            options: { ...getCommonOptions(), plugins: { legend: { display: false }, tooltip: { enabled: false } }, scales: { x: { display: false }, y: { display: false, min: 0, max: 100 } }, elements: { point: { radius: 0 } } }
        });

        initChart('liveTrendsChart', {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    createLineDataset('CPU %', COLORS.cpu, COLORS.cpuLight, []),
                    createLineDataset('Memory %', COLORS.memory, COLORS.memoryLight, []),
                    createLineDataset('Disk %', COLORS.disk, COLORS.diskLight, [])
                ]
            },
            options: getCommonOptions()
        });
    }

    function createHistoryCharts() {
        initChart('historyCpuChart', {
            type: 'line',
            data: { labels: [], datasets: [createLineDataset('CPU %', COLORS.cpu, COLORS.cpuLight, [])] },
            options: getCommonOptions()
        });

        initChart('historyMemoryChart', {
            type: 'line',
            data: { labels: [], datasets: [createLineDataset('Memory %', COLORS.memory, COLORS.memoryLight, [])] },
            options: getCommonOptions()
        });

        initChart('historyDiskChart', {
            type: 'line',
            data: { labels: [], datasets: [createLineDataset('Disk %', COLORS.disk, COLORS.diskLight, [])] },
            options: getCommonOptions()
        });
    }

    function updateOverviewCharts(metrics) {
        if (!metrics || !metrics.length) {
            updateChart('cpuHistoryChart', [], []);
            updateChart('memoryHistoryChart', [], []);
            return;
        }

        const labels = metrics.map(m => new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        const cpuData = metrics.map(m => m.cpu_percent);
        const memData = metrics.map(m => m.memory_percent);

        updateChart('cpuHistoryChart', [cpuData], labels);
        updateChart('memoryHistoryChart', [memData], labels);
    }

    function updateLiveCharts(metric) {
        if (!metric) return;

        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

        ['liveCpuChart', 'liveMemoryChart', 'liveDiskChart'].forEach(id => {
            const chart = charts[id];
            if (chart) {
                if (chart.data.labels.length > 30) {
                    chart.data.labels.shift();
                    chart.data.datasets[0].data.shift();
                }
                chart.data.labels.push(time);
            }
        });

        const cpuChart = charts['liveCpuChart'];
        if (cpuChart) cpuChart.data.datasets[0].data.push(metric.cpu_percent);
        cpuChart?.update('none');

        const memChart = charts['liveMemoryChart'];
        if (memChart) memChart.data.datasets[0].data.push(metric.memory_percent);
        memChart?.update('none');

        const diskChart = charts['liveDiskChart'];
        if (diskChart) diskChart.data.datasets[0].data.push(metric.disk_percent);
        diskChart?.update('none');

        const trendsChart = charts['liveTrendsChart'];
        if (trendsChart) {
            if (trendsChart.data.labels.length > 60) {
                trendsChart.data.labels.shift();
                trendsChart.data.datasets.forEach(d => d.data.shift());
            }
            trendsChart.data.labels.push(time);
            trendsChart.data.datasets[0].data.push(metric.cpu_percent);
            trendsChart.data.datasets[1].data.push(metric.memory_percent);
            trendsChart.data.datasets[2].data.push(metric.disk_percent);
            trendsChart.update('none');
        }
    }

    function updateHistoryCharts(metrics) {
        if (!metrics || !metrics.length) {
            updateChart('historyCpuChart', [], []);
            updateChart('historyMemoryChart', [], []);
            updateChart('historyDiskChart', [], []);
            return;
        }

        const labels = metrics.map(m => new Date(m.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }));
        const cpuData = metrics.map(m => m.cpu_percent);
        const memData = metrics.map(m => m.memory_percent);
        const diskData = metrics.map(m => m.disk_percent);

        updateChart('historyCpuChart', [cpuData], labels);
        updateChart('historyMemoryChart', [memData], labels);
        updateChart('historyDiskChart', [diskData], labels);
    }

    window.ChartManager = {
        initOverview: createOverviewCharts,
        initLive: createLiveCharts,
        initHistory: createHistoryCharts,
        updateOverview: updateOverviewCharts,
        updateLive: updateLiveCharts,
        updateHistory: updateHistoryCharts,
        destroyAll: destroyAllCharts,
        updateColors: updateColorsForTheme,
        charts: () => charts
    };

    window.addEventListener('themechange', (e) => {
        updateColorsForTheme(e.detail.theme);
        Object.values(charts).forEach(chart => {
            chart.options.scales.y.grid.color = COLORS.grid;
            chart.options.scales.x.ticks.color = COLORS.text;
            chart.options.scales.y.ticks.color = COLORS.text;
            chart.options.plugins.tooltip.backgroundColor = COLORS.tooltipBg;
            chart.options.plugins.tooltip.borderColor = COLORS.tooltipBorder;
            chart.options.plugins.tooltip.titleColor = COLORS.tooltipText;
            chart.options.plugins.tooltip.bodyColor = COLORS.tooltipText;
            chart.update();
        });
    });
})();
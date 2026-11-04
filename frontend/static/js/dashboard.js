(function() {
    'use strict';

    let refreshTimer = null;
    let currentProcesses = [];
    let selectedDeviceId = localStorage.getItem('processpulse-device') || '';
    const protectedProcessNames = new Set([
        'system', 'system idle process', 'registry', 'smss.exe', 'csrss.exe',
        'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe',
        'fontdrvhost.exe', 'dwm.exe', 'taskhostw.exe', 'explorer.exe',
        'winlogon.exe', 'spoolsv.exe', 'searchindexer.exe', 'sihost.exe',
        'taskhost.exe'
    ]);

    document.addEventListener('DOMContentLoaded', function() {
        initDashboard();
    });

    function initDashboard() {
        initCharts();
        loadInitialData();
        setupEventListeners();
        const savedInterval = Number(localStorage.getItem('processpulse-refresh-interval')) || 5000;
        const refreshControl = document.getElementById('refreshInterval');
        const settingsRefreshControl = document.getElementById('monitoringInterval');
        if (refreshControl) refreshControl.value = String(savedInterval);
        if (settingsRefreshControl) settingsRefreshControl.value = String(savedInterval);
        setupAutoRefresh(savedInterval);
    }
    const adminTokenControl = document.getElementById('adminToken');
    if (adminTokenControl) {
        adminTokenControl.value = localStorage.getItem('processpulse-admin-token') || '';
        adminTokenControl.addEventListener('change', () => {
            localStorage.setItem('processpulse-admin-token', adminTokenControl.value.trim());
        });
    }

    function initCharts() {
        if (window.ChartManager) {
            window.ChartManager.initOverview();
            window.ChartManager.initLive();
            window.ChartManager.initHistory();
        }
    }

    async function loadDashboardData() {
        try {
            const latest = await fetch('/api/latest');
            const data = await latest.json();

            if (window.ChartManager) {
                window.ChartManager.updateOverview(data.metric ? [data.metric] : []);
            }

            if (window.ChartManager) {
                window.ChartManager.updateLive(data.metric);
            }

            if (data.health_score !== undefined) {
                updateHealthScore(data.health_score);
            }

            if (data.analysis) {
                updateAnomalyStatus(data.analysis);
            }

            if (data.device && data.device.name) {
                document.getElementById('selectedDevice').textContent = data.device.name;
                document.getElementById('deviceIdDisplay').textContent = data.device.device_id || '--';
            }
        } catch (error) {
            console.error('Error loading dashboard data:', error);
        }
    }

    function setupEventListeners() {
        document.querySelectorAll('.nav-link[data-section]').forEach((link) => {
            link.addEventListener('click', (event) => {
                event.preventDefault();
                switchSection(link.dataset.section);
                updateNavActive(link);
                const title = document.getElementById('pageTitle');
                if (title) title.textContent = link.textContent.trim();
            });
        });

        const refreshButton = document.getElementById('refreshOverview');
        if (refreshButton) {
            refreshButton.addEventListener('click', async () => {
                refreshButton.disabled = true;
                try {
                    await loadInitialData();
                    showToast('Dashboard refreshed', 'success');
                } finally {
                    refreshButton.disabled = false;
                }
            });
        }

        const refreshControl = document.getElementById('refreshInterval');
        if (refreshControl) {
            refreshControl.addEventListener('change', () => {
                setupAutoRefresh(Number(refreshControl.value) || 5000);
            });
        }
        const settingsRefreshControl = document.getElementById('monitoringInterval');
        if (settingsRefreshControl) {
            settingsRefreshControl.addEventListener('change', () => {
                localStorage.setItem('processpulse-refresh-interval', settingsRefreshControl.value);
                setupAutoRefresh(Number(settingsRefreshControl.value) || 5000);
            });
        }

        const processSearch = document.getElementById('processSearch');
        const processSort = document.getElementById('processSort');
        const processFilter = document.getElementById('processFilter');
        [processSearch, processSort, processFilter].forEach((control) => {
            if (control) control.addEventListener('input', () => renderProcessTable());
            if (control) control.addEventListener('change', () => renderProcessTable());
        });

        const historyRange = document.getElementById('historyRange');
        if (historyRange) {
            historyRange.addEventListener('change', async () => {
                try {
                    const response = await fetch(`/api/history?hours=${encodeURIComponent(historyRange.value)}`);
                    if (!response.ok) throw new Error('Unable to load history');
                    const data = await response.json();
                    if (window.ChartManager) window.ChartManager.updateHistory(data.metrics || []);
                    await fetchResourcePatterns();
                } catch (error) {
                    showErrorNotification(error.message);
                }
            });
        }

        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebar = document.getElementById('sidebar');

        if (sidebarToggle && sidebar) {
            sidebarToggle.addEventListener('click', () => {
                sidebar.classList.toggle('open');
                const expanded = sidebarToggle.getAttribute('aria-expanded') === 'true';
                sidebarToggle.setAttribute('aria-expanded', !expanded);
            });
        }

        const deviceSelector = document.getElementById('deviceSelector');
        const deviceList = document.getElementById('deviceList');

        if (deviceSelector && deviceList) {
            loadDevices(deviceList, deviceSelector);
            deviceSelector.addEventListener('click', (e) => {
                if (e.target.closest('.device-btn')) {
                    deviceList.classList.toggle('show');
                    deviceSelector.querySelector('.device-btn').setAttribute('aria-expanded', deviceList.classList.contains('show') ? 'true' : 'false');
                }
            });

            document.addEventListener('click', (e) => {
                const isClickInside = deviceSelector.contains(e.target) || deviceList.contains(e.target);
                if (!isClickInside && deviceList.classList.contains('show')) {
                    deviceList.classList.remove('show');
                    deviceSelector.querySelector('.device-btn').setAttribute('aria-expanded', 'false');
                }
            });
        }

        const clearDataBtn = document.getElementById('clearDataBtn');
        if (clearDataBtn) {
            clearDataBtn.addEventListener('click', async () => {
                showConfirmModal({
                    title: 'Clear All Local Data',
                    message: 'This will clear all locally stored monitoring data. This action cannot be undone. Continue?',
                    confirmText: 'Clear Data',
                    cancelText: 'Cancel',
                    onConfirm: clearDataConfirmed
                });
            });
        }

        function clearDataConfirmed() {
            localStorage.removeItem('processpulse-theme');
            localStorage.removeItem('agent_token');
            localStorage.removeItem('device-selection');
            showToast('Local data cleared', 'success');
        }
    }

    function switchSection(sectionId) {
        const sections = document.querySelectorAll('.dashboard-section');
        sections.forEach(section => {
            section.classList.toggle('active', section.id === `${sectionId}-section`);
        });
    }

    function updateNavActive(activeLink) {
        const navLinks = document.querySelectorAll('.nav-link');
        navLinks.forEach(link => link.classList.remove('active'));
        activeLink.classList.add('active');
    }

    async function loadInitialData() {
        try {
            await Promise.all([
                fetchCurrentMetrics(),
                fetchHistory(),
                fetchConnectionStatus(),
                fetchResourcePatterns()
            ]);
        } catch (error) {
            console.error('Failed to load initial data:', error);
            showErrorNotification(error.message || 'Failed to load data from server');
        }
    }

    async function fetchCurrentMetrics() {
        try {
            const response = await fetch('/api/latest', {
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (response.status === 404) {
                showNoDeviceState();
                return;
            }
            if (!response.ok) throw new Error(`Server returned HTTP ${response.status}`);

            const data = await response.json();
            if (data.device) {
                selectedDeviceId = data.device.device_id || selectedDeviceId;
                localStorage.setItem('processpulse-device', selectedDeviceId);
                updateDeviceDisplay(data.device);
            }
            updateMetricsDisplay(data.metric || {});
            updateProcessTable(data.processes || []);
            updateHealthScore(data.health_score);
            updateAnomalyStatus(data.analysis);
            const lastUpdated = document.getElementById('lastUpdated');
            if (lastUpdated) lastUpdated.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
        } catch (error) {
            console.error('Error fetching metrics:', error);
            throw error;
        }
    }

    function showNoDeviceState() {
        const selected = document.getElementById('selectedDevice');
        const deviceId = document.getElementById('deviceIdDisplay');
        const lastUpdated = document.getElementById('lastUpdated');
        if (selected) selected.textContent = 'No device connected';
        if (deviceId) deviceId.textContent = '--';
        if (lastUpdated) lastUpdated.textContent = 'Waiting for monitoring agent';
        updateMetricsDisplay({
            cpu_percent: null,
            memory_percent: null,
            disk_percent: null,
            gpu: { available: false }
        });
        updateProcessTable([]);
        updateHealthScore(null);
        updateAnomalyStatus(null);
    }

    function updateMetricsDisplay(metric) {
        if (!metric) return;

        document.getElementById('liveCpu').textContent = metric.cpu_percent == null ? '--' : `${metric.cpu_percent}%`;
        document.getElementById('liveMemory').textContent = metric.memory_percent == null ? '--' : `${metric.memory_percent}%`;
        document.getElementById('liveDisk').textContent = metric.disk_percent == null ? '--' : `${metric.disk_percent}%`;

        const cpuBar = document.getElementById('cpuBar');
        if (cpuBar) cpuBar.style.width = `${metric.cpu_percent}%`;

        const memoryBar = document.getElementById('memoryBar');
        if (memoryBar) memoryBar.style.width = `${metric.memory_percent}%`;

        const diskBar = document.getElementById('diskBar');
        if (diskBar) diskBar.style.width = `${metric.disk_percent}%`;

        const gpu = metric.gpu || {};
        const gpuValue = document.getElementById('liveGpu');
        const gpuDetails = document.getElementById('gpuDetails');
        const gpuBar = document.getElementById('gpuBar');
        if (gpu.available && Number.isFinite(Number(gpu.utilization_percent))) {
            const utilization = Number(gpu.utilization_percent);
            if (gpuValue) gpuValue.textContent = `${utilization.toFixed(1)}%`;
            if (gpuDetails) {
                const memory = Number.isFinite(Number(gpu.memory_percent))
                    ? `Memory ${Number(gpu.memory_percent).toFixed(1)}%`
                    : 'Memory unavailable';
                gpuDetails.textContent = `${gpu.name || 'GPU'} · ${memory}`;
            }
            if (gpuBar) gpuBar.style.width = `${Math.max(0, Math.min(100, utilization))}%`;
        } else {
            if (gpuValue) gpuValue.textContent = 'N/A';
            if (gpuDetails) gpuDetails.textContent = 'No supported GPU detected';
            if (gpuBar) gpuBar.style.width = '0%';
        }
    }

    function updateProcessTable(processes) {
        currentProcesses = Array.isArray(processes) ? processes : [];
        renderProcessTable();
    }

    function renderProcessTable() {
        const tableBody = document.getElementById('processTableBody');
        const emptyState = document.getElementById('processEmptyState');

        if (!tableBody) return;

        const search = (document.getElementById('processSearch')?.value || '').trim().toLowerCase();
        const sort = document.getElementById('processSort')?.value || 'cpu_percent';
        const filter = document.getElementById('processFilter')?.value || '';
        const filtered = currentProcesses.filter((proc) => {
            const name = String(proc.name || '').toLowerCase();
            if (search && !name.includes(search) && !String(proc.pid).includes(search)) return false;
            if (filter === 'high_cpu' && Number(proc.cpu_percent) <= 25) return false;
            if (filter === 'high_memory' && Number(proc.memory_percent) <= 25) return false;
            return true;
        });
        const sorted = filtered.sort((a, b) => {
            const left = a[sort];
            const right = b[sort];
            return typeof left === 'string'
                ? String(left).localeCompare(String(right))
                : (Number(right) || 0) - (Number(left) || 0);
        }).slice(0, 50);

        if (sorted.length === 0) {
            if (emptyState) emptyState.hidden = false;
            tableBody.replaceChildren();
            const processCount = document.getElementById('processCount');
            if (processCount) processCount.textContent = '0 processes';
            return;
        }

        if (emptyState) emptyState.hidden = true;

        tableBody.replaceChildren();
        sorted.forEach((proc) => {
            const row = document.createElement('tr');
            const name = proc.name || 'Unknown';
            const cpu = Number(proc.cpu_percent) || 0;
            const memory = Number(proc.memory_percent) || 0;
            const memoryUsed = Number(proc.memory_used) || 0;
            const protectedProcess = Number(proc.pid) === 0
                || Number(proc.pid) === 4
                || protectedProcessNames.has(name.toLowerCase());
            row.innerHTML = `
                <td class="process-name"></td>
                <td class="process-pid"></td>
                <td class="process-cpu"></td>
                <td class="process-memory"></td>
                <td></td>
                <td class="process-status running"></td>
                <td><button class="action-btn" type="button" title="${protectedProcess ? 'Protected system process' : 'Terminate process'}"${protectedProcess ? ' disabled' : ''}>${protectedProcess ? 'Protected' : 'Terminate'}</button></td>
            `;
            row.children[0].textContent = name;
            row.children[0].title = name;
            row.children[1].textContent = proc.pid ?? 'N/A';
            row.children[2].textContent = `${cpu.toFixed(1)}%`;
            row.children[2].classList.toggle('high', cpu > 75);
            row.children[2].classList.toggle('medium', cpu > 50 && cpu <= 75);
            row.children[3].textContent = `${memory.toFixed(1)}%`;
            row.children[3].classList.toggle('high', memory > 75);
            row.children[3].classList.toggle('medium', memory > 50 && memory <= 75);
            row.children[4].textContent = `${(memoryUsed / 1024 / 1024).toFixed(1)} MB`;
            row.children[5].textContent = proc.status || 'unknown';
            row.querySelector('.action-btn').dataset.pid = proc.pid;
            row.querySelector('.action-btn').dataset.name = name;
            row.querySelector('.action-btn').dataset.protected = protectedProcess ? 'true' : 'false';
            tableBody.appendChild(row);
        });
        const processCount = document.getElementById('processCount');
        if (processCount) processCount.textContent = `${sorted.length} processes`;

        attachProcessButtonListeners();
    }

    function attachProcessButtonListeners() {
        document.querySelectorAll('.action-btn[data-pid]').forEach(btn => {
            if (btn.disabled) return;
            btn.addEventListener('click', (e) => {
                const pid = btn.getAttribute('data-pid');
                const name = btn.getAttribute('data-name');
                showConfirmModal({
                    title: 'Terminate Process',
                    message: `Terminate ${name} (PID ${pid})? This action cannot be undone.`,
                    confirmText: 'Terminate',
                    cancelText: 'Cancel',
                    onConfirm: () => terminateProcess(pid)
                });
            });
        });
    }

    async function terminateProcess(pid) {
        try {
            const response = await fetch(`/api/processes/${pid}/terminate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-Admin-Token': localStorage.getItem('processpulse-admin-token') || ''
                },
                body: JSON.stringify({ name: document.querySelector(`[data-pid="${pid}"]`)?.dataset.name || '' })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to request process termination');
            }
            showToast(`Process termination requested for PID ${pid}`, 'success');
        } catch (error) {
            console.error('Error terminating process:', error);
            const message = error instanceof TypeError && error.message === 'Failed to fetch'
                ? 'Backend is not running. Start app.py and try again.'
                : (error.message || 'Error communicating with backend');
            showToast(message, 'error');
            return false;
        }
    }

    async function fetchProcessList() {
        try {
            const response = await fetch('/api/processes?limit=20&sort=cpu_percent&order=desc', {
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const data = await response.json();
            updateProcessTable(data.processes || []);
        } catch (error) {
            console.error('Error fetching processes:', error);
        }
    }

    async function fetchHistory() {
        const range = document.getElementById('historyRange')?.value || '24';
        try {
            const query = `/api/history?hours=${encodeURIComponent(range)}${selectedDeviceId ? `&device_id=${encodeURIComponent(selectedDeviceId)}` : ''}`;
            const response = await fetch(query);
            if (!response.ok) throw new Error('Unable to load metric history');
            const data = await response.json();
            if (window.ChartManager) {
                window.ChartManager.updateOverview(data.metrics || []);
                window.ChartManager.updateHistory(data.metrics || []);
            }
        } catch (error) {
            console.error('Error fetching history:', error);
            showErrorNotification(error.message);
        }
    }

    async function fetchResourcePatterns() {
        const range = document.getElementById('historyRange')?.value || '24';
        try {
            const query = `/api/patterns?hours=${encodeURIComponent(range)}${selectedDeviceId ? `&device_id=${encodeURIComponent(selectedDeviceId)}` : ''}`;
            const response = await fetch(query);
            if (!response.ok) throw new Error('Unable to load resource patterns');
            updateResourcePatterns(await response.json());
        } catch (error) {
            console.error('Error fetching resource patterns:', error);
            updateResourcePatterns({ status: 'error', message: error.message });
        }
    }

    function updateResourcePatterns(data) {
        const summary = document.getElementById('patternSummary');
        const status = document.getElementById('patternStatus');
        const patternList = document.getElementById('patternList');
        const processList = document.getElementById('patternProcesses');
        if (!summary || !status || !patternList || !processList) return;
        status.textContent = data.status === 'analyzed' ? 'Analyzed' : 'Waiting';
        patternList.replaceChildren();
        processList.replaceChildren();
        if (data.status !== 'analyzed') {
            summary.textContent = data.message || 'Pattern analysis is unavailable.';
            patternList.innerHTML = '<li>Not enough historical data yet.</li>';
            processList.innerHTML = '<li>Process ranking will appear after metrics arrive.</li>';
            return;
        }
        summary.textContent = `${data.sample_count} samples analyzed over the last ${data.period_hours} hours.`;
        if (!data.patterns.length) {
            patternList.innerHTML = '<li>No significant increasing resource pattern detected.</li>';
        } else {
            data.patterns.forEach((pattern) => {
                const item = document.createElement('li');
                item.textContent = `${pattern.message} Peak ${pattern.peak_percent.toFixed(1)}%.`;
                patternList.appendChild(item);
            });
        }
        if (!data.top_processes.length) {
            processList.innerHTML = '<li>No process samples available.</li>';
        } else {
            data.top_processes.forEach((process) => {
                const item = document.createElement('li');
                item.textContent = `${process.name} (PID ${process.pid}) · ${Number(process.memory_percent).toFixed(1)}% RAM`;
                processList.appendChild(item);
            });
        }
    }

    async function loadDevices(deviceList, deviceSelector) {
        try {
            const response = await fetch('/api/devices');
            if (!response.ok) throw new Error('Unable to load devices');
            const data = await response.json();
            deviceList.replaceChildren();
            data.devices.forEach((device) => {
                const item = document.createElement('li');
                item.dataset.deviceId = device.device_id;
                item.setAttribute('role', 'option');
                item.textContent = device.name || device.device_id;
                item.addEventListener('click', async () => {
                    selectedDeviceId = device.device_id;
                    localStorage.setItem('processpulse-device', selectedDeviceId);
                    deviceSelector.querySelector('.device-btn').setAttribute('aria-expanded', 'false');
                    deviceList.classList.remove('show');
                    await loadInitialData();
                });
                deviceList.appendChild(item);
            });
        } catch (error) {
            console.error('Error loading devices:', error);
        }
    }

    async function fetchConnectionStatus() {
        const setStatus = (state, text) => {
            const connection = document.getElementById('connectionStatus');
            const badge = document.getElementById('agentConnectionBadge');
            if (connection) {
                connection.dataset.state = state;
                connection.querySelector('.status-text').textContent = text;
            }
            if (badge) {
                badge.dataset.state = state;
                badge.querySelector('.badge-text').textContent = text;
            }
        };
        try {
            setStatus('connecting', 'Connecting...');
            const response = await fetch('/api/health', { headers: { 'Accept': 'application/json' } });
            if (!response.ok) throw new Error('Backend health check failed');
            const data = await response.json();
            const age = data.metric_age_seconds;
            const state = age === null ? 'disconnected' : age > 30 ? 'stale' : 'connected';
            setStatus(state, state[0].toUpperCase() + state.slice(1));
            const backendUrl = document.getElementById('backendUrl');
            if (backendUrl) backendUrl.textContent = data.backend_url || window.location.origin;
            if (data.device) updateDeviceDisplay(data.device);
        } catch (error) {
            setStatus('disconnected', 'Disconnected');
            const backendUrl = document.getElementById('backendUrl');
            if (backendUrl) backendUrl.textContent = window.location.origin;
        }
    }

    function updateDeviceDisplay(device) {
        const selected = document.getElementById('selectedDevice');
        const deviceId = document.getElementById('deviceIdDisplay');
        if (selected) selected.textContent = device.name || device.device_id || 'Unknown Device';
        if (deviceId) deviceId.textContent = device.device_id || '--';
    }

    async function fetchAIStatus() {
        try {
            const response = await fetch('/api/latest', {
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const data = await response.json();

            if (data.healthScore !== undefined) {
                updateHealthScore(data.healthScore);
            }

            if (data.analysis) {
                updateAnomalyStatus(data.analysis);
            }

            if (data.device && data.device.name) {
                document.getElementById('selectedDevice').textContent = data.device.name;
                document.getElementById('deviceIdDisplay').textContent = data.device.device_id || '--';
            }
        } catch (error) {
            console.error('Error fetching AI status:', error);
        }
    }

    function updateHealthScore(score) {
        const scoreValue = document.getElementById('healthScore');
        const healthLabel = document.getElementById('healthLabel');

        if (!Number.isFinite(Number(score))) {
            if (scoreValue) scoreValue.textContent = '--';
            if (healthLabel) healthLabel.textContent = 'Waiting for analysis';
            return;
        }
        score = Number(score);
        if (scoreValue) scoreValue.textContent = score;
        if (healthLabel) {
            if (score >= 80) {
                healthLabel.textContent = 'Good';
            } else if (score >= 50) {
                healthLabel.textContent = 'Warning';
            } else {
                healthLabel.textContent = 'Critical';
            }
        }
    }

    function updateAnomalyStatus(analysis) {
        const anomalyIndicator = document.getElementById('anomalyIndicator');
        const anomalyText = document.getElementById('anomalyText');
        const anomalyReason = document.getElementById('anomalyReason');
        const anomalyScore = document.getElementById('anomalyScore');
        const recommendationsList = document.getElementById('recommendationsList');

        if (!anomalyIndicator || !anomalyText || !anomalyReason || !anomalyScore || !recommendationsList) return;
        if (!analysis || !analysis.label || analysis.anomaly_score === null || analysis.anomaly_score === undefined) {
            anomalyText.textContent = 'Waiting';
            anomalyReason.textContent = 'ML analysis is waiting for sufficient historical data';
            anomalyScore.textContent = '--';
            recommendationsList.innerHTML = '<li>Collect at least 50 valid metric samples</li>';
            return;
        }

        const label = analysis.label;
        const score = Number(analysis.anomaly_score);

        anomalyScore.textContent = score.toFixed(2);

        const labels = {
            'normal': { text: 'Normal', dotClass: '', color: 'var(--color-success)' },
            'warning': { text: 'Warning', dotClass: 'warning', color: 'var(--color-warning)' },
            'critical': { text: 'Critical', dotClass: 'critical', color: 'var(--color-danger)' }
        };

        const labelData = labels[label] || labels.normal;

        anomalyText.textContent = labelData.text;
        anomalyIndicator.className = `anomaly-indicator ${labelData.dotClass}`;
        anomalyReason.textContent = analysis.reason || 'No anomalies detected';

        if (recommendationsList) {
            if (analysis.recommendations && analysis.recommendations.length > 0) {
                recommendationsList.innerHTML = '';
                analysis.recommendations.slice(0, 3).forEach(rec => {
                    const li = document.createElement('li');
                    li.textContent = rec;
                    recommendationsList.appendChild(li);
                });
            } else {
                recommendationsList.innerHTML = '<li>System operating normally - continue monitoring</li>';
            }
        }
    }

    function showConfirmModal(options) {
        const defaultOptions = {
            title: 'Confirm Action',
            message: '',
            onConfirm: null,
            onCancel: () => {},
            showCancel: true,
            showClose: true,
            confirmText: 'Confirm',
            cancelText: 'Cancel',
            loadingText: 'Processing...',
            closeOnOverlayClick: true
        };

        const opts = { ...defaultOptions, ...options };

        const modal = document.getElementById('confirmModal');
        const modalTitle = document.getElementById('modalTitle');
        const modalMessage = document.getElementById('modalMessage');
        const modalConfirm = document.querySelector('.modal-confirm');
        const modalCancel = document.querySelector('.modal-cancel');
        const modalClose = document.querySelector('.modal-close');
        const modalOverlay = document.querySelector('.modal-overlay');

        if (!modal || !modalTitle || !modalMessage || !modalConfirm || !modalCancel || !modalClose || !modalOverlay) {
            console.error('Modal elements not found');
            return;
        }
        if (!String(opts.message || '').trim() || typeof opts.onConfirm !== 'function') {
            showToast('Unable to confirm this action: required details are missing', 'error');
            return;
        }

        modalTitle.textContent = opts.title;
        modalMessage.textContent = opts.message;
        modalConfirm.textContent = opts.confirmText;
        modalCancel.textContent = opts.cancelText;
        modal.hidden = false;
        modalConfirm.disabled = false;
        modalCancel.hidden = !opts.showCancel;
        modal.setAttribute('aria-describedby', 'modalMessage');

        // Hide/show close button based on option
        if (!opts.showClose) {
            modalClose.style.display = 'none';
        } else {
            modalClose.style.display = '';
        }

        let isProcessing = false;
        let escapeHandler;
        const cleanup = () => {
            document.removeEventListener('keydown', escapeHandler);
            modalOverlay.onclick = null;
        };

        const handleConfirm = async () => {
            if (isProcessing) return;
            isProcessing = true;

            modalConfirm.textContent = opts.loadingText;
            modalConfirm.disabled = true;
            modalCancel.disabled = true;

            try {
                const result = await opts.onConfirm();
                if (result === false) throw new Error('Action was not completed');
                cleanup();
                modal.hidden = true;
            } catch (error) {
                console.error('Confirm action failed:', error);
                showToast(error.message || 'Action failed', 'error');
            } finally {
                isProcessing = false;
                modalConfirm.textContent = opts.confirmText;
                modalConfirm.disabled = false;
                modalCancel.disabled = false;
            }
        };

        const handleCancel = () => {
            if (isProcessing) return;
            cleanup();
            if (opts.onCancel && typeof opts.onCancel === 'function') {
                opts.onCancel();
            }
            modal.hidden = true;
        };

        modalConfirm.onclick = handleConfirm;
        modalCancel.onclick = handleCancel;
        modalClose.onclick = handleCancel;

        if (opts.showOnOverlayClick !== false && opts.closeOnOverlayClick) {
            modalOverlay.onclick = (event) => {
                if (event.target === modalOverlay) handleCancel();
            };
        }

        escapeHandler = (e) => {
            if (e.key === 'Escape') {
                handleCancel();
            }
        };
        document.addEventListener('keydown', escapeHandler);
    }

    function showToast(message, type = 'info') {
        const toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        let toastIcon = '';
        if (type === 'success') {
            toastIcon = '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L3 14"/>M2 10l6.99 4.8a1.99 1.99 0 0 0 .89 3.1"/>';
        } else if (type === 'warning') {
            toastIcon = '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="15" x2="15" y2="9"/>';
        } else if (type === 'error') {
            toastIcon = '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="15" x2="15" y2="9"/>';
        }

        toast.innerHTML = `
            <svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                ${toastIcon}
            </svg>
            <div class="toast-content">
                <div class="toast-title">${type === 'error' ? 'Error' : type === 'success' ? 'Success' : 'Notification'}</div>
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close" aria-label="Close notification">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </button>
        `;

        toastContainer.appendChild(toast);

        setTimeout(() => {
            if (toast.parentNode) {
                toast.classList.add('removing');
                setTimeout(() => {
                    if (toast.parentNode) toast.parentNode.removeChild(toast);
                }, 300);
            }
        }, 5000);
    }

    function showErrorNotification(message) {
        showToast(message, 'error');
    }

    function setupAutoRefresh(refreshInterval = 5000) {
        if (refreshTimer) clearInterval(refreshTimer);
        refreshTimer = setInterval(async () => {
            try {
                await fetchCurrentMetrics();
                await fetchHistory();
                await fetchConnectionStatus();
            } catch (error) {
                console.error('Auto-refresh failed:', error);
            }
        }, refreshInterval);
    }

    window.showToast = showToast;
    window.showErrorNotification = showErrorNotification;
    window.ProcessPulseApp = {
        init: initDashboard,
        loadDashboardData
    };
})();
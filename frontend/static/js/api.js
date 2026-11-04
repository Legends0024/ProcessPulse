(function() {
    'use strict';

    const API_BASE = '';
    const DEFAULT_HEADERS = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    };

    let authToken = null;

    function setAuthToken(token) {
        authToken = token;
    }

    function getHeaders() {
        const headers = { ...DEFAULT_HEADERS };
        if (authToken) {
            headers['X-Agent-Token'] = authToken;
        }
        return headers;
    }

    async function request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            headers: getHeaders(),
            ...options
        };

        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                const error = await response.json().catch(() => ({ error: response.statusText }));
                throw new Error(error.error || `HTTP ${response.status}`);
            }

            if (response.status === 204) return null;
            return await response.json();
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    }

    const API = {
        health: () => request('/api/health'),

        getLatest: (deviceId) => {
            const params = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : '';
            return request(`/api/latest${params}`);
        },

        getHistory: (deviceId, hours = 24, limit = 1000) => {
            const params = new URLSearchParams();
            if (deviceId) params.append('device_id', deviceId);
            params.append('hours', hours);
            params.append('limit', limit);
            return request(`/api/history?${params}`);
        },

        getProcesses: (deviceId, limit = 100, sort = 'cpu_percent', order = 'desc') => {
            const params = new URLSearchParams();
            if (deviceId) params.append('device_id', deviceId);
            params.append('limit', limit);
            params.append('sort', sort);
            params.append('order', order);
            return request(`/api/processes?${params}`);
        },

        getProcessHistory: (pid, deviceId, hours = 24, limit = 500) => {
            const params = new URLSearchParams();
            if (deviceId) params.append('device_id', deviceId);
            params.append('hours', hours);
            params.append('limit', limit);
            return request(`/api/processes/${pid}/history?${params}`);
        },

        getAlerts: (deviceId, hours = 24, limit = 100, unacknowledged = false) => {
            const params = new URLSearchParams();
            if (deviceId) params.append('device_id', deviceId);
            params.append('hours', hours);
            params.append('limit', limit);
            if (unacknowledged) params.append('unacknowledged', 'true');
            return request(`/api/alerts?${params}`);
        },

        acknowledgeAlert: (alertId, acknowledgedBy = 'user') => {
            return request(`/api/alerts/${alertId}/acknowledge`, {
                method: 'POST',
                body: { acknowledged_by: acknowledgedBy }
            });
        },

        getSystemInfo: (deviceId) => {
            const params = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : '';
            return request(`/api/system${params}`);
        },

        getDevices: () => request('/api/devices'),

        getDevice: (deviceId) => request(`/api/devices/${encodeURIComponent(deviceId)}`),

        getStats: (deviceId, hours = 24) => {
            const params = new URLSearchParams();
            if (deviceId) params.append('device_id', deviceId);
            params.append('hours', hours);
            return request(`/api/stats?${params}`);
        },

        getResourcePatterns: (deviceId, hours = 24) => {
            const params = new URLSearchParams({ hours });
            if (deviceId) params.append('device_id', deviceId);
            return request(`/api/patterns?${params}`);
        },

        sendMetrics: (deviceData, metricsData, token) => {
            return request('/api/metrics', {
                method: 'POST',
                headers: { ...getHeaders(), 'X-Agent-Token': token },
                body: { device: deviceData, metrics: metricsData }
            });
        }
    };

    window.ApiClient = API;
    window.setAuthToken = setAuthToken;
})();
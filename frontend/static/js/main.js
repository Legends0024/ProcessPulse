(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        initializeApp();
    });

    function initializeApp() {
        initTheme();
        initCharts();
        loadDashboardData();
        setupEventHandlers();
    }

    function initTheme() {
        const storedTheme = localStorage.getItem('processpulse-theme');
        const theme = storedTheme || 'dark';
        document.documentElement.setAttribute('data-theme', theme);

        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            const isDark = theme === 'dark';
            themeToggle.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
            themeToggle.setAttribute('aria-pressed', isDark.toString());

            themeToggle.addEventListener('click', () => {
                const currentTheme = document.documentElement.getAttribute('data-theme');
                const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
                document.documentElement.setAttribute('data-theme', nextTheme);
                localStorage.setItem('processpulse-theme', nextTheme);

                const iconSun = document.querySelector('.icon-sun');
                const iconMoon = document.querySelector('.icon-moon');
                if (iconSun && iconMoon) {
                    iconSun.style.display = nextTheme === 'dark' ? 'block' : 'none';
                    iconMoon.style.display = nextTheme === 'dark' ? 'none' : 'block';
                }

                window.dispatchEvent(new CustomEvent('themechange', { detail: { theme: nextTheme } }));
            });
        }
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
        } catch (error) {
            console.error('Error loading dashboard data:', error);
        }
    }

    function setupEventHandlers() {
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
            deviceSelector.addEventListener('click', (e) => {
                if (e.target.closest('.device-btn')) {
                    deviceList.classList.toggle('show');
                    deviceSelector.querySelector('.device-btn').setAttribute('aria-expanded', deviceList.classList.contains('show') ? 'true' : 'false');
                }
            });

            deviceList.addEventListener('click', (e) => {
                const item = e.target.closest('li[data-device-id]');
                if (item) {
                    deviceList.classList.remove('show');
                    deviceSelector.querySelector('.device-btn').setAttribute('aria-expanded', 'false');
                    window.location.reload();
                }
            });
        }

        const clearDataBtn = document.getElementById('clearDataBtn');
        if (clearDataBtn) {
            clearDataBtn.addEventListener('click', async () => {
                try {
                    const response = await fetch('/api/stats');
                    if (response.ok) {
                        showClearSuccessToast();
                    }
                } catch (error) {
                    console.error('Error clearing data:', error);
                }
            });
        }
    }

    async function showClearSuccessToast() {
        const toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) return;

        const toast = document.createElement('div');
        toast.className = 'toast success';
        toast.innerHTML = `
            <svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <path d="M22 4L3 14"/>
                <path d="M2 10l6.99 4.8a1.99 1.99 0 0 0 .89 3.1"/>
            </svg>
            <div class="toast-content">
                <div class="toast-title">Data Cleared</div>
                <div class="toast-message">All local monitoring data has been cleared.</div>
            </div>
        `;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 4000);
    }

    window.ProcessPulseApp = {
        init: initializeApp,
        loadDashboardData
    };
})();
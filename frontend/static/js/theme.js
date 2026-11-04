(function() {
    'use strict';

    const THEME_KEY = 'processpulse-theme';
    const DARK_THEME = 'dark';
    const LIGHT_THEME = 'light';

    const themeToggle = document.getElementById('themeToggle');
    const themeSetting = document.getElementById('themeSetting');
    const html = document.documentElement;

    function getStoredTheme() {
        return localStorage.getItem(THEME_KEY);
    }

    function getPreferredTheme() {
        const stored = getStoredTheme();
        if (stored) return stored;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? DARK_THEME : LIGHT_THEME;
    }

    function applyTheme(theme) {
        html.setAttribute('data-theme', theme);
        localStorage.setItem(THEME_KEY, theme);
        updateToggleButtons(theme);
        dispatchThemeChangeEvent(theme);
    }

    function updateToggleButtons(theme) {
        const isDark = theme === DARK_THEME;
        if (themeToggle) {
            themeToggle.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
            themeToggle.setAttribute('aria-pressed', isDark.toString());
        }
        if (themeSetting) {
            themeSetting.checked = isDark;
        }
    }

    function dispatchThemeChangeEvent(theme) {
        window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
    }

    function toggleTheme() {
        const current = html.getAttribute('data-theme');
        const next = current === DARK_THEME ? LIGHT_THEME : DARK_THEME;
        applyTheme(next);
    }

    function initTheme() {
        const theme = getPreferredTheme();
        applyTheme(theme);

        if (themeToggle) {
            themeToggle.addEventListener('click', toggleTheme);
        }

        if (themeSetting) {
            themeSetting.addEventListener('change', () => {
                applyTheme(themeSetting.checked ? DARK_THEME : LIGHT_THEME);
            });
        }

        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!getStoredTheme()) {
                applyTheme(e.matches ? DARK_THEME : LIGHT_THEME);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }

    window.ThemeManager = {
        getTheme: () => html.getAttribute('data-theme'),
        setTheme: applyTheme,
        toggleTheme,
        DARK_THEME,
        LIGHT_THEME
    };
})();
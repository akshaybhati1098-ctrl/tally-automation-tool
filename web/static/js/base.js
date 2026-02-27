// base.js
// ---------- GLOBAL STATE ----------
let companies = [];
let currentCompany = null;
let currentMapping = null;
let currentGroup = null;
let currentModalGroup = null;
let companyModalMode = 'add';
let oldCompanyName = null;
let settings = {
    theme: 'light',
    default_vtype: 'sale',
    default_sheet: 'Sheet1'
};

// ---------- UTILITY ----------
function showMessage(text, type, elementId = 'message') {
    const msgDiv = document.getElementById(elementId);
    if (!msgDiv) return;
    msgDiv.className = `message ${type}`;
    msgDiv.innerHTML = text;
    msgDiv.style.display = 'block';
    setTimeout(() => {
        msgDiv.style.display = 'none';
    }, 5000);
}

// ---------- NAVIGATION ----------
function navigateTo(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById(pageId);
    if (page) page.classList.add('active');
    document.querySelectorAll('.nav-link').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.querySelector(`.nav-link[data-page="${pageId}"]`);
    if (activeBtn) activeBtn.classList.add('active');
}

document.querySelectorAll('.nav-link').forEach(btn => {
    btn.addEventListener('click', () => navigateTo(btn.dataset.page));
});

// ---------- SETTINGS & THEME ----------
function applyTheme(theme) {
    if (theme === 'dark') {
        document.body.classList.add('dark-theme');
    } else {
        document.body.classList.remove('dark-theme');
    }
}

function loadSettings() {
    const saved = localStorage.getItem('settings');
    if (saved) {
        settings = JSON.parse(saved);
    }
    const themeSelect = document.getElementById('themeSelect');
    if (themeSelect) themeSelect.value = settings.theme;
    const defaultVtype = document.getElementById('defaultVtype');
    if (defaultVtype) defaultVtype.value = settings.default_vtype;
    const defaultSheet = document.getElementById('defaultSheet');
    if (defaultSheet) defaultSheet.value = settings.default_sheet;
    applyTheme(settings.theme);
}

const saveSettingsBtn = document.getElementById('saveSettingsBtn');
if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', () => {
        const themeSelect = document.getElementById('themeSelect');
        const defaultVtype = document.getElementById('defaultVtype');
        const defaultSheet = document.getElementById('defaultSheet');
        if (themeSelect) settings.theme = themeSelect.value;
        if (defaultVtype) settings.default_vtype = defaultVtype.value;
        if (defaultSheet) settings.default_sheet = defaultSheet.value;
        localStorage.setItem('settings', JSON.stringify(settings));
        applyTheme(settings.theme);
        const msg = document.getElementById('settingsMessage');
        if (msg) {
            msg.className = 'message success';
            msg.innerHTML = 'Settings saved!';
            msg.style.display = 'block';
            setTimeout(() => {
                msg.style.display = 'none';
            }, 2000);
        }
    });
}

loadSettings();// common js logic
// Theme management
(function() {
    // Get saved theme from localStorage or default to 'light'
    function getSavedTheme() {
        return localStorage.getItem('theme') || 'light';
    }

    // Apply theme by adding/removing dark-theme class on body
    function applyTheme(theme) {
        document.body.classList.toggle('dark-theme', theme === 'dark');
        localStorage.setItem('theme', theme);
    }

    // Initialize theme on page load
    function initTheme() {
        const savedTheme = getSavedTheme();
        applyTheme(savedTheme);

        // If there's a theme selector on the page, set its value
        const themeSelect = document.getElementById('themeSelect');
        if (themeSelect) {
            themeSelect.value = savedTheme;
        }
    }

    // Listen for theme changes (from any page)
    document.addEventListener('change', function(e) {
        if (e.target && e.target.id === 'themeSelect') {
            applyTheme(e.target.value);
        }
    });

    // Run initialization when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }
})();
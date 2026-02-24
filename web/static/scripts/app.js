// ---------- STATE ----------
let currentMapping = null;
let currentGroup = null;
let settings = {
    theme: 'light',
    default_vtype: 'sale',
    default_sheet: 'Sheet1'
};

// ---------- NAVIGATION ----------
function navigateTo(pageId) {
    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    // Show selected page
    document.getElementById(pageId).classList.add('active');
    // Update active nav button
    document.querySelectorAll('.nav-link').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`.nav-link[data-page="${pageId}"]`).classList.add('active');
}

document.querySelectorAll('.nav-link').forEach(btn => {
    btn.addEventListener('click', () => navigateTo(btn.dataset.page));
});

// ---------- DASHBOARD ----------
function downloadTemplate() {
    alert('Template download: Create a sample Excel with required columns.\nIn a full version, this would generate a file.');
}

function viewReports() {
    alert('Reports feature coming soon.');
}

async function loadActivity() {
    // Simulate recent activity (in real app, could fetch from server logs)
    document.getElementById('activityLog').innerHTML = `
        <div>[12:34] Converted 25 records from sales.xlsx</div>
        <div>[11:20] Mapping updated</div>
        <div>[10:15] 3 files processed</div>
    `;
}
loadActivity();

// ---------- EXCEL TO XML CONVERTER ----------
document.getElementById('convertForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const progress = document.getElementById('progress');
    const progressBar = document.getElementById('progressBar');
    const messageDiv = document.getElementById('message');

    progress.style.display = 'block';
    progressBar.style.width = '0%';
    messageDiv.style.display = 'none';

    try {
        const response = await fetch('/api/convert', {
            method: 'POST',
            body: formData
        });

        progressBar.style.width = '100%';

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'output.xml';
            if (contentDisposition) {
                const match = contentDisposition.match(/filename="?([^"]+)"?/);
                if (match) filename = match[1];
            }
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);

            const records = response.headers.get('X-Records-Processed');
            messageDiv.className = 'message success';
            messageDiv.innerHTML = `✅ Conversion successful! ${records ? records + ' records processed.' : ''}`;
            messageDiv.style.display = 'block';
        } else {
            const error = await response.text();
            throw new Error(error);
        }
    } catch (err) {
        messageDiv.className = 'message error';
        messageDiv.innerHTML = `❌ Error: ${err.message}`;
        messageDiv.style.display = 'block';
    } finally {
        setTimeout(() => {
            progress.style.display = 'none';
            progressBar.style.width = '0%';
        }, 1000);
    }
});

// ---------- PDF TO EXCEL CONVERTER ----------
document.getElementById('pdfConvertForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const progress = document.getElementById('pdfProgress');
    const progressBar = document.getElementById('pdfProgressBar');
    const messageDiv = document.getElementById('pdfMessage');

    progress.style.display = 'block';
    progressBar.style.width = '0%';
    messageDiv.style.display = 'none';

    try {
        const response = await fetch('/api/convert-pdf', {
            method: 'POST',
            body: formData
        });

        progressBar.style.width = '100%';

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'converted.xlsx';
            if (contentDisposition) {
                const match = contentDisposition.match(/filename="?([^"]+)"?/);
                if (match) filename = match[1];
            }
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);

            messageDiv.className = 'message success';
            messageDiv.innerHTML = '✅ Conversion successful!';
            messageDiv.style.display = 'block';
        } else {
            const error = await response.text();
            throw new Error(error);
        }
    } catch (err) {
        messageDiv.className = 'message error';
        messageDiv.innerHTML = `❌ Error: ${err.message}`;
        messageDiv.style.display = 'block';
    } finally {
        setTimeout(() => {
            progress.style.display = 'none';
            progressBar.style.width = '0%';
        }, 1000);
    }
});

// ---------- MAPPING EDITOR ----------
const groupNames = [
    'COMPANY_STATE',
    'SALES',
    'SALES_IGST',
    'PURCHASE',
    'CGST_RATES',
    'SGST_RATES',
    'IGST_RATES',
    'DEBUG'
];

async function loadMapping() {
    try {
        const response = await fetch('/api/mapping');
        currentMapping = await response.json();
        renderGroupList();
        if (groupNames.length > 0) selectGroup(groupNames[0]);
    } catch (err) {
        alert('Failed to load mapping. Is the server running?');
    }
}

function renderGroupList() {
    const groupListDiv = document.getElementById('groupList');
    groupListDiv.innerHTML = '';
    groupNames.forEach(name => {
        const div = document.createElement('div');
        div.className = 'group-item';
        div.textContent = name;
        div.onclick = () => selectGroup(name);
        groupListDiv.appendChild(div);
    });
}

function selectGroup(name) {
    currentGroup = name;
    // Update active class
    document.querySelectorAll('.group-item').forEach(item => item.classList.remove('active'));
    // Find the one with matching text
    const items = document.querySelectorAll('.group-item');
    for (let item of items) {
        if (item.textContent.trim() === name) {
            item.classList.add('active');
            break;
        }
    }
    document.getElementById('currentGroupTitle').textContent = `Editing: ${name}`;
    renderRateList(name);
}

function renderRateList(group) {
    const rateListDiv = document.getElementById('rateList');
    const addBtn = document.getElementById('addRateBtn');
    const data = currentMapping[group];

    if (group === 'DEBUG') {
        const value = data || false;
        rateListDiv.innerHTML = `<div class="rate-item">DEBUG Mode: ${value ? 'Enabled' : 'Disabled'}</div>`;
        addBtn.textContent = 'Toggle DEBUG';
        addBtn.onclick = () => {
            currentMapping.DEBUG = !currentMapping.DEBUG;
            renderRateList(group);
        };
    } else if (group === 'COMPANY_STATE') {
        const value = data || 'Not set';
        rateListDiv.innerHTML = `<div class="rate-item">Current State: ${value}</div>`;
        addBtn.textContent = 'Change State';
        addBtn.onclick = () => {
            const newState = prompt('Enter company state:', value);
            if (newState) {
                currentMapping.COMPANY_STATE = newState;
                renderRateList(group);
            }
        };
    } else {
        // Object of rate -> ledger
        rateListDiv.innerHTML = '';
        if (!data || Object.keys(data).length === 0) {
            rateListDiv.innerHTML = '<div class="rate-item">No mappings found. Click "Add Rate" to create one.</div>';
        } else {
            Object.entries(data)
                .sort((a, b) => parseFloat(a[0]) - parseFloat(b[0]))
                .forEach(([rate, ledger]) => {
                    const item = document.createElement('div');
                    item.className = 'rate-item';
                    item.innerHTML = `
                        <span><b>${rate}%</b> → ${ledger}</span>
                        <div class="rate-actions">
                            <button class="btn-edit" onclick="editRate('${group}', '${rate}', '${ledger}')">✏️</button>
                            <button class="btn-delete" onclick="deleteRate('${group}', '${rate}')">🗑️</button>
                        </div>
                    `;
                    rateListDiv.appendChild(item);
                });
        }
        addBtn.textContent = '➕ Add Rate';
        addBtn.onclick = () => addRate(group);
    }
}

function addRate(group) {
    const rate = prompt('Enter GST Rate (%):', '');
    if (!rate) return;
    const floatRate = parseFloat(rate);
    if (isNaN(floatRate) || floatRate < 0 || floatRate > 100) {
        alert('Invalid rate');
        return;
    }
    const ledger = prompt('Enter Ledger Name:', '');
    if (!ledger) return;
    const rateKey = String(floatRate);
    if (!currentMapping[group]) currentMapping[group] = {};
    currentMapping[group][rateKey] = ledger;
    renderRateList(group);
}

window.editRate = function(group, rate, oldLedger) {
    const newLedger = prompt(`Edit ledger for ${rate}%:`, oldLedger);
    if (newLedger) {
        currentMapping[group][rate] = newLedger;
        renderRateList(group);
    }
};

window.deleteRate = function(group, rate) {
    if (confirm(`Delete mapping for ${rate}%?`)) {
        delete currentMapping[group][rate];
        renderRateList(group);
    }
};

document.getElementById('saveMappingBtn').addEventListener('click', async () => {
    try {
        const response = await fetch('/api/mapping', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentMapping)
        });
        if (response.ok) {
            alert('Mapping saved successfully!');
        } else {
            alert('Failed to save mapping.');
        }
    } catch (err) {
        alert('Error saving mapping: ' + err.message);
    }
});

// ---------- SETTINGS ----------
async function loadSettings() {
    // Load from localStorage
    const saved = localStorage.getItem('settings');
    if (saved) {
        settings = JSON.parse(saved);
    }
    document.getElementById('themeSelect').value = settings.theme;
    document.getElementById('defaultVtype').value = settings.default_vtype;
    document.getElementById('defaultSheet').value = settings.default_sheet;
    applyTheme(settings.theme);
}

function applyTheme(theme) {
    if (theme === 'dark') {
        document.body.classList.add('dark-theme');
    } else {
        document.body.classList.remove('dark-theme');
    }
}

document.getElementById('saveSettingsBtn').addEventListener('click', () => {
    settings.theme = document.getElementById('themeSelect').value;
    settings.default_vtype = document.getElementById('defaultVtype').value;
    settings.default_sheet = document.getElementById('defaultSheet').value;
    localStorage.setItem('settings', JSON.stringify(settings));
    applyTheme(settings.theme);
    const msg = document.getElementById('settingsMessage');
    msg.className = 'message success';
    msg.innerHTML = 'Settings saved!';
    msg.style.display = 'block';
    setTimeout(() => {
        msg.style.display = 'none';
    }, 2000);
});

// ---------- INIT ----------
loadMapping();
loadSettings();
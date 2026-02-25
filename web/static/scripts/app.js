// ---------- STATE ----------
let companies = [];
let currentCompany = null;
let currentMapping = null;   // mapping for the selected company
let currentGroup = null;
let currentModalGroup = null; // group for which we are adding a rate
let companyModalMode = 'add'; // 'add' or 'rename'
let oldCompanyName = null;
let settings = {
    theme: 'light',
    default_vtype: 'sale',
    default_sheet: 'Sheet1'
};

// ---------- NAVIGATION ----------
function navigateTo(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
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
    document.getElementById('activityLog').innerHTML = `
        <div>[12:34] Converted 25 records from sales.xlsx</div>
        <div>[11:20] Mapping updated</div>
        <div>[10:15] 3 files processed</div>
    `;
}
loadActivity();

// ---------- EXCEL TO XML: COMPANY & SHEET DETECTION ----------
const fileInput = document.getElementById('fileInput');
const sheetSelect = document.getElementById('sheetSelect');
const sheetLoading = document.getElementById('sheetLoading');
const submitBtn = document.getElementById('submitBtn');
const companySelect = document.getElementById('companySelect');

async function loadCompaniesForConverter() {
    try {
        const response = await fetch('/api/companies');
        const data = await response.json();
        companies = data.companies;
        companySelect.innerHTML = '<option value="">-- Select company --</option>';
        companies.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c;
            opt.textContent = c;
            companySelect.appendChild(opt);
        });
    } catch (err) {
        console.error('Failed to load companies', err);
    }
}

companySelect.addEventListener('change', () => {
    submitBtn.disabled = !(fileInput.files.length && sheetSelect.value && companySelect.value);
});

fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) {
        sheetSelect.disabled = true;
        sheetSelect.innerHTML = '<option value="">-- Select a sheet --</option>';
        submitBtn.disabled = true;
        return;
    }

    sheetSelect.disabled = true;
    sheetLoading.style.display = 'block';
    sheetSelect.innerHTML = '<option value="">Loading...</option>';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/sheets', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Failed to load sheets');

        const data = await response.json();
        const sheets = data.sheets;

        sheetSelect.innerHTML = '';
        sheets.forEach(sheet => {
            const option = document.createElement('option');
            option.value = sheet;
            option.textContent = sheet;
            sheetSelect.appendChild(option);
        });

        sheetSelect.disabled = false;
        submitBtn.disabled = !companySelect.value;
    } catch (err) {
        console.error(err);
        sheetSelect.innerHTML = '<option value="">Error loading sheets</option>';
        sheetSelect.disabled = true;
        submitBtn.disabled = true;
        showMessage('Error reading sheet names. Please check the file.', 'error');
    } finally {
        sheetLoading.style.display = 'none';
    }
});

function showMessage(text, type) {
    const msgDiv = document.getElementById('message');
    msgDiv.className = `message ${type}`;
    msgDiv.innerHTML = text;
    msgDiv.style.display = 'block';
    setTimeout(() => {
        msgDiv.style.display = 'none';
    }, 5000);
}

// ---------- EXCEL TO XML CONVERTER (SUBMIT) ----------
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

// ---------- MAPPING EDITOR (multi‑company) ----------
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

async function loadCompaniesForMapping() {
    try {
        const response = await fetch('/api/companies');
        const data = await response.json();
        companies = data.companies;
        renderCompanyList();
        if (companies.length > 0) selectCompany(companies[0]);
    } catch (err) {
        alert('Failed to load companies. Is the server running?');
    }
}

function renderCompanyList() {
    const companyListDiv = document.getElementById('companyList');
    if (!companyListDiv) return;
    companyListDiv.innerHTML = '';
    companies.forEach(name => {
        const div = document.createElement('div');
        div.className = 'group-item';
        div.textContent = name;
        div.onclick = () => selectCompany(name);
        companyListDiv.appendChild(div);
    });
}

async function selectCompany(name) {
    currentCompany = name;
    document.getElementById('selectedCompany').textContent = name;
    // Update active class
    document.querySelectorAll('#companyList .group-item').forEach(item => item.classList.remove('active'));
    const items = document.querySelectorAll('#companyList .group-item');
    for (let item of items) {
        if (item.textContent.trim() === name) {
            item.classList.add('active');
            break;
        }
    }
    // Show rename/delete only if not Default
    const isDefault = (name === 'Default');
    const deleteBtn = document.getElementById('deleteCompanyBtn');
    if (deleteBtn) deleteBtn.style.display = isDefault ? 'none' : 'inline-block';
    const renameBtn = document.getElementById('renameCompanyBtn');
    if (renameBtn) renameBtn.style.display = isDefault ? 'none' : 'inline-block';

    // Load mapping for this company
    try {
        const response = await fetch(`/api/mapping/${encodeURIComponent(name)}`);
        currentMapping = await response.json();
        renderGroupList();
        if (groupNames.length > 0) selectGroup(groupNames[0]);
    } catch (err) {
        alert('Failed to load mapping for this company.');
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
    document.querySelectorAll('#groupList .group-item').forEach(item => item.classList.remove('active'));
    const items = document.querySelectorAll('#groupList .group-item');
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
    const data = currentMapping ? currentMapping[group] : null;

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
    currentModalGroup = group;
    const modal = document.getElementById('rateModal');
    const rateInput = document.getElementById('modalRate');
    const ledgerInput = document.getElementById('modalLedger');
    
    // Clear previous values
    rateInput.value = '';
    ledgerInput.value = '';
    
    // Show modal
    modal.classList.add('show');
}

// Modal OK button (for rate)
document.getElementById('modalOkBtn').addEventListener('click', () => {
    const modal = document.getElementById('rateModal');
    const rateInput = document.getElementById('modalRate');
    const ledgerInput = document.getElementById('modalLedger');
    const rate = rateInput.value.trim();
    const ledger = ledgerInput.value.trim();
    
    if (!rate || !ledger) {
        alert('Please fill both fields');
        return;
    }
    
    const floatRate = parseFloat(rate);
    if (isNaN(floatRate) || floatRate < 0 || floatRate > 100) {
        alert('Invalid rate (must be between 0 and 100)');
        return;
    }
    
    const group = currentModalGroup;
    if (!group) {
        alert('No group selected');
        modal.classList.remove('show');
        return;
    }
    
    const rateKey = String(floatRate);
    if (!currentMapping[group]) currentMapping[group] = {};
    currentMapping[group][rateKey] = ledger;
    
    // Refresh the rate list
    renderRateList(group);
    
    // Hide modal
    modal.classList.remove('show');
    currentModalGroup = null;
});

// Modal Cancel button (for rate)
document.getElementById('modalCancelBtn').addEventListener('click', () => {
    document.getElementById('rateModal').classList.remove('show');
    currentModalGroup = null;
});

// Close rate modal when clicking outside
window.addEventListener('click', (e) => {
    const rateModal = document.getElementById('rateModal');
    if (e.target === rateModal) {
        rateModal.classList.remove('show');
        currentModalGroup = null;
    }
});

// Edit and delete rate functions (using prompt for simplicity)
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
    if (!currentCompany) return alert('No company selected');
    try {
        const response = await fetch(`/api/mapping/${encodeURIComponent(currentCompany)}`, {
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

// Add Company button - show modal
document.getElementById('addCompanyBtn')?.addEventListener('click', () => {
    companyModalMode = 'add';
    document.getElementById('companyModalTitle').textContent = 'Add Company';
    document.getElementById('companyNameInput').value = '';
    document.getElementById('companyModal').classList.add('show');
});

// Rename Company button - show modal with current name
document.getElementById('renameCompanyBtn')?.addEventListener('click', () => {
    if (!currentCompany || currentCompany === 'Default') {
        alert('Cannot rename the Default company');
        return;
    }
    companyModalMode = 'rename';
    oldCompanyName = currentCompany;
    document.getElementById('companyModalTitle').textContent = 'Rename Company';
    document.getElementById('companyNameInput').value = currentCompany;
    document.getElementById('companyModal').classList.add('show');
});

// Company Modal OK button
document.getElementById('companyModalOkBtn').addEventListener('click', async () => {
    const modal = document.getElementById('companyModal');
    const nameInput = document.getElementById('companyNameInput');
    const newName = nameInput.value.trim();
    
    if (!newName) {
        alert('Please enter a company name');
        return;
    }
    
    if (companyModalMode === 'add') {
        // Add company
        const formData = new FormData();
        formData.append('name', newName);
        try {
            const response = await fetch('/api/companies', {
                method: 'POST',
                body: formData
            });
            if (response.ok) {
                await loadCompaniesForMapping();
                await selectCompany(newName);
                await loadCompaniesForConverter();
            } else {
                const err = await response.text();
                alert('Failed to create company: ' + err);
            }
        } catch (err) {
            alert('Error: ' + err.message);
        }
    } else if (companyModalMode === 'rename') {
        // Rename company
        if (newName === oldCompanyName) {
            modal.classList.remove('show');
            return;
        }
        const formData = new FormData();
        formData.append('new_name', newName);
        try {
            const response = await fetch(`/api/companies/${encodeURIComponent(oldCompanyName)}`, {
                method: 'PUT',
                body: formData
            });
            if (response.ok) {
                await loadCompaniesForMapping();
                await selectCompany(newName);
                await loadCompaniesForConverter();
            } else {
                const err = await response.text();
                alert('Failed to rename company: ' + err);
            }
        } catch (err) {
            alert('Error: ' + err.message);
        }
    }
    
    modal.classList.remove('show');
    companyModalMode = 'add';
    oldCompanyName = null;
});

// Company Modal Cancel button
document.getElementById('companyModalCancelBtn').addEventListener('click', () => {
    document.getElementById('companyModal').classList.remove('show');
    companyModalMode = 'add';
    oldCompanyName = null;
});

// Close company modal when clicking outside
window.addEventListener('click', (e) => {
    const companyModal = document.getElementById('companyModal');
    if (e.target === companyModal) {
        companyModal.classList.remove('show');
        companyModalMode = 'add';
        oldCompanyName = null;
    }
});

// Delete Company button
document.getElementById('deleteCompanyBtn')?.addEventListener('click', async () => {
    if (!currentCompany || currentCompany === 'Default') return;
    if (!confirm(`Are you sure you want to delete company "${currentCompany}"?`)) return;
    try {
        const response = await fetch(`/api/companies/${encodeURIComponent(currentCompany)}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            await loadCompaniesForMapping();
            await loadCompaniesForConverter();
        } else {
            const err = await response.text();
            alert('Failed to delete company: ' + err);
        }
    } catch (err) {
        alert('Error: ' + err.message);
    }
});

// ---------- SETTINGS ----------
async function loadSettings() {
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
if (document.getElementById('companyList')) {
    loadCompaniesForMapping();
}
loadCompaniesForConverter();
loadSettings();
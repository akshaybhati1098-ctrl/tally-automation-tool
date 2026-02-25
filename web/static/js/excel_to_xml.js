// excel_to_xml.js
// ---------- EXCEL TO XML: COMPANY & SHEET DETECTION ----------
const fileInput = document.getElementById('fileInput');
const sheetSelect = document.getElementById('sheetSelect');
const sheetLoading = document.getElementById('sheetLoading');
const submitBtn = document.getElementById('submitBtn');
const companySelect = document.getElementById('companySelect');

async function loadCompaniesForConverter() {
    if (!companySelect) return;
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

if (companySelect) {
    companySelect.addEventListener('change', () => {
        if (submitBtn) {
            submitBtn.disabled = !(fileInput && fileInput.files.length && sheetSelect && sheetSelect.value && companySelect.value);
        }
    });
}

if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) {
            if (sheetSelect) {
                sheetSelect.disabled = true;
                sheetSelect.innerHTML = '<option value="">-- Select a sheet --</option>';
            }
            if (submitBtn) submitBtn.disabled = true;
            return;
        }

        if (sheetSelect) sheetSelect.disabled = true;
        if (sheetLoading) sheetLoading.style.display = 'block';
        if (sheetSelect) sheetSelect.innerHTML = '<option value="">Loading...</option>';

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

            if (sheetSelect) {
                sheetSelect.innerHTML = '';
                sheets.forEach(sheet => {
                    const option = document.createElement('option');
                    option.value = sheet;
                    option.textContent = sheet;
                    sheetSelect.appendChild(option);
                });
                sheetSelect.disabled = false;
            }
            if (submitBtn) submitBtn.disabled = !companySelect || !companySelect.value;
        } catch (err) {
            console.error(err);
            if (sheetSelect) {
                sheetSelect.innerHTML = '<option value="">Error loading sheets</option>';
                sheetSelect.disabled = true;
            }
            if (submitBtn) submitBtn.disabled = true;
            showMessage('Error reading sheet names. Please check the file.', 'error');
        } finally {
            if (sheetLoading) sheetLoading.style.display = 'none';
        }
    });
}

// ---------- EXCEL TO XML CONVERTER (SUBMIT) ----------
const convertForm = document.getElementById('convertForm');
if (convertForm) {
    convertForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const progress = document.getElementById('progress');
        const progressBar = document.getElementById('progressBar');
        const messageDiv = document.getElementById('message');

        if (progress) progress.style.display = 'block';
        if (progressBar) progressBar.style.width = '0%';
        if (messageDiv) messageDiv.style.display = 'none';

        try {
            const response = await fetch('/api/convert', {
                method: 'POST',
                body: formData
            });

            if (progressBar) progressBar.style.width = '100%';

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
                if (messageDiv) {
                    messageDiv.className = 'message success';
                    messageDiv.innerHTML = `✅ Conversion successful! ${records ? records + ' records processed.' : ''}`;
                    messageDiv.style.display = 'block';
                }
            } else {
                const error = await response.text();
                throw new Error(error);
            }
        } catch (err) {
            if (messageDiv) {
                messageDiv.className = 'message error';
                messageDiv.innerHTML = `❌ Error: ${err.message}`;
                messageDiv.style.display = 'block';
            }
        } finally {
            setTimeout(() => {
                if (progress) progress.style.display = 'none';
                if (progressBar) progressBar.style.width = '0%';
            }, 1000);
        }
    });
}

// ---------- PDF TO EXCEL CONVERTER ----------
const pdfConvertForm = document.getElementById('pdfConvertForm');
if (pdfConvertForm) {
    pdfConvertForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const progress = document.getElementById('pdfProgress');
        const progressBar = document.getElementById('pdfProgressBar');
        const messageDiv = document.getElementById('pdfMessage');

        if (progress) progress.style.display = 'block';
        if (progressBar) progressBar.style.width = '0%';
        if (messageDiv) messageDiv.style.display = 'none';

        try {
            const response = await fetch('/api/convert-pdf', {
                method: 'POST',
                body: formData
            });

            if (progressBar) progressBar.style.width = '100%';

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

                if (messageDiv) {
                    messageDiv.className = 'message success';
                    messageDiv.innerHTML = '✅ Conversion successful!';
                    messageDiv.style.display = 'block';
                }
            } else {
                const error = await response.text();
                throw new Error(error);
            }
        } catch (err) {
            if (messageDiv) {
                messageDiv.className = 'message error';
                messageDiv.innerHTML = `❌ Error: ${err.message}`;
                messageDiv.style.display = 'block';
            }
        } finally {
            setTimeout(() => {
                if (progress) progress.style.display = 'none';
                if (progressBar) progressBar.style.width = '0%';
            }, 1000);
        }
    });
}

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

async function loadCompaniesForMapping() {
    const companyListDiv = document.getElementById('companyList');
    if (!companyListDiv) return;
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
    const selectedCompanySpan = document.getElementById('selectedCompany');
    if (selectedCompanySpan) selectedCompanySpan.textContent = name;
    document.querySelectorAll('#companyList .group-item').forEach(item => item.classList.remove('active'));
    const items = document.querySelectorAll('#companyList .group-item');
    for (let item of items) {
        if (item.textContent.trim() === name) {
            item.classList.add('active');
            break;
        }
    }
    const isDefault = (name === 'Default');
    const deleteBtn = document.getElementById('deleteCompanyBtn');
    if (deleteBtn) deleteBtn.style.display = isDefault ? 'none' : 'inline-block';
    const renameBtn = document.getElementById('renameCompanyBtn');
    if (renameBtn) renameBtn.style.display = isDefault ? 'none' : 'inline-block';

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
    if (!groupListDiv) return;
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
    const currentGroupTitle = document.getElementById('currentGroupTitle');
    if (currentGroupTitle) currentGroupTitle.textContent = `Editing: ${name}`;
    renderRateList(name);
}

function renderRateList(group) {
    const rateListDiv = document.getElementById('rateList');
    const addBtn = document.getElementById('addRateBtn');
    if (!rateListDiv || !addBtn) return;
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
    if (!modal || !rateInput || !ledgerInput) return;
    rateInput.value = '';
    ledgerInput.value = '';
    modal.classList.add('show');
}

const modalOkBtn = document.getElementById('modalOkBtn');
if (modalOkBtn) {
    modalOkBtn.addEventListener('click', () => {
        const modal = document.getElementById('rateModal');
        const rateInput = document.getElementById('modalRate');
        const ledgerInput = document.getElementById('modalLedger');
        if (!modal || !rateInput || !ledgerInput) return;
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

        renderRateList(group);

        modal.classList.remove('show');
        currentModalGroup = null;
    });
}

const modalCancelBtn = document.getElementById('modalCancelBtn');
if (modalCancelBtn) {
    modalCancelBtn.addEventListener('click', () => {
        document.getElementById('rateModal')?.classList.remove('show');
        currentModalGroup = null;
    });
}

window.addEventListener('click', (e) => {
    const rateModal = document.getElementById('rateModal');
    if (e.target === rateModal) {
        rateModal.classList.remove('show');
        currentModalGroup = null;
    }
});

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

const saveMappingBtn = document.getElementById('saveMappingBtn');
if (saveMappingBtn) {
    saveMappingBtn.addEventListener('click', async () => {
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
}

const addCompanyBtn = document.getElementById('addCompanyBtn');
if (addCompanyBtn) {
    addCompanyBtn.addEventListener('click', () => {
        companyModalMode = 'add';
        const title = document.getElementById('companyModalTitle');
        if (title) title.textContent = 'Add Company';
        const input = document.getElementById('companyNameInput');
        if (input) input.value = '';
        const modal = document.getElementById('companyModal');
        if (modal) modal.classList.add('show');
    });
}

const renameCompanyBtn = document.getElementById('renameCompanyBtn');
if (renameCompanyBtn) {
    renameCompanyBtn.addEventListener('click', () => {
        if (!currentCompany || currentCompany === 'Default') {
            alert('Cannot rename the Default company');
            return;
        }
        companyModalMode = 'rename';
        oldCompanyName = currentCompany;
        const title = document.getElementById('companyModalTitle');
        if (title) title.textContent = 'Rename Company';
        const input = document.getElementById('companyNameInput');
        if (input) input.value = currentCompany;
        const modal = document.getElementById('companyModal');
        if (modal) modal.classList.add('show');
    });
}

const companyModalOkBtn = document.getElementById('companyModalOkBtn');
if (companyModalOkBtn) {
    companyModalOkBtn.addEventListener('click', async () => {
        const modal = document.getElementById('companyModal');
        const nameInput = document.getElementById('companyNameInput');
        if (!modal || !nameInput) return;
        const newName = nameInput.value.trim();

        if (!newName) {
            alert('Please enter a company name');
            return;
        }

        if (companyModalMode === 'add') {
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
}

const companyModalCancelBtn = document.getElementById('companyModalCancelBtn');
if (companyModalCancelBtn) {
    companyModalCancelBtn.addEventListener('click', () => {
        document.getElementById('companyModal')?.classList.remove('show');
        companyModalMode = 'add';
        oldCompanyName = null;
    });
}

window.addEventListener('click', (e) => {
    const companyModal = document.getElementById('companyModal');
    if (e.target === companyModal) {
        companyModal.classList.remove('show');
        companyModalMode = 'add';
        oldCompanyName = null;
    }
});

const deleteCompanyBtn = document.getElementById('deleteCompanyBtn');
if (deleteCompanyBtn) {
    deleteCompanyBtn.addEventListener('click', async () => {
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
}

if (document.getElementById('companyList')) {
    loadCompaniesForMapping();
}
if (document.getElementById('companySelect')) {
    loadCompaniesForConverter();
}
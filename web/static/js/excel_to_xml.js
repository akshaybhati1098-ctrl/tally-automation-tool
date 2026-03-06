// excel_to_xml.js
// ---------- EXCEL TO XML: COMPANY & SHEET DETECTION ----------
const fileInput = document.getElementById('fileInput');
const sheetSelect = document.getElementById('sheetSelect');
const sheetLoading = document.getElementById('sheetLoading');
const submitBtn = document.getElementById('submitBtn');
const companySelect = document.getElementById('companySelect');

// Store companies list (avoid implicit global)
let companies = [];

// Simple message function (fallback if not defined elsewhere)
function showMessage(msg, type = 'info') {
    console.log(`[${type}] ${msg}`);
    // You can replace this with a proper toast/notification
    if (type === 'error') alert(msg);
}

// ---------- COMPANY DROPDOWN ----------
async function loadCompaniesForConverter() {
    if (!companySelect) return;
    try {
        const response = await fetch('/api/companies');
        const data = await response.json();
        companies = data.companies || [];
        companySelect.innerHTML = '<option value="">-- Select company --</option>';
        companies.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c;
            opt.textContent = c;
            companySelect.appendChild(opt);
        });
    } catch (err) {
        console.error('Failed to load companies', err);
        showMessage('Failed to load companies', 'error');
    }
}

// Make it globally accessible so mapping page can refresh it
window.loadCompaniesForConverter = loadCompaniesForConverter;

// Enable/disable submit button based on selections
if (companySelect) {
    companySelect.addEventListener('change', () => {
        if (submitBtn) {
            submitBtn.disabled = !(fileInput && fileInput.files.length && sheetSelect && sheetSelect.value && companySelect.value);
        }
    });
}

// ---------- SHEET DETECTION ----------
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

                // Auto-select if only one sheet
                if (sheets.length === 1) {
                    sheetSelect.value = sheets[0];
                }
            }
            // Enable submit if company is already selected
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
            showMessage('Conversion failed: ' + err.message, 'error');
        } finally {
            setTimeout(() => {
                if (progress) progress.style.display = 'none';
                if (progressBar) progressBar.style.width = '0%';
            }, 1000);
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadCompaniesForConverter();
});
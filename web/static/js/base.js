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

// ---------- EXCEL → TALLY VOUCHER TYPES ----------
// The converter page keeps its existing voucher selector and conversion flow.
// Add Credit Note / Debit Note here so the page can expose the new voucher types
// without changing the existing Sales / Purchase UI logic.
(function addNoteVoucherTypes() {
    function addOptions() {
        const select = document.getElementById('voucherSelect');
        if (!select) return;

        const options = [
            { value: 'credit_note', label: '↩️ Credit Note' },
            { value: 'debit_note', label: '↪️ Debit Note' }
        ];

        options.forEach(({ value, label }) => {
            if (select.querySelector(`option[value="${value}"]`)) return;
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            select.appendChild(option);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', addOptions);
    } else {
        addOptions();
    }
})();

// ---------- EXCEL LEDGER COLUMN SELECTION ----------
// Only runs on the Excel → XML page.  The existing converter expects the
// ledger-column headers below.  If the user selects "Use Excel Ledgers" but
// their workbook uses different headers (for example "sale", "cgst", "sgst"),
// this small pre-conversion step lets them map those Excel columns to the
// existing names.  The original conversion/XML logic is not changed.
(function addExcelLedgerColumnSelection() {
    const DEFAULT_HEADERS = {
        sales: 'Sales Ledger',
        purchase: 'Purchase Ledger',
        cgst: 'CGST Ledger',
        sgst: 'SGST Ledger',
        igst: 'IGST Ledger'
    };

    const norm = value => String(value ?? '').trim().toLowerCase();

    function getRequiredRoles(ws, vtype) {
        const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
        const headers = (rows[0] || []).map(v => String(v ?? '').trim());
        const headerIndex = {};
        headers.forEach((h, i) => { if (h) headerIndex[norm(h)] = i; });

        const roles = [
            vtype === 'purchase' || vtype === 'debit_note'
                ? { key: 'purchase', label: 'Purchase Ledger', header: DEFAULT_HEADERS.purchase }
                : { key: 'sales', label: 'Sales Ledger', header: DEFAULT_HEADERS.sales }
        ];

        // Tax-ledger columns are only required when the corresponding tax
        // column actually contains a non-zero/non-empty value in the sheet.
        [
            ['cgst', 'CGST', DEFAULT_HEADERS.cgst],
            ['sgst', 'SGST', DEFAULT_HEADERS.sgst],
            ['igst', 'IGST', DEFAULT_HEADERS.igst]
        ].forEach(([key, taxColumn, header]) => {
            const idx = headerIndex[norm(taxColumn)];
            if (idx == null) return;
            const hasTax = rows.slice(1).some(row => {
                const value = row[idx];
                if (value === null || value === undefined || String(value).trim() === '') return false;
                const number = Number(String(value).replace(/,/g, '').trim());
                return Number.isNaN(number) ? String(value).trim() !== '' : number !== 0;
            });
            if (hasTax) roles.push({ key, label: `${taxColumn} Ledger`, header });
        });

        return { headers, roles };
    }

    function findHeader(headers, expected) {
        const target = norm(expected);
        return headers.find(h => norm(h) === target) || '';
    }

    function showLedgerColumnPopup(headers, roles, filename, onConfirm) {
        const existing = document.getElementById('excelLedgerColumnOverlay');
        if (existing) existing.remove();

        const detected = {};
        const needsMapping = roles.filter(role => {
            const exact = findHeader(headers, role.header);
            detected[role.key] = exact;
            return !exact;
        });

        if (!needsMapping.length) {
            onConfirm({});
            return;
        }

        const escape = value => String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');

        const options = '<option value="">-- Select Excel column --</option>' +
            headers.map(h => `<option value="${escape(h)}">${escape(h)}</option>`).join('');

        const overlay = document.createElement('div');
        overlay.id = 'excelLedgerColumnOverlay';
        overlay.style.cssText = `
            position:fixed; inset:0; z-index:10060; display:flex; align-items:center;
            justify-content:center; padding:20px; background:rgba(10,15,30,.55);
            backdrop-filter:blur(5px);
        `;

        overlay.innerHTML = `
            <div style="width:min(620px,96vw); max-height:88vh; overflow:auto; background:#fff;
                        border-radius:22px; box-shadow:0 24px 70px rgba(10,15,30,.25); padding:24px;">
                <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
                            padding-bottom:16px;border-bottom:1px solid #e2ebf8;">
                    <div>
                        <div style="font-size:.68rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#1649e0;">
                            Excel Ledgers
                        </div>
                        <h2 style="margin:4px 0 0;font-family:Syne,sans-serif;font-size:1.25rem;color:#0a0f1e;">
                            Select Your Ledger Columns
                        </h2>
                        <p style="margin:6px 0 0;color:#7688a8;font-size:.84rem;line-height:1.5;">
                            Your Excel uses different column names. Select which Excel column represents each ledger field.
                        </p>
                    </div>
                    <button type="button" id="excelLedgerColumnClose"
                            style="width:32px;height:32px;border:0;border-radius:9px;background:#f4f7fd;color:#7688a8;cursor:pointer;font-size:1rem;">✕</button>
                </div>
                <div style="margin-top:14px;padding:10px 12px;background:#fff8eb;border:1px solid #f4d59a;border-radius:10px;color:#92400e;font-size:.8rem;">
                    ⚠️ The standard ledger column names were not found in this Excel file.
                </div>
                <div style="margin-top:16px;display:flex;flex-direction:column;gap:12px;">
                    ${needsMapping.map(role => `
                        <div data-excel-ledger-role="${role.key}" style="padding:13px 14px;border:1px solid #e2ebf8;border-radius:12px;background:#f8fbff;">
                            <div style="font-size:.78rem;font-weight:800;color:#1a2035;margin-bottom:7px;">
                                ${escape(role.label)}
                                <span style="font-weight:500;color:#7688a8;"> · expected: ${escape(role.header)}</span>
                            </div>
                            <select data-ledger-role="${role.key}"
                                    style="width:100%;padding:10px 12px;border:1px solid #c8d8f0;border-radius:9px;background:#fff;color:#1a2035;font-size:.9rem;">
                                ${options}
                            </select>
                        </div>
                    `).join('')}
                </div>
                <div style="display:flex;gap:10px;margin-top:20px;">
                    <button type="button" id="excelLedgerColumnCancel"
                            style="flex:0 0 auto;padding:11px 16px;border:1px solid #e2ebf8;border-radius:11px;background:#f4f7fd;color:#7688a8;font-weight:700;cursor:pointer;">
                        Cancel
                    </button>
                    <button type="button" id="excelLedgerColumnConfirm"
                            style="flex:1;padding:11px 16px;border:0;border-radius:11px;background:linear-gradient(135deg,#1649e0,#3324d8);color:#fff;font-weight:800;cursor:pointer;">
                        ✓ Continue Conversion
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const close = () => overlay.remove();
        overlay.querySelector('#excelLedgerColumnClose').addEventListener('click', close);
        overlay.querySelector('#excelLedgerColumnCancel').addEventListener('click', close);
        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

        overlay.querySelector('#excelLedgerColumnConfirm').addEventListener('click', () => {
            const mapping = {};
            const selected = new Set();
            let invalid = false;

            needsMapping.forEach(role => {
                const select = overlay.querySelector(`[data-ledger-role="${role.key}"]`);
                const value = select ? select.value : '';
                if (!value || selected.has(norm(value))) {
                    invalid = true;
                    if (select) select.style.borderColor = '#dc2626';
                    return;
                }
                selected.add(norm(value));
                mapping[role.key] = { source: value, target: role.header };
            });

            if (invalid) {
                const firstInvalid = overlay.querySelector('select[style*="dc2626"]');
                if (firstInvalid) firstInvalid.focus();
                return;
            }

            close();
            onConfirm(mapping);
        });
    }

    async function prepareMappedExcelFile(file, sheetName, mapping) {
        if (!mapping || Object.keys(mapping).length === 0) return file;

        const buffer = await file.arrayBuffer();
        const workbook = XLSX.read(new Uint8Array(buffer), { type: 'array' });
        const ws = workbook.Sheets[sheetName];
        if (!ws || !ws['!ref']) throw new Error('Could not read the selected Excel sheet.');

        const range = XLSX.utils.decode_range(ws['!ref']);
        const headerMap = {};
        for (let col = range.s.c; col <= range.e.c; col++) {
            const cell = ws[XLSX.utils.encode_cell({ r: range.s.r, c: col })];
            if (cell && cell.v != null) headerMap[norm(cell.v)] = { cell, col };
        }

        Object.values(mapping).forEach(item => {
            const found = headerMap[norm(item.source)];
            if (!found) throw new Error(`Selected Excel column "${item.source}" was not found.`);
            found.cell.v = item.target;
            found.cell.t = 's';
        });

        const output = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
        return new File([output], `${file.name.replace(/\.[^.]+$/, '')}_ledger_mapped.xlsx`, {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        });
    }

    function replaceInputFile(input, file) {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
    }

    function init() {
        const form = document.getElementById('convertForm');
        const fileInput = document.getElementById('fileInput');
        const companySelect = document.getElementById('companySelect');
        const sheetSelect = document.getElementById('sheetSelect');
        const voucherSelect = document.getElementById('voucherSelect');
        if (!form || !fileInput || !companySelect || !sheetSelect || !voucherSelect) return;

        // Capture phase runs before the existing converter submit handler.
        form.addEventListener('submit', async function(event) {
            if (window.__excelLedgerMappingBypass) {
                window.__excelLedgerMappingBypass = false;
                return;
            }

            if (companySelect.value !== '__EXCEL_LEDGERS__') return;

            const file = fileInput.files && fileInput.files[0];
            const sheetName = sheetSelect.value;
            if (!file || !sheetName) return;

            try {
                const buffer = await file.arrayBuffer();
                const workbook = XLSX.read(new Uint8Array(buffer), { type: 'array' });
                const ws = workbook.Sheets[sheetName];
                if (!ws) return;

                const vtype = voucherSelect.value;
                const { headers, roles } = getRequiredRoles(ws, vtype);
                const needsMapping = roles.some(role => !findHeader(headers, role.header));
                if (!needsMapping) return;

                event.preventDefault();
                event.stopImmediatePropagation();

                showLedgerColumnPopup(headers, roles, file.name, async mapping => {
                    try {
                        const mappedFile = await prepareMappedExcelFile(file, sheetName, mapping);
                        replaceInputFile(fileInput, mappedFile);
                        window.__excelLedgerMappingBypass = true;
                        form.requestSubmit(document.getElementById('submitBtn'));
                    } catch (err) {
                        if (typeof window.showErrorPopup === 'function') {
                            window.showErrorPopup(err.message || 'Unable to prepare Excel ledger mapping.');
                        } else {
                            alert(err.message || 'Unable to prepare Excel ledger mapping.');
                        }
                    }
                });
            } catch (err) {
                event.preventDefault();
                event.stopImmediatePropagation();
                if (typeof window.showErrorPopup === 'function') {
                    window.showErrorPopup(err.message || 'Unable to inspect Excel ledger columns.');
                } else {
                    alert(err.message || 'Unable to inspect Excel ledger columns.');
                }
            }
        }, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

// Template download function
function downloadTemplate() {
    // Define headers
    const headers = [
        'Sr',
        'GSTIN',
        'Recipient Name',
        'Invoice Number',
        'Invoice date',
        'Invoice Value',
        'Taxable Value',
        'IGST',
        'CGST',
        'SGST',
        'Cess'
    ];

    // Example rows
    const exampleRows = [
        [1, '27AABCT1234E1Z5', 'ABC Enterprises', 'INV-001', '2025-02-20', '11800.00', '10000.00', '0', '900.00', '900.00', '0'],
        [2, '27BBBTX5678F2Y6', 'XYZ Traders', 'INV-002', '2025-02-21', '23600.00', '20000.00', '3600.00', '0', '0', '0'],
        [3, '27CCCP9012G3H7', 'LMN Pvt Ltd', 'INV-003', '2025-02-22', '5900.00', '5000.00', '0', '450.00', '450.00', '0']
    ];

    // Build CSV content
    let csvContent = headers.join(',') + '\n';
    exampleRows.forEach(row => {
        const escapedRow = row.map(cell => 
            typeof cell === 'string' && (cell.includes(',') || cell.includes('"')) 
                ? `"${cell.replace(/"/g, '""')}"` 
                : cell
        ).join(',');
        csvContent += escapedRow + '\n';
    });

    // Create download
    const blob = new Blob([csvContent], { type: 'application/vnd.ms-excel' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'invoice_template.xlsx';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
}
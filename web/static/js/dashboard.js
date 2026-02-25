// dashboard.js
function downloadTemplate() {
    alert('Template download: Create a sample Excel with required columns.\nIn a full version, this would generate a file.');
}

function viewReports() {
    alert('Reports feature coming soon.');
}

async function loadActivity() {
    const activityLog = document.getElementById('activityLog');
    if (!activityLog) return;
    activityLog.innerHTML = `
        <div>[12:34] Converted 25 records from sales.xlsx</div>
        <div>[11:20] Mapping updated</div>
        <div>[10:15] 3 files processed</div>
    `;
}

if (document.getElementById('activityLog')) {
    loadActivity();
}// dashboard page js
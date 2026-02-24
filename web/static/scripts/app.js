/* ================================
   Global helpers
================================ */

function qs(selector) {
    return document.querySelector(selector);
}

function qsa(selector) {
    return document.querySelectorAll(selector);
}

/* ================================
   SPA Navigation
================================ */

function navigateTo(pageId) {
    // hide all pages
    qsa('.page').forEach(p => p.classList.remove('active'));

    // show selected page
    const page = document.getElementById(pageId);
    if (page) page.classList.add('active');

    // update navbar active state
    qsa('.nav-link').forEach(btn => btn.classList.remove('active'));
    const navBtn = document.querySelector(`.nav-link[data-page="${pageId}"]`);
    if (navBtn) navBtn.classList.add('active');

    // 🔥 IMPORTANT FIX
    if (pageId === "image2excel") {
        loadCompaniesIntoSelect();
    }
}

/* ================================
   Company dropdown loader
================================ */

function loadCompaniesIntoSelect() {
    const select = document.getElementById("companySelect");
    if (!select) return;

    // reset dropdown
    select.innerHTML = '<option value="">-- Select Company --</option>';

    const raw = localStorage.getItem("company_rules");
    if (!raw) {
        console.warn("No company_rules found in localStorage");
        return;
    }

    let companies;
    try {
        companies = JSON.parse(raw);
    } catch (e) {
        console.error("Invalid company_rules JSON");
        return;
    }

    Object.keys(companies).forEach(key => {
        const opt = document.createElement("option");
        opt.value = key;
        opt.textContent = companies[key].label || key;
        select.appendChild(opt);
    });

    console.log("Company dropdown populated");
}

/* ================================
   Company Rules (basic helpers)
   (Your existing logic can stay)
================================ */

function showAddCompanyModal() {
    const modal = document.getElementById("companyModal");
    if (modal) modal.style.display = "block";
}

function closeCompanyModal() {
    const modal = document.getElementById("companyModal");
    if (modal) modal.style.display = "none";
}

/* ================================
   Init (runs once)
================================ */

document.addEventListener("DOMContentLoaded", () => {
    // Default page on load
    navigateTo("dashboard");
});
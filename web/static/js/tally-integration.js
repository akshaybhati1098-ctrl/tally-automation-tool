
(function () {
  "use strict";

  // ───────── CONFIG ─────────
const USER_ID = window.USER_ID; // comes from HTML

const API = {
  STATUS: `/api/tally/status/${USER_ID}`,
  LEDGERS: "/api/tally/ledgers",
  MATCH: "/api/match-party",
};

  const state = {
    ledgers: [],
    selectedGroup: "Sundry Debtors",
    file: null,
    matchResults: [],
    overrides: {},
  };

  // ───────── DOM ─────────
  const statusCard = document.getElementById("tallyStatusCard");
  const statusDot = document.getElementById("tallyStatusDot");
  const statusLabel = document.getElementById("tallyStatusLabel");
  const statusCompany = document.getElementById("tallyCompanyName");
  const statusPill = document.getElementById("tallyStatusPill");

  const fetchBtn = document.getElementById("tallyFetchBtn");
  const ledgerCount = document.getElementById("tallyLedgerCount");
  const spinner = document.getElementById("tallyFetchSpinner");

  const matchSection = document.getElementById("tallyMatchSection");
  const matchBody = document.getElementById("tallyMatchTbody");

  const warning = document.getElementById("tallyWarningBanner");
  const warningText = document.getElementById("tallyWarningText");

  const fileInput = document.getElementById("fileInput");
  const sheetSelect = document.getElementById("sheetSelect");

  // ───────── INIT ─────────
  init();

  function init() {
    bindEvents();
    checkStatus();
    setInterval(checkStatus, 5000);
  }

 function bindEvents() {
  const btnDebtors = document.getElementById("btnDebtors");
  const btnCreditors = document.getElementById("btnCreditors");

  console.log({
    fetchBtn,
    fileInput,
    sheetSelect,
    btnDebtors,
    btnCreditors
  });

  // ✅ Group buttons
  if (btnDebtors) {
    btnDebtors.onclick = () => {
      state.selectedGroup = "Sundry Debtors";
      console.log("📦 Selected:", state.selectedGroup);
      // 🔥 Re-run matching if file is already loaded
      if (state.file) {
        runMatching();
      }
    };
  }

  if (btnCreditors) {
    btnCreditors.onclick = () => {
      state.selectedGroup = "Sundry Creditors";
      console.log("📦 Selected:", state.selectedGroup);
      // 🔥 Re-run matching if file is already loaded
      if (state.file) {
        runMatching();
      }
    };
  }

  // ✅ Fetch button (IMPORTANT FIX)
  if (fetchBtn) {
    fetchBtn.onclick = fetchLedgers;
  }

  // ✅ File change
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      state.file = fileInput.files[0];
      if (state.file && state.ledgers.length > 0) {
        runMatching();
      }
    });
  }

  // ✅ Sheet change
  if (sheetSelect) {
    sheetSelect.addEventListener("change", () => {
      if (state.file && state.ledgers.length > 0) {
        runMatching();
      }
    });
  }
}

  // ───────── STATUS ─────────
async function fetchLedgers() {
  spinner.classList.remove("hidden");
  ledgerCount.textContent = "";

  try {
    console.log("📤 Sending group:", state.selectedGroup);

    const res = await fetch(
      `${API.LEDGERS}?group=${encodeURIComponent(state.selectedGroup)}`
    );

    const data = await res.json();

    if (data.status === "waiting") {
      ledgerCount.textContent = "Waiting for connector...";
      ledgerCount.className = "tally-ledger-count warning";

      setTimeout(fetchLedgers, 2000);
      return;
    }

    state.ledgers = data.ledgers || [];

    ledgerCount.textContent = `✓ ${state.ledgers.length} loaded`;
    ledgerCount.className = "tally-ledger-count success";

    if (state.file) runMatching();

  } catch (e) {
    ledgerCount.textContent = "Error loading";
    ledgerCount.className = "tally-ledger-count error";
  }

  spinner.classList.add("hidden");
}
  // ───────── MATCHING ─────────
  console.log("🔁 runMatching called with state.selectedGroup:", state.selectedGroup);
  console.log("📁 state.file:", state.file);
async function runMatching(retries = 20, delay = 500) {
  if (!state.file) {
    console.warn("No file loaded");
    return;
  }

  const sheetName = sheetSelect ? sheetSelect.value : "";
  const formData = new FormData();
  formData.append("file", state.file);
  formData.append("tally_group", state.selectedGroup);
  if (sheetName) formData.append("sheet_name", sheetName);

  console.log("🔁 Sending request with group:", state.selectedGroup);

  try {
    const res = await fetch(API.MATCH, {
      method: "POST",
      body: formData,
    });
    const data = await res.json();

    if (data.status === "waiting") {
      if (retries > 0) {
        setTimeout(() => runMatching(retries - 1, delay), delay);
      } else {
        showWarning("Matching timed out. Please try again.");
      }
      return;
    }

    if (data.status === "ok") {
      state.matchResults = data.match_results || [];
      renderTable();
      matchSection.classList.remove("hidden");
      checkWarnings();
    } else {
      showWarning(data.message || "Matching failed");
    }
  } catch (e) {
    console.error(e);
    showWarning("Matching failed");
  }
}

  // ───────── TABLE ─────────
  function renderTable() {
    matchBody.innerHTML = "";

    state.matchResults.forEach((r, i) => {
      const row = document.createElement("tr");

      row.innerHTML = `
        <td>${i + 1}</td>
        <td>${r.original}</td>
        <td>${r.original_gstin || "-"}</td>
        <td>${r.matched || "-"}</td>
        <td>${r.score || "-"}</td>
        <td>${r.status}</td>
        <td>
          <select data-index="${r.row_index}">
            <option value="">Select</option>
            ${state.ledgers.map((l) => `<option>${l.name}</option>`).join("")}
          </select>
        </td>
      `;

      matchBody.appendChild(row);
    });

    // Manual override
    matchBody.querySelectorAll("select").forEach((sel) => {
      sel.addEventListener("change", (e) => {
        state.overrides[e.target.dataset.index] = e.target.value;
        checkWarnings();
      });
    });
  }

  // ───────── WARNINGS ─────────
  function checkWarnings() {
    const unresolved = state.matchResults.filter(
      (r) => r.status !== "matched" && !state.overrides[r.row_index],
    );

    if (unresolved.length > 0) {
      showWarning(`${unresolved.length} unmatched parties`);
    } else {
      warning.classList.add("hidden");
    }
  }

  function showWarning(msg) {
    warning.classList.remove("hidden");
    warningText.textContent = msg;
  }
})();

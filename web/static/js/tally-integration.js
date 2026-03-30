(function () {
  "use strict";

  // ───────── CONFIG ─────────
  const API = {
    STATUS: "/api/tally/status",
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

  // ───────── EVENTS ─────────
  function bindEvents() {
    document.getElementById("btnDebtors").onclick = () => {
      state.selectedGroup = "Sundry Debtors";
    };

    document.getElementById("btnCreditors").onclick = () => {
      state.selectedGroup = "Sundry Creditors";
    };

    fetchBtn.onclick = fetchLedgers;

    fileInput.addEventListener("change", () => {
      state.file = fileInput.files[0];
      if (state.file && state.ledgers.length > 0) {
        runMatching();
      }
    });

    sheetSelect.addEventListener("change", () => {
      if (state.file && state.ledgers.length > 0) {
        runMatching();
      }
    });
  }

  // ───────── STATUS ─────────
  async function checkStatus() {
    try {
      const res = await fetch("http://127.0.0.1:9000", {
        method: "POST",
        body: "<ENVELOPE><HEADER><VERSION>1</VERSION></HEADER></ENVELOPE>",
        mode: "no-cors",
      });

      // If no error → assume running
      statusDot.className = "tally-status-dot green";
      statusLabel.textContent = "Connected to Tally";
      statusCompany.textContent = "Detected locally";
      statusPill.textContent = "Online";
      statusPill.className = "tally-status-pill green";
      fetchBtn.disabled = false;
    } catch (e) {
      statusDot.className = "tally-status-dot red";
      statusLabel.textContent = "Tally not detected";
      statusCompany.textContent = "Open Tally on port 9000";
      statusPill.textContent = "Offline";
      statusPill.className = "tally-status-pill red";
      fetchBtn.disabled = true;
    }
  }

  // ───────── FETCH LEDGERS ─────────
  async function fetchLedgers() {
    spinner.classList.remove("hidden");
    ledgerCount.textContent = "";

    try {
      const res = await fetch(`${API.LEDGERS}?group=${state.selectedGroup}`);
      const data = await res.json();

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
  async function runMatching() {
    if (!state.file) return;

    const formData = new FormData();
    formData.append("file", state.file);
    formData.append("tally_group", state.selectedGroup);

    try {
      const res = await fetch(API.MATCH, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      state.matchResults = data.match_results || [];

      renderTable();
      matchSection.classList.remove("hidden");

      checkWarnings();
    } catch (e) {
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

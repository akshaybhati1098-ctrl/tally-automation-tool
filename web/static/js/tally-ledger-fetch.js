(function () {
  "use strict";

  function initTallyLedgerFetch() {
    const button = document.getElementById("fetchLedgerBtn");
    const groupSelect = document.getElementById("ledgerTypeSelect");
    if (!button || !groupSelect) return;

    // Keep the fetch control directly below the ledger-group selector.
    const groupContainer = groupSelect.closest(".form-group");
    if (groupContainer) groupContainer.appendChild(button);

    button.textContent = "↻ Fetch Tally Ledgers";
    button.className = "btn-secondary tally-ledger-fetch-small";
    button.style.cssText = "display:block;margin:8px 0 0;width:auto;padding:7px 12px;font-size:.78rem;";

    button.addEventListener("click", async function (event) {
      event.preventDefault();
      event.stopImmediatePropagation();

      const group = groupSelect.value || "Sundry Debtors";
      const overlay = createLedgerFetchOverlay(group);
      document.body.appendChild(overlay);

      const status = overlay.querySelector("#ledgerFetchStatus");
      const count = overlay.querySelector("#ledgerFetchCount");
      const title = overlay.querySelector("#ledgerFetchGroup");
      const spinner = overlay.querySelector("#ledgerFetchSpinner");

      button.disabled = true;
      button.style.opacity = "0.65";
      title.textContent = group;
      status.textContent = "Connecting to Tally";
      count.textContent = "";

      try {
        // Match the cache scope used by Party Matching.  Without the company in
        // this request, a manual refresh was stored under the empty-company key
        // while Party Matching looked up the active-company key.
        const tallyCompany = window.currentTallyCompany || "";
        let data = null;
        for (let attempt = 0; attempt < 30; attempt += 1) {
          const response = await fetch(
            `/api/tally/ledgers?group=${encodeURIComponent(group)}&company=${encodeURIComponent(tallyCompany)}`,
            { cache: "no-store" },
          );
          data = await response.json();

          if (!response.ok) {
            throw new Error(data.detail || "Failed to fetch Tally ledgers");
          }

          if (data.status !== "waiting") break;

          status.textContent = "Waiting for Tally data";
          await new Promise((resolve) => setTimeout(resolve, 500));
        }

        if (!data || data.status === "waiting") {
          throw new Error("Tally connector did not respond in time.");
        }

        const ledgers = Array.isArray(data.ledgers) ? data.ledgers : [];
        window.tallyLedgers = ledgers;

        spinner.style.display = "none";
        status.textContent = "Fetch complete";
        count.textContent = `${ledgers.length.toLocaleString()} ledgers fetched`;

        // Ledger fetch is intentionally isolated from the existing Tally Status card.
        // Do not update #tallyStatusBox here; that card is owned by the Tally status UI.
        const done = overlay.querySelector("#ledgerFetchDone");
        done.style.display = "inline-flex";
        done.onclick = () => overlay.remove();
      } catch (error) {
        spinner.style.display = "none";
        status.textContent = "Fetch failed";
        count.textContent = error?.message || "Unable to fetch ledgers";
        count.classList.add("ledger-fetch-error");

        const done = overlay.querySelector("#ledgerFetchDone");
        done.style.display = "inline-flex";
        done.textContent = "Close";
        done.onclick = () => overlay.remove();
      } finally {
        button.disabled = false;
        button.style.opacity = "";
      }
    }, true);
  }

  function escapeText(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    })[char]);
  }

  function createLedgerFetchOverlay(group) {
    const overlay = document.createElement("div");
    overlay.id = "tallyLedgerFetchOverlay";
    overlay.innerHTML = `
      <style>
        #tallyLedgerFetchOverlay {
          position: fixed;
          inset: 0;
          z-index: 99999;
          display: grid;
          place-items: center;
          padding: 20px;
          background: rgba(10, 15, 30, .30);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
        }

        #tallyLedgerFetchOverlay .ledger-fetch-card {
          width: min(370px, 92vw);
          padding: 34px 32px 28px;
          background: #ffffff;
          border: 1px solid rgba(226, 235, 248, .95);
          border-radius: 20px;
          box-shadow: 0 24px 70px rgba(10, 15, 30, .18),
                      0 4px 16px rgba(10, 15, 30, .06);
          text-align: center;
        }

        #tallyLedgerFetchOverlay .ledger-fetch-spinner {
          width: 34px;
          height: 34px;
          margin: 0 auto 22px;
          border: 3px solid #e8eef8;
          border-top-color: #1649e0;
          border-radius: 50%;
          animation: tallyLedgerSpin .8s linear infinite;
        }

        #tallyLedgerFetchOverlay .ledger-fetch-title {
          font: 600 1.05rem/1.4 "DM Sans", sans-serif;
          letter-spacing: -.01em;
          color: #0a0f1e;
        }

        #tallyLedgerFetchOverlay .ledger-fetch-group {
          margin-top: 6px;
          font: 500 .82rem/1.4 "DM Sans", sans-serif;
          color: #1649e0;
        }

        #tallyLedgerFetchOverlay .ledger-fetch-status {
          margin-top: 20px;
          font: 400 .84rem/1.4 "DM Sans", sans-serif;
          color: #64748b;
        }

        #tallyLedgerFetchOverlay .ledger-fetch-count {
          min-height: 24px;
          margin-top: 8px;
          font: 600 1rem/1.5 "DM Sans", sans-serif;
          color: #0a0f1e;
        }

        #tallyLedgerFetchOverlay .ledger-fetch-error {
          color: #dc2626;
          font-size: .86rem;
        }

        #tallyLedgerFetchOverlay .ledger-fetch-done {
          display: none;
          align-items: center;
          justify-content: center;
          margin: 22px auto 0;
          min-width: 76px;
          padding: 9px 18px;
          border: 0;
          border-radius: 9px;
          background: #1649e0;
          color: #fff;
          font: 600 .82rem "DM Sans", sans-serif;
          cursor: pointer;
          transition: transform .18s ease, box-shadow .18s ease;
        }

        #tallyLedgerFetchOverlay .ledger-fetch-done:hover {
          transform: translateY(-1px);
          box-shadow: 0 5px 14px rgba(22, 73, 224, .24);
        }

        @keyframes tallyLedgerSpin {
          to { transform: rotate(360deg); }
        }
      </style>

      <div class="ledger-fetch-card" role="dialog" aria-modal="true" aria-labelledby="ledgerFetchTitle">
        <div class="ledger-fetch-spinner" id="ledgerFetchSpinner" aria-hidden="true"></div>
        <div class="ledger-fetch-title" id="ledgerFetchTitle">Fetching Tally Ledgers</div>
        <div class="ledger-fetch-group" id="ledgerFetchGroup">${escapeText(group)}</div>
        <div class="ledger-fetch-status" id="ledgerFetchStatus">Connecting to Tally</div>
        <div class="ledger-fetch-count" id="ledgerFetchCount"></div>
        <button type="button" class="ledger-fetch-done" id="ledgerFetchDone">Done</button>
      </div>`;
    return overlay;
  }

  function showExcelRequiredPopup() {
    const existing = document.getElementById("excelRequiredPopup");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "excelRequiredPopup";
    overlay.innerHTML = `
      <style>
        #excelRequiredPopup {
          position: fixed;
          inset: 0;
          z-index: 100000;
          display: grid;
          place-items: center;
          padding: 20px;
          background: rgba(10, 15, 30, .28);
          backdrop-filter: blur(5px);
          -webkit-backdrop-filter: blur(5px);
        }
        #excelRequiredPopup .excel-required-card {
          width: min(380px, 92vw);
          padding: 30px 28px 24px;
          background: #fff;
          border: 1px solid #e2ebf8;
          border-radius: 18px;
          box-shadow: 0 24px 70px rgba(10, 15, 30, .18);
          text-align: center;
        }
        #excelRequiredPopup .excel-required-icon {
          width: 48px;
          height: 48px;
          margin: 0 auto 14px;
          display: grid;
          place-items: center;
          border-radius: 14px;
          background: rgba(22, 73, 224, .09);
          font-size: 24px;
        }
        #excelRequiredPopup h3 {
          margin: 0;
          color: #0a0f1e;
          font: 700 1.05rem/1.4 "DM Sans", sans-serif;
        }
        #excelRequiredPopup p {
          margin: 8px 0 20px;
          color: #7688a8;
          font: 400 .88rem/1.5 "DM Sans", sans-serif;
        }
        #excelRequiredPopup button {
          border: 0;
          border-radius: 9px;
          padding: 9px 20px;
          background: #1649e0;
          color: #fff;
          font: 600 .84rem "DM Sans", sans-serif;
          cursor: pointer;
        }
      </style>
      <div class="excel-required-card" role="dialog" aria-modal="true" aria-labelledby="excelRequiredTitle">
        <div class="excel-required-icon">📄</div>
        <h3 id="excelRequiredTitle">Excel File Required</h3>
        <p>Please upload an Excel file before matching parties.</p>
        <button type="button" id="excelRequiredClose">OK</button>
      </div>`;

    const close = () => overlay.remove();
    overlay.querySelector("#excelRequiredClose").addEventListener("click", close);
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) close();
    });
    document.addEventListener("keydown", function escHandler(event) {
      if (event.key === "Escape") {
        close();
        document.removeEventListener("keydown", escHandler);
      }
    });
    document.body.appendChild(overlay);
  }

  // Guard the Match Parties action before any existing click handler can start.
  // This is capture-phase so it remains safe even if the page has another handler.
  document.addEventListener("click", function (event) {
    const matchButton = event.target.closest?.("#matchBtn");
    if (!matchButton) return;

    const fileInput = document.getElementById("fileInput");
    const hasFile = !!(fileInput && fileInput.files && fileInput.files.length);
    if (hasFile) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    showExcelRequiredPopup();
  }, true);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTallyLedgerFetch);
  } else {
    initTallyLedgerFetch();
  }
})();

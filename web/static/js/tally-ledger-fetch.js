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
        let data = null;
        for (let attempt = 0; attempt < 30; attempt += 1) {
          const response = await fetch(
            `/api/tally/ledgers?group=${encodeURIComponent(group)}`,
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

        const statusBox = document.getElementById("tallyStatusBox");
        if (statusBox) {
          statusBox.innerHTML = `<strong>✓ ${ledgers.length.toLocaleString()} ledgers fetched</strong><br><small>${escapeText(group)}</small>`;
        }

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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTallyLedgerFetch);
  } else {
    initTallyLedgerFetch();
  }
})();

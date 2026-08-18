(function () {
  "use strict";

  function initTallyLedgerFetch() {
    const button = document.getElementById("fetchLedgerBtn");
    const groupSelect = document.getElementById("ledgerTypeSelect");
    if (!button || !groupSelect) return;

    // Move the small fetch control directly below the ledger-group selector.
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

      button.disabled = true;
      button.style.opacity = "0.65";
      title.textContent = group;
      status.textContent = "Connecting to Tally...";
      count.textContent = "0 ledgers fetched";

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

          status.textContent = "Waiting for Tally data...";
          await new Promise((resolve) => setTimeout(resolve, 500));
        }

        if (!data || data.status === "waiting") {
          throw new Error("Tally connector did not respond in time.");
        }

        const ledgers = Array.isArray(data.ledgers) ? data.ledgers : [];
        window.tallyLedgers = ledgers;
        count.textContent = `${ledgers.length.toLocaleString()} ledgers fetched`;
        status.textContent = "Ledger fetch completed";

        const statusBox = document.getElementById("tallyStatusBox");
        if (statusBox) {
          statusBox.innerHTML = `<strong>✓ ${ledgers.length.toLocaleString()} ledgers fetched</strong><br><small>${escapeText(group)}</small>`;
        }

        const done = overlay.querySelector("#ledgerFetchDone");
        done.style.display = "inline-flex";
        done.onclick = () => overlay.remove();
      } catch (error) {
        status.textContent = "Ledger fetch failed";
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
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
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
          background: rgba(10, 15, 30, .38);
          backdrop-filter: blur(5px);
          padding: 20px;
        }
        #tallyLedgerFetchOverlay .ledger-fetch-card {
          width: min(390px, 92vw);
          background: #fff;
          border: 1px solid #e2ebf8;
          border-radius: 22px;
          padding: 30px 28px 24px;
          box-shadow: 0 24px 70px rgba(10,15,30,.22);
          text-align: center;
        }
        #tallyLedgerFetchOverlay .ledger-fetch-face {
          width: 64px;
          height: 64px;
          margin: 0 auto 18px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          font-size: 31px;
          background: #f4f7fd;
          border: 1px solid #e2ebf8;
          animation: tallyLedgerPulse 1.35s ease-in-out infinite;
        }
        #tallyLedgerFetchOverlay .ledger-fetch-title {
          font: 700 1.05rem "DM Sans", sans-serif;
          color: #0a0f1e;
        }
        #tallyLedgerFetchOverlay .ledger-fetch-group {
          margin-top: 5px;
          font: 600 .82rem "DM Sans", sans-serif;
          color: #1649e0;
        }
        #tallyLedgerFetchOverlay .ledger-fetch-status {
          margin-top: 18px;
          font: 600 .82rem "DM Sans", sans-serif;
          color: #344260;
        }
        #tallyLedgerFetchOverlay .ledger-fetch-count {
          margin-top: 8px;
          font: 800 1.45rem "Syne", sans-serif;
          color: #0a0f1e;
        }
        #tallyLedgerFetchOverlay .ledger-fetch-error {
          color: #dc2626;
          font-size: .9rem;
        }
        #tallyLedgerFetchOverlay .ledger-fetch-done {
          display: none;
          margin-top: 20px;
          border: 0;
          border-radius: 10px;
          padding: 9px 20px;
          background: #1649e0;
          color: #fff;
          font: 700 .8rem "DM Sans", sans-serif;
          cursor: pointer;
        }
        @keyframes tallyLedgerPulse {
          0%,100% { transform: scale(1); opacity: .9; }
          50% { transform: scale(1.06); opacity: 1; }
        }
      </style>
      <div class="ledger-fetch-card" role="dialog" aria-modal="true" aria-labelledby="ledgerFetchTitle">
        <div class="ledger-fetch-face" aria-hidden="true">🙂</div>
        <div class="ledger-fetch-title" id="ledgerFetchTitle">Fetching Tally Ledgers</div>
        <div class="ledger-fetch-group" id="ledgerFetchGroup">${escapeText(group)}</div>
        <div class="ledger-fetch-status" id="ledgerFetchStatus">Connecting to Tally...</div>
        <div class="ledger-fetch-count" id="ledgerFetchCount">0 ledgers fetched</div>
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

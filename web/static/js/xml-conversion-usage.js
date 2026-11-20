(function () {
  "use strict";

  let loadedForVisiblePage = false;
  let popupWrapped = false;

  function ensureCard() {
    if (document.getElementById("xmlConversionUsageCol")) return;

    const remainingMatches = document.getElementById("remainingMatches");
    if (!remainingMatches) return;

    const parentCol = remainingMatches.closest(".col-lg-6");
    if (!parentCol || !parentCol.parentElement) return;

    const col = document.createElement("div");
    col.id = "xmlConversionUsageCol";
    col.className = "col-lg-6 mb-4";
    col.innerHTML = `
      <div class="card summary-card summary-xml-card shadow-sm border-0 rounded-4 h-100">
        <div class="card-body p-4">
          <div class="summary-xml-header">
            <div class="summary-xml-heading">
              <span class="summary-xml-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none"><path d="M5 3.5h9l5 5v12H5a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 5 3.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M14 3.8v5h5M7.5 13h9M7.5 16.5h9" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>
              </span>
              <span class="summary-xml-title">Excel to Tally XML</span>
            </div>
          </div>
          <div class="summary-xml-value-row">
            <h1 id="xmlRowsRemaining" class="summary-xml-value">-</h1>
            <span class="summary-xml-remaining-label">rows left</span>
          </div>
          <div class="summary-xml-progress-heading">
            <small>Usage</small>
            <strong id="xmlUsagePercentText">0%</strong>
          </div>
          <div class="progress summary-xml-progress" role="progressbar" aria-label="XML row usage" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
            <div id="xmlUsageBar" class="progress-bar" style="width:0%;"></div>
          </div>
          <div class="summary-xml-counts">
            <small id="xmlUsageText">Loading...</small>
            <small id="xmlUsageTotal">- total</small>
          </div>
        </div>
      </div>`;

    parentCol.parentElement.appendChild(col);
  }

  function applyUsage(data) {
    const sub = data && data.subscription;
    if (!sub) return;

    ensureCard();

    const limit = Number(sub.xml_row_limit || 0);
    const used = Math.max(0, Number(sub.xml_used_count || 0));
    const remaining = Math.max(0, Number(sub.xml_remaining || 0));

    const remainingEl = document.getElementById("xmlRowsRemaining");
    const usageTextEl = document.getElementById("xmlUsageText");
    const usageTotalEl = document.getElementById("xmlUsageTotal");
    const usagePercentTextEl = document.getElementById("xmlUsagePercentText");
    const usageBar = document.getElementById("xmlUsageBar");
    const percent = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
    const roundedPercent = Math.round(percent);

    if (remainingEl) remainingEl.textContent = remaining.toLocaleString("en-IN");
    if (usageTextEl) usageTextEl.textContent = `${used.toLocaleString("en-IN")} used`;
    if (usageTotalEl) usageTotalEl.textContent = `${limit.toLocaleString("en-IN")} total`;
    if (usagePercentTextEl) usagePercentTextEl.textContent = `${roundedPercent}%`;

    if (usageBar) {
      usageBar.style.width = `${percent}%`;
      usageBar.setAttribute("aria-valuenow", String(roundedPercent));
      usageBar.setAttribute("aria-valuemin", "0");
      usageBar.setAttribute("aria-valuemax", "100");
    }
  }

  function enhanceLimitPopup() {
    if (popupWrapped || typeof window.showErrorPopup !== "function") return;

    const originalShowErrorPopup = window.showErrorPopup;
    window.showErrorPopup = function (message, ...args) {
      const text = String(message || "");
      if (text.includes("XML conversion rows remaining")) {
        message = `⚠️ XML Conversion Limit\n\n${text}`;
      }
      return originalShowErrorPopup.call(this, message, ...args);
    };
    popupWrapped = true;
  }

  async function refresh() {
    try {
      const response = await fetch("/api/subscription/me", {
        credentials: "same-origin",
        cache: "no-store"
      });
      if (!response.ok) return;
      applyUsage(await response.json());
    } catch (error) {
      console.error("Unable to refresh XML conversion usage:", error);
    }
  }

  function handleVisibility() {
    const page = document.getElementById("subscription");
    const visible = !!page && page.classList.contains("active");

    if (!visible) {
      loadedForVisiblePage = false;
      return;
    }

    if (!loadedForVisiblePage) {
      loadedForVisiblePage = true;
      refresh();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    handleVisibility();
    enhanceLimitPopup();

    const page = document.getElementById("subscription");
    if (page) {
      const observer = new MutationObserver(handleVisibility);
      observer.observe(page, { attributes: true, attributeFilter: ["class"] });
    }

    window.setInterval(function () {
      if (document.getElementById("subscription")?.classList.contains("active")) {
        refresh();
      }
      enhanceLimitPopup();
    }, 1000);
  });
})();

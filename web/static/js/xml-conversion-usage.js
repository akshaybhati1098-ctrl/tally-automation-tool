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
      <div class="card summary-card shadow-sm border-0 rounded-4 h-100">
        <div class="card-body p-4">
          <h5 class="eyebrow">Excel → Tally XML Usage</h5>
          <h1 id="xmlRowsRemaining" class="fw-bold mt-2" style="font-family:var(--sp-font-mono);font-weight:800;color:var(--sp-accent);">-</h1>
          <small class="text-muted">Remaining XML Conversion Rows</small>
          <div class="progress mt-4" style="height:12px;">
            <div id="xmlUsageBar" class="progress-bar" style="width:0%;"></div>
          </div>
          <div class="mt-3"><small id="xmlUsageText">Loading...</small></div>
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
    const usageBar = document.getElementById("xmlUsageBar");

    if (remainingEl) remainingEl.textContent = remaining.toLocaleString("en-IN");

    if (usageTextEl) {
      usageTextEl.textContent = `${used.toLocaleString("en-IN")} / ${limit.toLocaleString("en-IN")} rows used`;
    }

    if (usageBar) {
      const percent = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
      usageBar.style.width = `${percent}%`;
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

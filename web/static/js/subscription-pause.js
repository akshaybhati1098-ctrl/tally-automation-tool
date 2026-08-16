(function () {
  "use strict";

  function ensurePausedBanner() {
    const page = document.querySelector("#subscription .subscription-page");
    if (!page) return null;

    let banner = document.getElementById("subscriptionPausedBanner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "subscriptionPausedBanner";
      banner.className = "alert alert-warning border-0 rounded-4 shadow-sm mb-4";
      banner.style.display = "none";
      banner.innerHTML = `
        <div class="d-flex align-items-start gap-3">
          <div style="font-size:24px;">⏸️</div>
          <div>
            <div class="fw-bold">Subscription Paused</div>
            <div class="small">Your subscription is currently paused by the administrator. Party Matching and Excel → Tally XML conversion are unavailable until your subscription is resumed.</div>
          </div>
        </div>`;
      page.querySelector(".page-container")?.insertBefore(banner, page.querySelector(".page-container").children[1] || null);
    }
    return banner;
  }

  async function refreshPausedState() {
    try {
      const response = await fetch("/api/subscription/me", {
        credentials: "same-origin",
        cache: "no-store"
      });
      if (!response.ok) return;

      const data = await response.json();
      const subscription = data.subscription;
      if (!subscription) return;

      const paused = String(subscription.subscription_status || "").toUpperCase() === "PAUSED";
      const banner = ensurePausedBanner();
      if (banner) banner.style.display = paused ? "block" : "none";

      const status = document.getElementById("planStatus");
      if (status && paused) {
        status.textContent = "⏸ PAUSED";
        status.className = "text-warning fw-bold";
      }
    } catch (error) {
      console.error("Unable to refresh subscription pause state:", error);
    }
  }

  function handleVisibility() {
    const page = document.getElementById("subscription");
    if (page && page.classList.contains("active")) refreshPausedState();
  }

  document.addEventListener("DOMContentLoaded", function () {
    handleVisibility();
    const page = document.getElementById("subscription");
    if (page) {
      new MutationObserver(handleVisibility).observe(page, {
        attributes: true,
        attributeFilter: ["class"]
      });
    }
  });
})();

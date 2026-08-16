(function () {
  "use strict";

  let currentUserId = null;
  let currentSubscription = null;

  function ensureControls() {
    const modal = document.getElementById("customerModal");
    if (!modal) return;

    const body = modal.querySelector(".modal-body");
    const footer = modal.querySelector(".modal-footer");
    if (!body || !footer) return;

    if (!document.getElementById("cm_subscription_status")) {
      const row = document.createElement("div");
      row.className = "row mt-3";
      row.innerHTML = `
        <div class="col-md-6">
          <label class="form-label">Subscription Status</label>
          <input id="cm_subscription_status" class="form-control" readonly>
        </div>
        <div class="col-md-6 d-flex align-items-end">
          <button id="cm_pause_toggle" type="button" class="btn w-100 fw-semibold"></button>
        </div>`;
      body.appendChild(row);
    }

    if (!document.getElementById("cm_pause_toggle")) return;
    document.getElementById("cm_pause_toggle").onclick = togglePause;
  }

  function renderStatus(subscription) {
    ensureControls();
    const status = String(subscription?.subscription_status || "ACTIVE").toUpperCase();
    const statusInput = document.getElementById("cm_subscription_status");
    const toggle = document.getElementById("cm_pause_toggle");
    if (!statusInput || !toggle) return;

    if (status === "PAUSED") {
      statusInput.value = "⏸ PAUSED";
      statusInput.classList.add("text-warning", "fw-bold");
      toggle.textContent = "▶ Resume Subscription";
      toggle.className = "btn btn-success w-100 fw-semibold";
    } else {
      statusInput.value = "● ACTIVE";
      statusInput.classList.remove("text-warning", "fw-bold");
      toggle.textContent = "⏸ Pause Subscription";
      toggle.className = "btn btn-outline-warning w-100 fw-semibold";
    }
  }

  async function loadSubscription(userId) {
    const response = await fetch(`/admin/api/admin/user/${userId}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Unable to load subscription details.");
    const data = await response.json();
    currentSubscription = data.subscription;
    renderStatus(currentSubscription);
  }

  async function togglePause() {
    if (!currentUserId || !currentSubscription) return;

    const paused = String(currentSubscription.subscription_status || "").toUpperCase() === "PAUSED";
    const targetStatus = paused ? "ACTIVE" : "PAUSED";
    const actionText = paused ? "resume this subscription" : "pause this subscription";

    if (!confirm(`Are you sure you want to ${actionText}?`)) return;

    const payload = {
      plan_id: Number(currentSubscription.plan_id),
      match_limit: Number(currentSubscription.match_limit ?? 0),
      subscription_status: targetStatus,
      plan_expiry: currentSubscription.plan_expiry || null
    };

    try {
      const response = await fetch(`/admin/api/admin/user/${currentUserId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.detail || data.error || "Unable to update subscription.");
      }

      alert(paused ? "Subscription resumed successfully." : "Subscription paused successfully.");
      location.reload();
    } catch (error) {
      console.error("Subscription pause/resume failed:", error);
      alert(error.message || "Unable to update subscription.");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    ensureControls();

    document.addEventListener("click", function (event) {
      const manageButton = event.target.closest(".manage-user");
      if (!manageButton) return;

      currentUserId = manageButton.dataset.userId;
      setTimeout(function () {
        loadSubscription(currentUserId).catch(function (error) {
          console.error("Unable to load subscription pause state:", error);
        });
      }, 100);
    });
  });
})();

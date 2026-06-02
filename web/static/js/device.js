/**
 * Persistent device id via localStorage (shared across logged-in users on this browser).
 */
(function () {
  "use strict";

  const STORAGE_KEY = "device_id";
  const CONNECTOR_STATUS_URL = "/api/connector/status";

  function generateDeviceId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return "dev-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  function ensureDeviceId() {
    window.DEVICE_ID = localStorage.getItem(STORAGE_KEY);
    if (!window.DEVICE_ID) {
      window.DEVICE_ID = generateDeviceId();
      localStorage.setItem(STORAGE_KEY, window.DEVICE_ID);
    }
    console.log("DEVICE_ID:", window.DEVICE_ID);
    return window.DEVICE_ID;
  }

  window.initDeviceId = function initDeviceId() {
    return ensureDeviceId();
  };

  window.getDeviceId = function getDeviceId() {
    return window.DEVICE_ID || ensureDeviceId();
  };

  window.fetchConnectorStatus = function fetchConnectorStatus() {
    const deviceId = window.getDeviceId();
    return fetch(CONNECTOR_STATUS_URL, {
      headers: {
        "X-Device-ID": deviceId,
      },
    }).then((res) => {
      const resolvedDeviceId = res.headers.get("X-Resolved-Device-ID");
      if (resolvedDeviceId && resolvedDeviceId !== deviceId) {
        localStorage.setItem(STORAGE_KEY, resolvedDeviceId);
        window.DEVICE_ID = resolvedDeviceId;
      }
      return res;
    });
  };

  ensureDeviceId();
})();

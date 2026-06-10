/**
 * Machine-scoped connector discovery via localhost endpoint.
 * All browsers on the same Windows machine discover the same connector device_id.
 */
(function () {
  "use strict";

  const CONNECTOR_DISCOVERY_URL = "http://127.0.0.1:8765/device-info";
  const CONNECTOR_STATUS_URL = "/api/connector/status";
  const DISCOVERY_TIMEOUT = 1000; // 1 second timeout

  let connectorDeviceId = null;
  let connectorAvailable = false;

  /**
   * Discover connector's device_id from local endpoint.
   * This enables machine-scoped status: all browsers on the same PC
   * will see the same connector status.
   */
  async function discoverConnectorDeviceId() {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), DISCOVERY_TIMEOUT);

      const res = await fetch(CONNECTOR_DISCOVERY_URL, {
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        connectorDeviceId = data.device_id;
        connectorAvailable = true;
        console.log("[Connector Discovery] Machine device_id:", connectorDeviceId);
        return connectorDeviceId;
      }
    } catch (err) {
      console.log("[Connector Discovery] Unavailable:", err.message);
    }

    connectorAvailable = false;
    connectorDeviceId = null;
    return null;
  }

  window.getConnectorDeviceId = function getConnectorDeviceId() {
    return connectorDeviceId;
  };

  window.isConnectorAvailable = function isConnectorAvailable() {
    return connectorAvailable;
  };

  /**
   * Fetch connector status using discovered machine device_id.
   * If connector is not available, return "not_running" status.
   */
  window.fetchConnectorStatus = function fetchConnectorStatus() {
    if (!connectorAvailable || !connectorDeviceId) {
      return Promise.resolve(
        new Response(
          JSON.stringify({ status: "not_running", company: null }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }

    return fetch(CONNECTOR_STATUS_URL, {
      headers: {
        "X-Device-ID": connectorDeviceId,
      },
    });
  };

  /**
   * Initialize connector discovery on page load.
   */
  window.initConnectorDiscovery = function initConnectorDiscovery() {
    return discoverConnectorDeviceId();
  };

  // Auto-discover connector on script load
  discoverConnectorDeviceId();
})();

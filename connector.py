import os
import uuid
import requests
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# ================================
# CONFIG
# ================================
SERVER_URL = "https://tally-automation-tool.onrender.com"
TALLY_URL = os.environ.get("TALLY_URL", "http://127.0.0.1:9000")

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEVICE_ID_FILE = _SCRIPT_DIR / "connector_device_id.txt"


def load_user_id() -> str:
    """Account id for jobs/results (session user_id)."""
    env_id = os.environ.get("TALLY_USER_ID", "").strip()
    if env_id:
        return env_id

    config_path = _SCRIPT_DIR / "connector_user_id.txt"
    if config_path.exists():
        value = config_path.read_text(encoding="utf-8").strip()
        if value:
            return value

    raise SystemExit(
        "Connector user id not configured.\n"
        "Set TALLY_USER_ID or create connector_user_id.txt with your account user id."
    )


def load_device_id() -> str:
    """
    Machine device id for connector heartbeats.
    Set CONNECTOR_DEVICE_ID to match browser localStorage device_id on this PC.
    """
    env_id = os.environ.get("CONNECTOR_DEVICE_ID", "").strip()
    if env_id:
        return env_id

    if _DEVICE_ID_FILE.exists():
        value = _DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value

    device_id = str(uuid.uuid4())
    _DEVICE_ID_FILE.write_text(device_id, encoding="utf-8")
    print(
        "⚠️ New DEVICE_ID created for connector. "
        "Set browser localStorage device_id to this value, or set CONNECTOR_DEVICE_ID:\n"
        f"   {device_id}"
    )
    return device_id


USER_id = load_user_id()
DEVICE_id = load_device_id()

STATUS_XML = """
<ENVELOPE>
 <HEADER>
  <VERSION>1</VERSION>
  <TALLYREQUEST>Export</TALLYREQUEST>
  <TYPE>Collection</TYPE>
  <ID>Company Collection</ID>
 </HEADER>
 <BODY>
  <DESC>
   <STATICVARIABLES>
    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
   </STATICVARIABLES>
   <TDL>
    <TDLMESSAGE>
     <COLLECTION NAME="Company Collection">
      <TYPE>Company</TYPE>
      <FETCH>Name</FETCH>
     </COLLECTION>
    </TDLMESSAGE>
   </TDL>
  </DESC>
 </BODY>
</ENVELOPE>
"""


def get_tally_status():
    try:
        res = requests.post(TALLY_URL, data=STATUS_XML, timeout=3)
        print("🔎 Tally response:", res.text[:200])

        if res.status_code != 200 or not res.text.strip():
            return "not_running", None

        root = ET.fromstring(res.text)
        company = None
        for tag in ["COMPANYNAME", "NAME", "CMPNAME", "CMPINFO"]:
            elem = root.find(f".//{tag}")
            if elem is not None and elem.text:
                company = elem.text.strip()
                break

        if company:
            return "running", company
        return "not_running", None

    except Exception as e:
        print("❌ Tally check error:", e)
        return "not_running", None


def send_heartbeat(status, company=None):
    try:
        print("DEVICE_ID:", DEVICE_id)
        print("SENDING STATUS:", status)
        print("COMPANY:", company)
        res = requests.post(
            f"{SERVER_URL}/api/connector/heartbeat/{DEVICE_id}",
            json={"status": status, "company": company},
            timeout=5,
        )
        if res.status_code >= 400:
            print(f"❌ Heartbeat failed: HTTP {res.status_code} {res.text[:200]}")
        else:
            print(f"🟢 Heartbeat sent for device {DEVICE_id}")
    except Exception as e:
        print("❌ Heartbeat error:", e)


def get_job():
    try:
        print("CURRENT USER:", USER_id)
        res = requests.get(f"{SERVER_URL}/api/get-job/{USER_id}", timeout=5)
        print("📡 GET JOB RESPONSE:", res.text)
        if res.status_code == 200 and res.text.strip():
            return res.json()
        return {}
    except Exception as e:
        print("❌ Job fetch error:", e)
        return {}


def send_result(data):
    try:
        print("CURRENT USER:", USER_id)
        requests.post(
            f"{SERVER_URL}/api/submit-result/{USER_id}",
            json={"data": data},
            timeout=10,
        )
        print("✅ Result sent")
    except Exception as e:
        print("❌ Result send error:", e)


def main():
    print("🚀 Connector started...")
    print("DEVICE_ID:", DEVICE_id)
    print("CURRENT USER (jobs):", USER_id)
    print(f"Server: {SERVER_URL}")
    print(
        "Tip: browser localStorage device_id must match DEVICE_ID above for status to show online.\n"
    )

    while True:
        try:
            print("🔄 Checking system...")
            status, company = get_tally_status()
            send_heartbeat(status, company)

            job = get_job()
            if job:
                print("📥 Job received")
                xml = job.get("xml")
                if xml:
                    res = requests.post(
                        TALLY_URL,
                        data=xml.encode("utf-8"),
                        headers={"Content-Type": "text/xml"},
                        timeout=10,
                    )
                    send_result(res.text)
                    print("✅ Job processed\n")
        except Exception as e:
            print("❌ Main loop error:", e)

        time.sleep(5)


if __name__ == "__main__":
    main()

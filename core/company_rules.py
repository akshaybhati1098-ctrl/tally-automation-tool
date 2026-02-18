import json
import os

RULES_FILE = os.path.join(os.path.dirname(__file__), "company_rules.json")

def load_rules():
    """Load company rules from JSON. Create default if not exists."""
    default = {
        "DR_LOGISTIC": {
            "label": "DR Logistic",
            "taxable": "Total Bill Amount",
            "cgst": "CGST @",
            "sgst": "SGST @",
            "igst": None,
            "fuel": "Fuel",
            "shipment": "Shipment",
            "invoice_total": "GRAND TOTAL"
        }
    }
    if not os.path.exists(RULES_FILE):
        with open(RULES_FILE, "w") as f:
            json.dump(default, f, indent=4)
        return default
    with open(RULES_FILE, "r") as f:
        return json.load(f)

def save_rules(rules):
    """Save company rules to JSON."""
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=4)
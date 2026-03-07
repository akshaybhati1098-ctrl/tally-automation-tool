import json
import os

# HuggingFace persistent storage
DATA_DIR = os.path.dirname(__file__)
os.makedirs(DATA_DIR, exist_ok=True)

MAP_FILE = os.path.join(DATA_DIR, "mapping.json")


def get_default_mapping():
    return {
        "COMPANY_STATE": "Uttar Pradesh",
        "DEBUG": False,
        "SALES": {
            "0": "Sales - 0%",
            "5": "Local Sale @5%",
            "12": "Local Sale @12%",
            "18": "Local Sale @18%",
            "28": "Local Sale @28%"
        },
        "SALES_IGST": {
            "0": "Sales - IGST 0%",
            "5": "Interstate Sale @5%",
            "12": "Interstate Sale @12%",
            "18": "Interstate Sale @18%",
            "28": "Interstate Sale @28%"
        },
        "PURCHASE": {
            "0": "Purchase - 0%",
            "5": "Local Purchase @5%",
            "12": "Local Purchase @12%",
            "18": "Local Purchase @18%",
            "28": "Local Purchase @28%"
        },
        "CGST_RATES": {
            "5": "CGST @ 2.5%",
            "12": "CGST @ 6%",
            "18": "CGST @ 9%",
            "28": "CGST @ 14%"
        },
        "SGST_RATES": {
            "5": "SGST @ 2.5%",
            "12": "SGST @ 6%",
            "18": "SGST @ 9%",
            "28": "SGST @ 14%"
        },
        "IGST_RATES": {
            "5": "IGST @ 5%",
            "12": "IGST @ 12%",
            "18": "IGST @ 18%",
            "28": "IGST @ 28%"
        }
    }


def load_mapping_json():
    if not os.path.exists(MAP_FILE):
        data = {
            "companies": ["Default"],
            "mappings": {
                "Default": get_default_mapping()
            }
        }
        save_mapping_json(data)
        return data

    with open(MAP_FILE, "r") as f:
        data = json.load(f)

    if "companies" not in data:
        data = {
            "companies": ["Default"],
            "mappings": {
                "Default": data
            }
        }
        save_mapping_json(data)

    return data


def save_mapping_json(data):
    with open(MAP_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_companies():
    return load_mapping_json().get("companies", [])


def add_company(name):
    data = load_mapping_json()

    if name in data["companies"]:
        raise ValueError(f"Company '{name}' already exists")

    data["companies"].append(name)
    data["mappings"][name] = get_default_mapping()

    save_mapping_json(data)


def delete_company(name):
    if name == "Default":
        raise ValueError("Cannot delete Default company")

    data = load_mapping_json()

    if name not in data["companies"]:
        raise ValueError(f"Company '{name}' not found")

    data["companies"].remove(name)
    del data["mappings"][name]

    save_mapping_json(data)


def get_company_mapping(name):
    data = load_mapping_json()

    if name not in data["mappings"]:
        raise ValueError(f"Company '{name}' not found")

    return data["mappings"][name]


def save_company_mapping(name, mapping):
    data = load_mapping_json()

    if name not in data["mappings"]:
        raise ValueError(f"Company '{name}' not found")

    data["mappings"][name] = mapping

    save_mapping_json(data)
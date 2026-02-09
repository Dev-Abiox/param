import requests

BASE_URL = "http://127.0.0.1:8001/api"

def verify_indices():
    # 1. Login
    resp = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin"})
    token = resp.json()["access_token"]
    
    # 2. Predict
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "patientId": "TEST001",
        "cbc": {
            "Hb_g_dL": 13.5,
            "RBC_million_uL": 4.8,
            "HCT_percent": 42.0,
            "MCV_fL": 88.0,
            "MCH_pg": 29.0,
            "MCHC_g_dL": 33.0,
            "RDW_percent": 13.0,
            "WBC_10_3_uL": 7.5,
            "Platelets_10_3_uL": 250,
            "Neutrophils_percent": 60,
            "Lymphocytes_percent": 30,
            "Age": 30,
            "Sex": "M"
        }
    }
    
    resp = requests.post(f"{BASE_URL}/screening/predict", json=payload, headers=headers)
    print("Status:", resp.status_code)
    if resp.status_code == 200:
        data = resp.json()
        if "indices" in data:
            print("SUCCESS: 'indices' key found.")
            print("Indices:", data["indices"])
        else:
            print("FAILURE: 'indices' key NOT found.")
    else:
        print("Error:", resp.text)

if __name__ == "__main__":
    verify_indices()

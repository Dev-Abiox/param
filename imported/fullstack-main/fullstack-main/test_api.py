import requests

BASE_URL = "http://127.0.0.1:8001/api"

def test_api():
    # 1. Login
    print("Logging in...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin"})
    if resp.status_code != 200:
        print("Login failed:", resp.text)
        return
    token = resp.json()["access_token"]
    print("Login success.")

    # 2. Predict
    print("Sending prediction request...")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "patientId": "TEST-PATIENT",
        "cbc": {
            "Hb_g_dL": 13.5,
            "RBC_million_uL": 4.8,
            "HCT_percent": 42.0,
            "MCV_fL": 90.0,
            "MCH_pg": 30.0,
            "MCHC_g_dL": 34.0,
            "RDW_percent": 13.0,
            "WBC_10_3_uL": 7.5,
            "Platelets_10_3_uL": 250.0,
            "Neutrophils_percent": 60.0,
            "Lymphocytes_percent": 30.0,
            "Age": 35,
            "Sex": "M"
        }
    }
    
    resp = requests.post(f"{BASE_URL}/screening/predict", json=payload, headers=headers)
    if resp.status_code == 200:
        print("Prediction success!")
        print(resp.json())
    else:
        print("Prediction failed:", resp.status_code)
        print(resp.text)

if __name__ == "__main__":
    test_api()

import requests

BASE_URL = "http://127.0.0.1:8000/api"

def test_analytics():
    # 1. Login
    resp = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin"})
    if resp.status_code != 200:
        print("Login failed")
        return
    token = resp.json()["access_token"]

    # 2. Get Stats
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/analytics/summary", headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        print("Success!")
        print("Keys:", list(data.keys()))
        if "modelMetrics" in data and "distribution" in data:
            print("Structure looks correct.")
        else:
            print("Missing expected keys.")
    else:
        print("Failed:", resp.status_code, resp.text)

if __name__ == "__main__":
    test_analytics()

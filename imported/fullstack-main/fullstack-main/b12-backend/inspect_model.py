import joblib
import pandas as pd
import sys

try:
    model = joblib.load("app/b12_clinical_engine_v1.0/stage1_normal_vs_abnormal.pkl")
    print("Model Type:", type(model))
    
    if hasattr(model, "feature_names_in_"):
        print("Expected Features:", list(model.feature_names_in_))
    elif hasattr(model, "get_booster"): # XGBoost
        print("Expected Features:", model.get_booster().feature_names)
    else:
        print("Could not determine feature names via attributes.")
        
except Exception as e:
    print("Error loading model:", e)

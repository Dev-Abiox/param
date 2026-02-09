import joblib
import json
import pandas as pd


class B12ClinicalEngine:
    def __init__(self, model_dir="app/b12_clinical_engine_v1.0"):
        self.stage1 = joblib.load(f"{model_dir}/stage1_normal_vs_abnormal.pkl")
        self.stage2 = joblib.load(f"{model_dir}/stage2_borderline_vs_deficient.pkl")

        with open(f"{model_dir}/thresholds.json") as f:
            self.thresholds = json.load(f)

    # ---------------------------
    # INDICES
    # ---------------------------
    def add_indices(self, row):
        row["Mentzer"] = row["MCV"] / row["RBC"] if row["RBC"] > 0 else 0
        row["RDW_MCV"] = row["RDW"] / row["MCV"] if row["MCV"] > 0 else 0
        row["Pancytopenia"] = int(
            (row["Hb"] < 12) and (row["WBC"] < 4) and (row["Platelets"] < 150)
        )
        return row

    # ---------------------------
    # RULES (EXPLAINABILITY ONLY)
    # ---------------------------
    def apply_rules(self, row):
        score = 0
        rules = []

        if row["MCV"] > 100:
            score += 1; rules.append("Macrocytosis")
        if row["RDW"] > 15:
            score += 1; rules.append("High RDW")
        if row["Mentzer"] > 13:
            score += 1; rules.append("Ineffective erythropoiesis")
        if row["Pancytopenia"] == 1:
            score += 2; rules.append("Pancytopenia")

        if row["MCV"] < 100 and row["Pancytopenia"] == 0:
            score -= 0.5; rules.append("No macrocytosis / no pancytopenia")
        if row["Hb"] > 11 and row["Platelets"] > 150:
            score -= 0.5; rules.append("Preserved cell counts")
        if row["MCV"] < 96 and row["RDW"] < 14 and row["Hb"] > 12:
            score -= 1; rules.append("Normal marrow pattern")

        return score, rules

    # ---------------------------
    # MAIN PREDICTION
    # ---------------------------
    def predict(self, cbc_dict):

        # Build dataframe
        df = pd.DataFrame([cbc_dict])

        expected_cols = [
            'Age', 'Sex', 'Hb', 'RBC', 'HCT', 'MCV', 'MCH', 'MCHC', 'RDW',
            'WBC', 'Platelets', 'Neutrophils', 'Lymphocytes'
        ]

        for col in expected_cols:
            if col not in df.columns:
                df[col] = 0

        df = df[expected_cols]

        # Encode sex
        if df['Sex'].dtype == 'object':
            df['Sex'] = df['Sex'].map({'M': 1, 'F': 0, 'm': 1, 'f': 0})
            df['Sex'] = df['Sex'].fillna(0)

        # ---------------------------
        # MODEL PREDICTIONS
        # ---------------------------
        p_abnormal = self.stage1.predict_proba(df)[0][1]
        p_def = self.stage2.predict_proba(df)[0][1]

        # ---------------------------
        # RULES (for explanation only)
        # ---------------------------
        row = self.add_indices(dict(cbc_dict))
        rule_score, rules = self.apply_rules(row)

        # ---------------------------
        # HIERARCHICAL PROBABILITY MATH
        # ---------------------------
        p_normal = 1 - p_abnormal
        p_borderline = p_abnormal * (1 - p_def)
        p_deficient = p_abnormal * p_def

        total = p_normal + p_borderline + p_deficient

        if total == 0:
            p_normal, p_borderline, p_deficient = 1, 0, 0
        else:
            p_normal /= total
            p_borderline /= total
            p_deficient /= total

        # ---------------------------
        # CLASSIFICATION (ARGMAX)
        # ---------------------------
        probs = {
            "NORMAL": p_normal,
            "BORDERLINE": p_borderline,
            "DEFICIENT": p_deficient
        }

        label = max(probs, key=probs.get)

        cls_map = {
            "NORMAL": 1,
            "BORDERLINE": 2,
            "DEFICIENT": 3
        }

        cls = cls_map[label]

        # ---------------------------
        # RESPONSE
        # ---------------------------
        return {
            "riskClass": cls,
            "label": label,

            "debug": {
                "p_abnormal_raw": float(p_abnormal),
                "p_def_raw": float(p_def),
                "input_df": df.iloc[0].to_dict()
            },

            "probabilities": {
                "normal": round(float(p_normal), 3),
                "borderline": round(float(p_borderline), 3),
                "deficient": round(float(p_deficient), 3)
            },

            "rulesFired": rules,
            "modelVersion": "B12-Clinical-Engine-v1.0",

            "indices": {
                "mentzer": round(
                    cbc_dict.get("MCV", 0) / cbc_dict.get("RBC", 1)
                    if cbc_dict.get("RBC", 0) > 0 else 0, 2
                ),
                "greenKing": round(
                    (pow(cbc_dict.get("MCV", 0), 2) * cbc_dict.get("RDW", 0)) /
                    (100 * cbc_dict.get("Hb", 1))
                    if cbc_dict.get("Hb", 0) > 0 else 0, 2
                ),
                "nlr": round(
                    (cbc_dict.get("Neutrophils") or 0) /
                    (cbc_dict.get("Lymphocytes") or 1)
                    if (cbc_dict.get("Lymphocytes") or 0) > 0 else 0, 2
                )
            }
        }

"""
ML Engine for B12 Clinical Screening.

Provides CatBoost-based two-stage classification with rule-based adjustments.
"""

import asyncio
import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

import joblib
import pandas as pd
from django.conf import settings

from apps.core.exceptions import MLModelNotReadyError

logger = logging.getLogger(__name__)


class B12ClinicalEngine:
    """
    Two-stage ML engine for B12 deficiency prediction.

    Stage 1: Normal vs Abnormal
    Stage 2: Borderline vs Deficient
    """

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.stage1 = None
        self.stage2 = None
        self.thresholds = None
        self._ready = False
        self._load_error = None
        self._model_version = "unknown"
        self._model_artifact_hash = ""
        self._validation_metrics = {}

        self._load_models()

    def _load_models(self):
        """Load ML models. Sets _ready=True on success, stores error on failure."""
        try:
            stage1_path = self.model_dir / "stage1_normal_vs_abnormal.pkl"
            stage2_path = self.model_dir / "stage2_borderline_vs_deficient.pkl"
            thresholds_path = self.model_dir / "thresholds.json"
            version_path = self.model_dir / "version.json"

            self.stage1 = joblib.load(str(stage1_path))
            self.stage2 = joblib.load(str(stage2_path))

            with open(thresholds_path, "r", encoding="utf-8") as f:
                self.thresholds = json.load(f)

            # Load version info
            if version_path.exists():
                with open(version_path, "r", encoding="utf-8") as f:
                    version_info = json.load(f)
                    self._model_version = version_info.get("version", "1.0.0")
                    self._validation_metrics = version_info.get("validation", {})

            # Compute artifact hash for reproducibility
            self._model_artifact_hash = self._compute_artifact_hash()

            self._ready = True
            logger.info(f"ML models loaded successfully (version: {self._model_version})")

        except FileNotFoundError as e:
            self._load_error = f"Model file not found: {e}"
            self._ready = False
            logger.error(f"CRITICAL: {self._load_error}")
        except Exception as e:
            self._load_error = str(e)
            self._ready = False
            logger.error(f"CRITICAL: Failed to load ML models: {e}")

    def _compute_artifact_hash(self) -> str:
        """Compute hash of model artifacts for versioning."""
        files = [
            self.model_dir / "stage1_normal_vs_abnormal.pkl",
            self.model_dir / "stage2_borderline_vs_deficient.pkl",
            self.model_dir / "thresholds.json",
        ]
        combined = ""
        for f in files:
            if f.exists():
                combined += hashlib.sha256(f.read_bytes()).hexdigest()
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    @property
    def is_ready(self) -> bool:
        """Check if the ML engine is ready for predictions."""
        return self._ready and self.stage1 is not None and self.stage2 is not None

    def get_status(self) -> dict:
        """Get ML engine status for health checks."""
        return {
            "ready": self.is_ready,
            "stage1_loaded": self.stage1 is not None,
            "stage2_loaded": self.stage2 is not None,
            "thresholds_loaded": self.thresholds is not None,
            "version": self._model_version,
            "artifact_hash": self._model_artifact_hash,
            "validation_metrics": self._validation_metrics,
            "error": self._load_error,
        }

    def add_indices(self, row: dict[str, Any]) -> dict[str, Any]:
        """Calculate clinical indices from CBC values."""
        row = dict(row)
        row["Mentzer"] = (row.get("MCV") or 0) / (row.get("RBC") or 1)
        row["RDW_MCV"] = (row.get("RDW") or 0) / (row.get("MCV") or 1)
        row["Pancytopenia"] = int(
            (row.get("Hb") or 0) < 12 and
            (row.get("WBC") or 0) < 4 and
            (row.get("Platelets") or 0) < 150
        )
        return row

    def apply_rules(self, row: dict[str, Any]) -> tuple[float, list[str]]:
        """Apply clinical rules for score adjustment.

        Rules are MCV-context-aware: B12 deficiency causes macrocytosis
        (MCV > 100) while iron deficiency causes microcytosis (MCV < 90).
        Markers like high RDW and Mentzer > 13 are only B12 risk factors
        in a macrocytic context; in microcytic context they indicate iron
        deficiency instead.
        """
        score = 0.0
        rules: list[str] = []

        mcv = row.get("MCV") or 0
        mch = row.get("MCH") or 0
        mchc = row.get("MCHC") or 0
        rdw = row.get("RDW") or 0
        hb = row.get("Hb") or 0
        platelets = row.get("Platelets") or 0

        # Iron deficiency pattern: microcytic + hypochromic = opposite of B12
        is_microcytic = 0 < mcv < 90
        is_hypochromic = (0 < mch < 27) or (0 < mchc < 32)
        iron_def_pattern = is_microcytic and is_hypochromic

        # ── Risk factors ──
        if mcv > 100:
            score += 1
            rules.append("Macrocytosis")
            if mcv > 115:
                score += 1
                rules.append("Severe macrocytosis")

        # High RDW: only a B12 risk in macrocytic context
        if rdw > 15:
            if mcv >= 95:
                score += 1
                rules.append("High RDW (macrocytic context)")
            elif not iron_def_pattern:
                score += 0.5
                rules.append("High RDW (normocytic)")
            # else: expected in iron deficiency, not a B12 signal

        # Mentzer > 13: only relevant for B12 when MCV >= 95
        if (row.get("Mentzer") or 0) > 13 and mcv >= 95:
            score += 1
            rules.append("Ineffective erythropoiesis")

        if (row.get("Pancytopenia") or 0) == 1:
            score += 2
            rules.append("Pancytopenia")

        # ── Protective factors ──
        if 0 < mcv < 100 and (row.get("Pancytopenia") or 0) == 0:
            score -= 0.5
            rules.append("No macrocytosis / no pancytopenia")
        if hb > 11 and platelets > 150:
            score -= 0.5
            rules.append("Preserved cell counts")
        if 0 < mcv < 96 and rdw < 14 and hb > 12:
            score -= 1
            rules.append("Normal marrow pattern")

        # Iron deficiency pattern: strong protective against B12 risk
        if iron_def_pattern:
            score -= 3
            rules.append("Iron deficiency pattern (microcytic/hypochromic)")

        return score, rules

    def compute_shap_values(self, cbc_dict: dict[str, Any]) -> dict[str, float]:
        """
        Compute SHAP values for the given CBC input against the stage1 model.

        Returns a dict mapping feature names to their SHAP values for the
        "abnormal" class (class index 1). Uses TreeExplainer for CatBoost
        models (fast, exact for tree models).
        """
        if not self.is_ready:
            return {}

        try:
            import shap

            df = pd.DataFrame([cbc_dict])
            expected_cols = [
                "Age", "Sex", "Hb", "RBC", "HCT", "MCV", "MCH", "MCHC",
                "RDW", "WBC", "Platelets", "Neutrophils", "Lymphocytes",
            ]
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = 0
            df = df[expected_cols]

            if df["Sex"].dtype == "object":
                df["Sex"] = df["Sex"].map({"M": 1, "F": 0, "m": 1, "f": 0}).fillna(0)

            if not hasattr(self, '_shap_explainer') or self._shap_explainer is None:
                self._shap_explainer = shap.TreeExplainer(self.stage1)
            explainer = self._shap_explainer
            shap_values = explainer.shap_values(df)

            # shap_values is a list of arrays (one per class) for classification
            # We want the "abnormal" class (index 1)
            if isinstance(shap_values, list):
                values = shap_values[1][0]  # class 1, first (only) sample
            else:
                values = shap_values[0]  # single output

            return {
                col: round(float(val), 6)
                for col, val in zip(expected_cols, values)
            }
        except Exception as e:
            logger.warning("SHAP computation failed: %s", e)
            return {}

    def predict(self, cbc_dict: dict[str, Any], include_shap: bool = False) -> dict[str, Any]:
        """
        Perform B12 deficiency prediction.

        Args:
            cbc_dict: CBC values with Age, Sex, Hb, RBC, HCT, MCV, MCH, MCHC, RDW, WBC, Platelets, Neutrophils, Lymphocytes
            include_shap: If True, compute and include SHAP feature attributions.
                          Defaults to False to avoid latency on bulk imports and
                          routine predictions. Set to True for explain/ endpoints.

        Returns:
            dict with riskClass, labelText, probabilities, rulesFired, indices

        Raises:
            MLModelNotReadyError: If models are not loaded
        """
        # CRITICAL: Fail closed if models are not ready
        if not self.is_ready:
            raise MLModelNotReadyError(
                f"ML models not ready for prediction. Status: {self.get_status()}"
            )

        df = pd.DataFrame([cbc_dict])

        expected_cols = [
            "Age", "Sex", "Hb", "RBC", "HCT", "MCV", "MCH", "MCHC",
            "RDW", "WBC", "Platelets", "Neutrophils", "Lymphocytes",
        ]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = 0
        df = df[expected_cols]

        if df["Sex"].dtype == "object":
            df["Sex"] = df["Sex"].map({"M": 1, "F": 0, "m": 1, "f": 0}).fillna(0)

        # Two-stage prediction
        p_abnormal = float(self.stage1.predict_proba(df)[0][1])
        p_def = float(self.stage2.predict_proba(df)[0][1]) if p_abnormal > 0.3 else 0.05

        # Apply clinical rules
        row = self.add_indices(cbc_dict)
        rule_score, rules = self.apply_rules(row)

        rule_weight = float(self.thresholds.get("rule_weight", 0.0))
        p_def_final = min(1, max(0, p_def + rule_weight * float(rule_score)))

        # Microcytic pattern override: iron deficiency (microcytic +
        # hypochromic) is the opposite of B12 deficiency.  Cap the B12
        # deficiency probability because the CatBoost model cannot
        # distinguish iron-deficient from B12-deficient CBC patterns.
        mcv_val = cbc_dict.get("MCV") or 0
        mch_val = cbc_dict.get("MCH") or 0
        mchc_val = cbc_dict.get("MCHC") or 0
        if 0 < mcv_val < 90 and ((0 < mch_val < 27) or (0 < mchc_val < 32)):
            if mcv_val < 80 and 0 < mch_val < 27 and 0 < mchc_val < 32:
                # Strong microcytic: textbook iron deficiency
                p_def_final = min(p_def_final, 0.15)
            else:
                # Moderate microcytic with hypochromia
                p_def_final = min(p_def_final, 0.30)

        # Three-class probabilities
        p_normal = 1 - max(p_abnormal, p_def_final)
        p_borderline = max(0, p_abnormal - p_def_final)
        p_deficient = p_def_final

        # Classification: highest probability wins, cross-validated by indices
        probs = {"normal": p_normal, "borderline": p_borderline, "deficient": p_deficient}
        winner = max(probs, key=probs.get)

        # Extract index signals for cross-validation
        mcv = row.get("MCV") or 0
        rdw = row.get("RDW") or 0
        hb = row.get("Hb") or 0
        rbc = row.get("RBC") or 0
        mentzer = mcv / rbc if rbc > 0 else 0
        has_macrocytosis = mcv > 100
        has_severe_macrocytosis = mcv > 115
        has_high_rdw = rdw > 15
        has_pancytopenia = row.get("Pancytopenia", 0) == 1
        has_high_mentzer = mentzer > 13
        has_normal_marrow = mcv < 96 and rdw < 14 and hb > 12
        has_iron_def_pattern = (
            0 < mcv < 90
            and ((0 < (row.get("MCH") or 0) < 27) or (0 < (row.get("MCHC") or 0) < 32))
        )
        # Iron deficiency indices (high RDW/Mentzer) are explained by iron
        # deficiency, not B12 — treat them as "clean" for B12 purposes.
        all_indices_clean = (
            not has_macrocytosis
            and not has_high_rdw
            and not has_pancytopenia
            and not has_high_mentzer
        ) or has_iron_def_pattern

        if winner == "deficient":
            cls = 3
            label_text = "DEFICIENT"
            # Downgrade: no B12-relevant markers support deficiency
            if all_indices_clean:
                cls = 2
                label_text = "BORDERLINE"
            # Downgrade: iron deficiency pattern contradicts B12
            elif has_iron_def_pattern and not has_macrocytosis:
                cls = 2
                label_text = "BORDERLINE"

        elif winner == "borderline":
            cls = 2
            label_text = "BORDERLINE"
            # Upgrade: severe markers point to deficiency
            if (has_macrocytosis and has_pancytopenia) \
               or has_severe_macrocytosis \
               or (has_macrocytosis and has_high_rdw and has_high_mentzer):
                cls = 3
                label_text = "DEFICIENT"
            # Downgrade: all indices clean with normal marrow
            elif all_indices_clean and has_normal_marrow:
                cls = 1
                label_text = "NORMAL"

        else:  # normal
            cls = 1
            label_text = "NORMAL"
            # Upgrade: risk markers contradict normal classification
            # Iron deficiency pattern explains high RDW/Mentzer — not a B12 signal
            if not has_iron_def_pattern and (
                has_macrocytosis or has_pancytopenia
                or (has_high_rdw and has_high_mentzer)
            ):
                cls = 2
                label_text = "BORDERLINE"

        # Compute SHAP values only when explicitly requested (opt-in).
        # Skipped by default to avoid latency on bulk imports and routine predictions.
        shap_values = self.compute_shap_values(cbc_dict) if include_shap else {}

        return {
            "riskClass": cls,
            "labelText": label_text,
            "probabilities": {
                "normal": round(p_normal, 3),
                "borderline": round(p_borderline, 3),
                "deficient": round(p_deficient, 3),
            },
            "rulesFired": rules,
            "modelVersion": self._model_version,
            "modelArtifactHash": self._model_artifact_hash,
            "indices": {
                "mentzer": round(
                    (cbc_dict.get("MCV", 0) / cbc_dict.get("RBC", 1))
                    if (cbc_dict.get("RBC", 0) or 0) > 0 else 0,
                    2,
                ),
                "greenKing": round(
                    (
                        ((pow(cbc_dict.get("MCV", 0), 2) * cbc_dict.get("RDW", 0)) / (100 * cbc_dict.get("Hb", 1)))
                        if (cbc_dict.get("Hb", 0) or 0) > 0
                        else 0
                    ),
                    2,
                ),
                "nlr": round(
                    (
                        ((cbc_dict.get("Neutrophils") or 0) / (cbc_dict.get("Lymphocytes") or 1))
                        if (cbc_dict.get("Lymphocytes") or 0) > 0
                        else 0
                    ),
                    2,
                ),
                "pancytopenia": int(
                    (cbc_dict.get("Hb", 0) or 0) < 12
                    and (cbc_dict.get("WBC", 0) or 0) < 4
                    and (cbc_dict.get("Platelets", 0) or 0) < 150
                ),
                "shap_values": shap_values,
            },
        }


# Singleton instance
_engine: Optional[B12ClinicalEngine] = None
_executor: Optional[ThreadPoolExecutor] = None
_engine_lock = threading.Lock()
_executor_lock = threading.Lock()


def get_ml_engine() -> B12ClinicalEngine:
    """Get or initialize the ML engine singleton (thread-safe)."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                model_dir = settings.ML_MODEL_DIR
                _engine = B12ClinicalEngine(model_dir)
    return _engine


def get_ml_executor() -> ThreadPoolExecutor:
    """Get or initialize the thread pool executor for ML inference (thread-safe)."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=settings.ML_EXECUTOR_WORKERS,
                    thread_name_prefix="ml_worker"
                )
    return _executor


async def predict_async(cbc_dict: dict[str, Any], include_shap: bool = False) -> dict[str, Any]:
    """
    Async wrapper for ML prediction.

    Runs prediction in thread pool to avoid blocking event loop.
    """
    import functools
    engine = get_ml_engine()
    executor = get_ml_executor()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,
        functools.partial(engine.predict, cbc_dict, include_shap=include_shap),
    )


def shutdown_ml_executor():
    """Shutdown the ML thread pool executor."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None

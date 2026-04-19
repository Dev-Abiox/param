"""
ML Engine for B12 Clinical Screening.

Provides CatBoost-based two-stage classification with rule-based adjustments.
"""

import asyncio
import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

import joblib
import pandas as pd
from django.conf import settings

from apps.core.exceptions import MLModelNotReadyError

logger = logging.getLogger(__name__)

# How often (seconds) to check for updated model files on disk.
_RELOAD_CHECK_INTERVAL = int(getattr(settings, 'ML_RELOAD_CHECK_INTERVAL', 30))


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
        self._lock = threading.Lock()
        self._last_reload_check = 0.0

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

    def maybe_reload(self) -> bool:
        """
        Check if model files have changed on disk and reload if needed.

        Called before each prediction (throttled to once every
        _RELOAD_CHECK_INTERVAL seconds).  The reload is atomic — the old
        models remain active until the new ones are fully loaded.

        Returns True if models were reloaded.
        """
        # Guard against instances created via __new__ without __init__
        if not hasattr(self, '_last_reload_check'):
            return False

        now = time.time()
        if now - self._last_reload_check < _RELOAD_CHECK_INTERVAL:
            return False
        self._last_reload_check = now

        try:
            current_hash = self._compute_artifact_hash()
        except Exception:
            return False

        if current_hash == self._model_artifact_hash:
            return False

        logger.info(
            "ML model file change detected (hash %s → %s), reloading...",
            self._model_artifact_hash[:8], current_hash[:8],
        )

        with self._lock:
            # Double-check after acquiring the lock
            if self._compute_artifact_hash() == self._model_artifact_hash:
                return False

            old_stage1, old_stage2, old_thresholds = self.stage1, self.stage2, self.thresholds
            try:
                self._load_models()
                logger.info(
                    "ML models reloaded successfully (version: %s, hash: %s)",
                    self._model_version, self._model_artifact_hash[:8],
                )
                return True
            except Exception as e:
                # Rollback — keep the old models running
                self.stage1, self.stage2, self.thresholds = old_stage1, old_stage2, old_thresholds
                self._ready = old_stage1 is not None
                logger.error("ML model reload failed, keeping previous models: %s", e)
                return False

    def get_status(self) -> dict:
        """Get ML engine status for health checks."""
        return {
            "ready": self.is_ready,
            "stage1_loaded": self.stage1 is not None,
            "stage2_loaded": self.stage2 is not None,
            "thresholds_loaded": self.thresholds is not None,
            "version": self._model_version,
            "artifact_hash": self._model_artifact_hash,
            "error": self._load_error,
            "hot_reload": {
                "enabled": True,
                "check_interval_seconds": _RELOAD_CHECK_INTERVAL,
                "last_check": getattr(self, '_last_reload_check', 0),
            },
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

    def compute_shap_values(self, df: pd.DataFrame) -> dict[str, float] | None:
        """
        Compute SHAP feature importance values for the Stage 1 model prediction.

        Uses CatBoost's native get_feature_importance(type='ShapValues') which
        is fast and doesn't require the shap library at runtime.

        Returns a dict of {feature_name: shap_value} or None if computation fails.
        """
        try:
            from catboost import Pool
            # stage1 is typically a CalibratedClassifierCV wrapping CatBoost —
            # unwrap to the underlying fitted CatBoost before calling
            # get_feature_importance (which exists only on CatBoost estimators).
            base = self._unwrap_catboost(self.stage1)
            if base is None:
                logger.warning(
                    "SHAP skipped: could not locate underlying CatBoost estimator"
                )
                return None
            pool = Pool(df)
            # CatBoost shap: last column is the base value, drop it
            shap_matrix = base.get_feature_importance(
                data=pool,
                type='ShapValues',
            )
            shap_row = shap_matrix[0][:-1]  # exclude base value
            feature_names = df.columns.tolist()
            return {
                name: round(float(val), 4)
                for name, val in zip(feature_names, shap_row)
            }
        except Exception as e:
            logger.warning("SHAP computation failed (non-fatal): %s", e)
            return None

    @staticmethod
    def _unwrap_catboost(model):
        """Return the underlying CatBoost estimator from a possibly-wrapped model."""
        if hasattr(model, "get_feature_importance"):
            return model
        calibrated = getattr(model, "calibrated_classifiers_", None)
        if calibrated:
            inner = calibrated[0]
            # sklearn >=1.2 uses `.estimator`; older uses `.base_estimator`.
            base = getattr(inner, "estimator", None) or getattr(inner, "base_estimator", None)
            if base is not None and hasattr(base, "get_feature_importance"):
                return base
        return None

    def apply_rules(self, row: dict[str, Any]) -> tuple[float, list[str]]:
        """Apply clinical rules for score adjustment."""
        score = 0.0
        rules: list[str] = []

        # Risk factors
        if (row.get("MCV") or 0) > 100:
            score += 1
            rules.append("Macrocytosis")
        if (row.get("RDW") or 0) > 15:
            score += 1
            rules.append("High RDW")
        if (row.get("Mentzer") or 0) > 13:
            score += 1
            rules.append("Ineffective erythropoiesis")
        if (row.get("Pancytopenia") or 0) == 1:
            score += 2
            rules.append("Pancytopenia")

        # Protective factors
        if (row.get("MCV") or 0) < 100 and (row.get("Pancytopenia") or 0) == 0:
            score -= 0.5
            rules.append("No macrocytosis / no pancytopenia")
        if (row.get("Hb") or 0) > 11 and (row.get("Platelets") or 0) > 150:
            score -= 0.5
            rules.append("Preserved cell counts")
        if (row.get("MCV") or 0) < 96 and (row.get("RDW") or 0) < 14 and (row.get("Hb") or 0) > 12:
            score -= 1
            rules.append("Normal marrow pattern")

        return score, rules

    def _build_indices(self, cbc_dict: dict[str, Any], df: pd.DataFrame) -> dict[str, Any]:
        """Build the indices dict including clinical indices and SHAP values."""
        indices: dict[str, Any] = {
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
        }

        # Compute SHAP feature importances (best-effort, non-blocking)
        shap_values = self.compute_shap_values(df)
        if shap_values:
            indices["shap_values"] = shap_values

        return indices

    def predict(self, cbc_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Perform B12 deficiency prediction.

        Args:
            cbc_dict: CBC values with Age, Sex, Hb, RBC, HCT, MCV, MCH, MCHC, RDW, WBC, Platelets, Neutrophils, Lymphocytes

        Returns:
            dict with riskClass, labelText, probabilities, rulesFired, indices

        Raises:
            MLModelNotReadyError: If models are not loaded
        """
        # Check for updated model files (throttled, non-blocking)
        self.maybe_reload()

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

        # Derive three-class probabilities
        p_normal = max(0, 1 - p_abnormal)
        p_borderline = max(0, p_abnormal - p_def_final)
        p_deficient = p_def_final

        # Apply rule adjustment to shift probability mass toward/away from deficient
        adjustment = rule_weight * float(rule_score)
        p_deficient = min(1, max(0, p_deficient + adjustment))

        # Re-normalise so probabilities sum to 1
        total = p_normal + p_borderline + p_deficient
        if total > 0:
            p_normal /= total
            p_borderline /= total
            p_deficient /= total

        # Classification: highest probability wins
        if p_deficient >= p_borderline and p_deficient >= p_normal:
            cls = 3
            label_text = "DEFICIENT"
        elif p_borderline >= p_normal:
            cls = 2
            label_text = "BORDERLINE"
        else:
            cls = 1
            label_text = "NORMAL"

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
            "indices": self._build_indices(cbc_dict, df),
        }


# Singleton instance
_engine: Optional[B12ClinicalEngine] = None
_engine_lock = threading.Lock()
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def get_ml_engine() -> B12ClinicalEngine:
    """Get or initialize the ML engine singleton (double-checked locking)."""
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            model_dir = settings.ML_MODEL_DIR
            _engine = B12ClinicalEngine(model_dir)
    return _engine


def get_ml_executor() -> ThreadPoolExecutor:
    """Get or initialize the thread pool executor for ML inference."""
    global _executor
    if _executor is not None:
        return _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.ML_EXECUTOR_WORKERS,
                thread_name_prefix="ml_worker"
            )
    return _executor


async def predict_async(cbc_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Async wrapper for ML prediction.

    Runs prediction in thread pool to avoid blocking event loop.
    """
    engine = get_ml_engine()
    executor = get_ml_executor()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, engine.predict, cbc_dict)


def shutdown_ml_executor():
    """Shutdown the ML thread pool executor."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None

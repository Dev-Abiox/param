"""
ML Engine for B12 Clinical Screening.

Provides CatBoost-based two-stage classification with rule-based adjustments.
"""

import asyncio
import hashlib
import json
import logging
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

        # Classification
        deficient_threshold = float(self.thresholds.get("deficient_threshold", 0.7))
        borderline_threshold = float(self.thresholds.get("borderline_threshold", 0.4))

        if p_def_final >= deficient_threshold:
            cls = 3
            label_text = "DEFICIENT"
        elif p_def_final >= borderline_threshold:
            cls = 2
            label_text = "BORDERLINE"
        else:
            cls = 1
            label_text = "NORMAL"

        return {
            "riskClass": cls,
            "labelText": label_text,
            "probabilities": {
                "normal": round(1 - max(p_abnormal, p_def_final), 3),
                "borderline": round(max(0, p_abnormal - p_def_final), 3),
                "deficient": round(p_def_final, 3),
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
            },
        }


# Singleton instance
_engine: Optional[B12ClinicalEngine] = None
_executor: Optional[ThreadPoolExecutor] = None


def get_ml_engine() -> B12ClinicalEngine:
    """Get or initialize the ML engine singleton."""
    global _engine
    if _engine is None:
        model_dir = settings.ML_MODEL_DIR
        _engine = B12ClinicalEngine(model_dir)
    return _engine


def get_ml_executor() -> ThreadPoolExecutor:
    """Get or initialize the thread pool executor for ML inference."""
    global _executor
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

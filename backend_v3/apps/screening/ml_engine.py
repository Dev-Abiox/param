"""
B12 Clinical Engine v2.0.0
Two-Stage Architecture: Binary Deficient Detector + Borderline Refinement

Architecture:
  Stage 1: HistGradientBoosting (Deficient vs Not-Deficient)
           - Trained on clear cases only (B12 <200 vs >=300)
           - Class-weighted for balance
           - 10 features, AUC ~0.878

  Stage 2: HistGradientBoosting (Borderline vs Normal)
           - Fires ONLY in Stage 1's uncertain zone
           - Uses 17 features (base + indices + p_stage1)
           - AUC ~0.61 in uncertain zone

  Classification:
           - p_stage1 > T_DEF -> Deficient (class 3)
           - p_stage1 < T_NORM and (not in zone OR p_stage2 < T_S2) -> Normal (class 1)
           - Everything else -> Borderline (class 2)
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
import numpy as np
from django.conf import settings

from apps.core.exceptions import MLModelNotReadyError

logger = logging.getLogger(__name__)

VALID_RANGES = {
    "Hb":          (1.0, 25.0),
    "RBC":         (0.5, 10.0),
    "HCT":         (5.0, 75.0),
    "MCV":         (30.0, 160.0),
    "MCH":         (10.0, 60.0),
    "MCHC":        (20.0, 45.0),
    "RDW":         (5.0, 40.0),
    "WBC":         (0.1, 100.0),
    "Platelets":   (1.0, 2000.0),
    "Neutrophils": (0.0, 100.0),
    "Lymphocytes": (0.0, 100.0),
    "Age":         (0, 120),
}

LABEL_MAP = {1: "NORMAL", 2: "BORDERLINE", 3: "DEFICIENT"}
LABEL_DESCRIPTION_MAP = {
    1: "Low Risk / Likely Normal",
    2: "Intermediate Risk / Possible Early Deficiency",
    3: "High Risk / Likely Deficient",
}


class B12ClinicalEngine:
    """
    Two-stage B12 deficiency screening engine (v2).

    Stage 1: Binary deficiency probability (HistGradientBoosting)
    Stage 2: Borderline refinement in uncertain zone (HistGradientBoosting)
    """

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self.stage1 = None
        self.stage2 = None
        self.config = None
        self._ready = False
        self._load_error = None
        self._model_version = "unknown"
        self._model_artifact_hash = ""

        self._load_models()

    def _load_models(self):
        """Load ML models. Sets _ready=True on success, stores error on failure."""
        try:
            stage1_path = self.model_dir / "stage1_binary.pkl"
            stage2_path = self.model_dir / "stage2_borderline.pkl"
            config_path = self.model_dir / "model_config.json"

            self.stage1 = joblib.load(str(stage1_path))
            self.stage2 = joblib.load(str(stage2_path))

            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)

            self.zone_lo, self.zone_hi = self.config["zone"]
            self.t_def = self.config["thresholds"]["deficient"]
            self.t_norm = self.config["thresholds"]["normal"]
            self.t_s2 = self.config["thresholds"]["s2_border"]

            self._model_version = self.config.get("version", "2.0.0")
            self._model_artifact_hash = self._compute_artifact_hash()

            self._ready = True
            logger.info(
                "B12ClinicalEngine v%s loaded. Stage1 AUC=%s, Zone=[%s, %s]",
                self._model_version,
                self.config.get("stage1_auc"),
                self.zone_lo,
                self.zone_hi,
            )

        except FileNotFoundError as e:
            self._load_error = f"Model file not found: {e}"
            self._ready = False
            logger.error("CRITICAL: %s", self._load_error)
        except Exception as e:
            self._load_error = str(e)
            self._ready = False
            logger.error("CRITICAL: Failed to load ML models: %s", e)

    def _compute_artifact_hash(self) -> str:
        """Compute hash of model artifacts for versioning."""
        files = [
            self.model_dir / "stage1_binary.pkl",
            self.model_dir / "stage2_borderline.pkl",
            self.model_dir / "model_config.json",
        ]
        combined = ""
        for f in files:
            if f.exists():
                combined += hashlib.sha256(f.read_bytes()).hexdigest()
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    @property
    def is_ready(self) -> bool:
        return self._ready and self.stage1 is not None and self.stage2 is not None

    def get_status(self) -> dict:
        return {
            "ready": self.is_ready,
            "stage1_loaded": self.stage1 is not None,
            "stage2_loaded": self.stage2 is not None,
            "config_loaded": self.config is not None,
            "version": self._model_version,
            "artifact_hash": self._model_artifact_hash,
            "error": self._load_error,
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate(self, cbc: dict) -> dict:
        """Validate CBC input. Returns data_quality dict."""
        warnings_list = []

        for key in ["Platelets", "WBC", "Hb", "RBC", "HCT"]:
            val = cbc.get(key)
            if val is not None and val < 0:
                warnings_list.append(
                    f"Physically impossible value: {key}={val}"
                )

        for key, (lo, hi) in VALID_RANGES.items():
            val = cbc.get(key)
            if val is not None and (val < lo or val > hi):
                warnings_list.append(
                    f"{key}={val} outside expected range [{lo}, {hi}]"
                )

        hb = cbc.get("Hb")
        hct = cbc.get("HCT")
        mchc = cbc.get("MCHC")
        if hb and hct and mchc and hct > 0:
            mchc_calc = (hb / hct) * 100
            if abs(mchc - mchc_calc) > 5.0:
                warnings_list.append(
                    f"MCHC inconsistency: reported={mchc:.1f}, "
                    f"calculated={mchc_calc:.1f}"
                )

        neut = cbc.get("Neutrophils", 0)
        lymph = cbc.get("Lymphocytes", 0)
        diff_sum = neut + lymph
        if diff_sum > 0 and (diff_sum < 30 or diff_sum > 110):
            warnings_list.append(
                f"WBC differential partial sum {diff_sum:.1f}% looks unusual"
            )

        return {
            "valid": len(warnings_list) == 0,
            "warnings": warnings_list,
        }

    # ------------------------------------------------------------------
    # Feature computation
    # ------------------------------------------------------------------
    def _compute_indices(self, cbc: dict) -> dict:
        """Compute clinical hematological indices."""
        mcv = cbc.get("MCV", 0)
        rbc = cbc.get("RBC", 0)
        rdw = cbc.get("RDW", 0)
        hb = cbc.get("Hb", 0)
        neut = cbc.get("Neutrophils", 50.0)
        lymph = cbc.get("Lymphocytes", 30.0)

        mentzer = mcv / rbc if rbc > 0 else 0
        green_king = (mcv ** 2 * rdw) / (100 * hb) if hb > 0 else 0
        nlr = neut / lymph if lymph > 0 else 0

        return {
            "mentzer": round(mentzer, 2),
            "green_king": round(green_king, 2),
            "nlr": round(nlr, 2),
        }

    def _build_stage1_vector(self, cbc: dict) -> np.ndarray:
        return np.array([[
            cbc["Hb"], cbc["RBC"], cbc["HCT"], cbc["MCV"], cbc["MCH"],
            cbc["MCHC"], cbc["RDW"], cbc["WBC"], cbc["Platelets"], cbc["Age"],
        ]])

    def _build_stage2_vector(self, cbc: dict, indices: dict, p_stage1: float) -> np.ndarray:
        sex_enc = 1 if str(cbc.get("Sex", "")).upper() in ("M", "MALE") else 0
        return np.array([[
            cbc["Hb"], cbc["RBC"], cbc["HCT"], cbc["MCV"], cbc["MCH"],
            cbc["MCHC"], cbc["RDW"], cbc["WBC"], cbc["Platelets"], cbc["Age"],
            sex_enc,
            cbc.get("Neutrophils", 50.0),
            cbc.get("Lymphocytes", 30.0),
            indices["mentzer"],
            indices["green_king"],
            indices["nlr"],
            p_stage1,
        ]])

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------
    def predict(self, cbc_dict: dict[str, Any], include_shap: bool = False) -> dict[str, Any]:
        """
        Perform B12 deficiency prediction.

        Args:
            cbc_dict: CBC values with Age, Sex, Hb, RBC, HCT, MCV, MCH, MCHC,
                      RDW, WBC, Platelets, Neutrophils, Lymphocytes
            include_shap: Ignored in v2 (SHAP not supported for HistGradientBoosting).
                          Kept for API compatibility.

        Returns:
            dict with v1-compat keys (riskClass, labelText, probabilities,
            rulesFired, modelVersion, modelArtifactHash, indices) plus
            v2 fields (p_stage1, p_stage2, in_uncertain_zone, confidence,
            clinical_indices, data_quality, labelDescription).

        Raises:
            MLModelNotReadyError: If models are not loaded
        """
        if not self.is_ready:
            raise MLModelNotReadyError(
                f"ML models not ready for prediction. Status: {self.get_status()}"
            )

        # Validate
        data_quality = self._validate(cbc_dict)

        # Compute indices
        clinical_indices = self._compute_indices(cbc_dict)

        # Stage 1: Binary deficiency probability
        X1 = self._build_stage1_vector(cbc_dict)
        p_stage1 = float(self.stage1.predict_proba(X1)[0][1])

        # Stage 2: Borderline detection (only in uncertain zone)
        in_zone = self.zone_lo <= p_stage1 <= self.zone_hi
        p_stage2 = None

        if in_zone:
            X2 = self._build_stage2_vector(cbc_dict, clinical_indices, p_stage1)
            p_stage2 = float(self.stage2.predict_proba(X2)[0][1])

        # Classification
        if p_stage1 > self.t_def:
            prediction = 3
        elif p_stage1 < self.t_norm:
            if in_zone and p_stage2 is not None and p_stage2 >= self.t_s2:
                prediction = 2
            else:
                prediction = 1
        else:
            prediction = 2

        # Derive display probabilities
        if prediction == 3:
            p_deficient = p_stage1
            p_borderline = (1 - p_stage1) * 0.6
            p_normal = (1 - p_stage1) * 0.4
        elif prediction == 1:
            p_normal = 1 - p_stage1
            p_deficient = p_stage1 * 0.3
            p_borderline = p_stage1 * 0.7
        else:
            if p_stage2 is not None:
                p_borderline = 0.3 + 0.3 * p_stage2
                p_deficient = p_stage1
                p_normal = max(0, 1 - p_deficient - p_borderline)
            else:
                p_borderline = 0.4
                p_deficient = p_stage1
                p_normal = max(0, 1 - p_deficient - p_borderline)

        # Normalize
        total = p_deficient + p_borderline + p_normal
        if total > 0:
            p_deficient /= total
            p_borderline /= total
            p_normal /= total

        # Confidence
        if p_stage1 > 0.75 or p_stage1 < 0.10:
            confidence = "high"
        elif p_stage1 > 0.55 or p_stage1 < 0.20:
            confidence = "moderate"
        else:
            confidence = "low"

        # Pancytopenia flag (for backward-compat indices dict)
        pancytopenia = int(
            (cbc_dict.get("Hb", 0) or 0) < 12
            and (cbc_dict.get("WBC", 0) or 0) < 4
            and (cbc_dict.get("Platelets", 0) or 0) < 150
        )

        return {
            # ── v1-compat keys (unchanged shape) ──
            "riskClass": prediction,
            "labelText": LABEL_MAP[prediction],
            "probabilities": {
                "normal": round(p_normal, 3),
                "borderline": round(p_borderline, 3),
                "deficient": round(p_deficient, 3),
            },
            "rulesFired": [],
            "modelVersion": self._model_version,
            "modelArtifactHash": self._model_artifact_hash,
            "indices": {
                "mentzer": clinical_indices["mentzer"],
                "greenKing": clinical_indices["green_king"],
                "nlr": clinical_indices["nlr"],
                "pancytopenia": pancytopenia,
                "shap_values": {},
            },
            # ── v2 new fields ──
            "labelDescription": LABEL_DESCRIPTION_MAP[prediction],
            "p_stage1": round(p_stage1, 4),
            "p_stage2": round(p_stage2, 4) if p_stage2 is not None else None,
            "in_uncertain_zone": in_zone,
            "confidence": confidence,
            "clinical_indices": clinical_indices,
            "data_quality": data_quality,
        }


# ── Singleton & async infrastructure (unchanged from v1) ──

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

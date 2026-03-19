"""
Tests for the ML engine (B12 screening classification) v1.
"""

import pytest
from unittest.mock import MagicMock, patch

import numpy as np


def _make_mock_engine():
    """Create a v1 engine with mocked CatBoost models and thresholds."""
    from apps.screening.ml_engine import B12ClinicalEngine

    engine = B12ClinicalEngine.__new__(B12ClinicalEngine)
    engine._ready = True
    engine._load_error = None
    engine._model_version = "1.0.0"
    engine._model_artifact_hash = "test_hash"
    engine.model_dir = MagicMock()
    engine.thresholds = {
        "rule_weight": 0.05,
        "deficient_threshold": 0.7,
        "borderline_threshold": 0.4,
    }

    mock_stage1 = MagicMock()
    mock_stage1.predict_proba.return_value = np.array([[0.8, 0.2]])
    mock_stage2 = MagicMock()
    mock_stage2.predict_proba.return_value = np.array([[0.6, 0.4]])

    engine.stage1 = mock_stage1
    engine.stage2 = mock_stage2

    return engine


class TestMLEngineConfig:
    """Tests for ML engine configuration and initialization."""

    def test_ml_engine_import(self):
        """Test that ML engine can be imported."""
        from apps.screening.ml_engine import B12ClinicalEngine

        assert B12ClinicalEngine is not None

    def test_engine_not_ready_without_models(self):
        """Test engine reports not ready without loaded models."""
        from pathlib import Path
        from apps.screening.ml_engine import B12ClinicalEngine

        engine = B12ClinicalEngine(Path("../../backend_v3/ml/models"))
        assert engine.is_ready is False

    def test_engine_has_model_not_ready_error(self):
        """Test MLModelNotReadyError is available."""
        from apps.screening.ml_engine import MLModelNotReadyError

        error = MLModelNotReadyError("Test error")
        assert str(error) == "Test error"


class TestMLEnginePrediction:
    """Tests for ML prediction functionality."""

    @pytest.fixture
    def mock_engine(self):
        return _make_mock_engine()

    def test_predict_normal_sample(self, mock_engine, sample_cbc_data):
        """Test prediction returns valid result for healthy CBC values."""
        mock_engine.stage1.predict_proba.return_value = np.array([[0.85, 0.15]])

        result = mock_engine.predict(sample_cbc_data)

        assert result is not None
        assert "riskClass" in result
        assert result["riskClass"] in [1, 2, 3]

    def test_predict_deficient_sample(self, mock_engine, sample_cbc_deficient):
        """Test prediction returns Deficient for abnormal CBC values."""
        mock_engine.stage1.predict_proba.return_value = np.array([[0.1, 0.9]])
        mock_engine.stage2.predict_proba.return_value = np.array([[0.1, 0.9]])

        result = mock_engine.predict(sample_cbc_deficient)

        assert result is not None
        assert result["riskClass"] == 3  # Deficient

    def test_predict_returns_expected_keys(self, mock_engine, sample_cbc_data):
        """Test prediction returns all expected keys."""
        result = mock_engine.predict(sample_cbc_data)

        assert "riskClass" in result
        assert "labelText" in result
        assert "probabilities" in result
        assert "rulesFired" in result
        assert "modelVersion" in result
        assert "modelArtifactHash" in result
        assert "indices" in result

    def test_predict_indices_keys(self, mock_engine, sample_cbc_data):
        """Test prediction indices contain expected clinical indices."""
        result = mock_engine.predict(sample_cbc_data)

        assert "mentzer" in result["indices"]
        assert "greenKing" in result["indices"]
        assert "nlr" in result["indices"]
        assert "pancytopenia" in result["indices"]

    def test_predict_rules_fired_is_list(self, mock_engine, sample_cbc_data):
        """rulesFired should be a list of strings."""
        result = mock_engine.predict(sample_cbc_data)
        assert isinstance(result["rulesFired"], list)

    def test_predict_stage2_skipped_when_p_abnormal_low(self, mock_engine, sample_cbc_data):
        """When p_abnormal <= 0.3, stage2 is skipped and p_def defaults to 0.05."""
        mock_engine.stage1.predict_proba.return_value = np.array([[0.85, 0.15]])

        result = mock_engine.predict(sample_cbc_data)

        mock_engine.stage2.predict_proba.assert_not_called()
        assert result["riskClass"] == 1  # NORMAL

    def test_predict_stage2_runs_when_p_abnormal_high(self, mock_engine, sample_cbc_data):
        """When p_abnormal > 0.3, stage2 should run."""
        mock_engine.stage1.predict_proba.return_value = np.array([[0.3, 0.7]])

        result = mock_engine.predict(sample_cbc_data)

        mock_engine.stage2.predict_proba.assert_called_once()

    def test_predict_not_ready_raises_error(self, sample_cbc_data):
        """Test prediction raises error when engine not ready."""
        from apps.screening.ml_engine import B12ClinicalEngine, MLModelNotReadyError

        engine = B12ClinicalEngine.__new__(B12ClinicalEngine)
        engine._ready = False
        engine._load_error = "Models not found"
        engine.stage1 = None
        engine.stage2 = None
        engine._model_version = "unknown"
        engine._model_artifact_hash = ""
        engine.thresholds = None

        with pytest.raises(MLModelNotReadyError):
            engine.predict(sample_cbc_data)


class TestMLEngineValidation:
    """Tests for CBC data validation — engine handles missing/bad data gracefully."""

    @pytest.fixture
    def mock_engine(self):
        return _make_mock_engine()

    def test_predict_with_missing_fields(self, mock_engine):
        """Engine should handle prediction even with sparse input."""
        sparse_cbc = {'Hb': 12.0, 'MCV': 85.0, 'MCH': 30.0, 'MCHC': 34.0,
                       'RBC': 4.5, 'HCT': 40.0, 'RDW': 13.0, 'WBC': 7.0,
                       'Platelets': 250.0, 'Sex': 'M', 'Age': 40}
        result = mock_engine.predict(sparse_cbc)
        assert 'riskClass' in result
        assert 'labelText' in result

    def test_predict_with_zero_rbc_no_crash(self, mock_engine):
        """Engine should handle zero RBC (division guard) without crashing."""
        cbc = {'Hb': 0, 'MCV': 0, 'MCH': 0, 'MCHC': 0, 'RBC': 0, 'HCT': 0,
               'RDW': 0, 'WBC': 0, 'Platelets': 0, 'Sex': 'M', 'Age': 0,
               'Neutrophils': 0, 'Lymphocytes': 0}
        result = mock_engine.predict(cbc)
        assert 'riskClass' in result

    def test_clinical_rules_macrocytosis(self, mock_engine):
        """MCV > 100 should trigger Macrocytosis rule."""
        cbc = {'Hb': 10.0, 'MCV': 110.0, 'MCH': 30.0, 'MCHC': 34.0,
               'RBC': 3.5, 'HCT': 35.0, 'RDW': 16.0, 'WBC': 5.0,
               'Platelets': 200.0, 'Sex': 'M', 'Age': 50,
               'Neutrophils': 60.0, 'Lymphocytes': 30.0}
        row = mock_engine.add_indices(cbc)
        _, rules = mock_engine.apply_rules(row)
        assert "Macrocytosis" in rules

    def test_clinical_rules_pancytopenia(self, mock_engine):
        """Low Hb, WBC, Platelets should trigger Pancytopenia rule."""
        cbc = {'Hb': 8.0, 'MCV': 105.0, 'MCH': 30.0, 'MCHC': 34.0,
               'RBC': 2.5, 'HCT': 25.0, 'RDW': 18.0, 'WBC': 3.0,
               'Platelets': 100.0, 'Sex': 'F', 'Age': 60,
               'Neutrophils': 40.0, 'Lymphocytes': 50.0}
        row = mock_engine.add_indices(cbc)
        _, rules = mock_engine.apply_rules(row)
        assert "Pancytopenia" in rules


class TestMLEngineAsync:
    """Tests for async prediction functionality."""

    def test_predict_async_is_coroutine_function(self):
        """Verify predict_async is an async callable."""
        import asyncio
        from apps.screening.ml_engine import predict_async

        assert callable(predict_async)
        assert asyncio.iscoroutinefunction(predict_async)

    @pytest.mark.asyncio
    async def test_async_predict_calls_engine(self, sample_cbc_data):
        """Test that predict_async delegates to the engine via a thread pool."""
        from apps.screening.ml_engine import predict_async

        mock_result = {
            'riskClass': 1,
            'labelText': 'NORMAL',
            'probabilities': {'normal': 0.85, 'borderline': 0.1, 'deficient': 0.05},
        }
        with patch('apps.screening.ml_engine.get_ml_engine') as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.predict.return_value = mock_result
            mock_get_engine.return_value = mock_engine

            result = await predict_async(sample_cbc_data)
            assert result == mock_result
            mock_engine.predict.assert_called_once_with(sample_cbc_data)

"""
Tests for the ML engine (B12 screening classification) v2.
"""

import pytest
from unittest.mock import MagicMock, patch


def _make_mock_engine():
    """Create a v2 engine with mocked models and config."""
    from apps.screening.ml_engine import B12ClinicalEngine

    engine = B12ClinicalEngine.__new__(B12ClinicalEngine)
    engine._ready = True
    engine._load_error = None
    engine._model_version = "2.0.0"
    engine._model_artifact_hash = "test_hash"
    engine.model_dir = MagicMock()
    engine.config = {"version": "2.0.0", "stage1_auc": 0.877}
    engine.zone_lo = 0.1
    engine.zone_hi = 0.6
    engine.t_def = 0.42
    engine.t_norm = 0.2
    engine.t_s2 = 0.35

    import numpy as np
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
        # Without model files, engine should not be ready
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
        import numpy as np
        mock_engine.stage1.predict_proba.return_value = np.array([[0.85, 0.15]])

        result = mock_engine.predict(sample_cbc_data)

        assert result is not None
        assert "riskClass" in result
        assert result["riskClass"] in [1, 2, 3]

    def test_predict_deficient_sample(self, mock_engine, sample_cbc_deficient):
        """Test prediction returns Deficient for abnormal CBC values."""
        import numpy as np
        mock_engine.stage1.predict_proba.return_value = np.array([[0.1, 0.9]])
        mock_engine.stage2.predict_proba.return_value = np.array([[0.2, 0.8]])

        result = mock_engine.predict(sample_cbc_deficient)

        assert result is not None
        assert result["riskClass"] == 3  # Deficient

    def test_predict_returns_v1_compat_keys(self, mock_engine, sample_cbc_data):
        """Test prediction returns all v1-compatible keys."""
        result = mock_engine.predict(sample_cbc_data)

        assert "riskClass" in result
        assert "labelText" in result
        assert "probabilities" in result
        assert "rulesFired" in result
        assert "modelVersion" in result
        assert "modelArtifactHash" in result
        assert "indices" in result

    def test_predict_returns_v2_new_keys(self, mock_engine, sample_cbc_data):
        """Test prediction returns new v2 fields."""
        result = mock_engine.predict(sample_cbc_data)

        assert "p_stage1" in result
        assert "p_stage2" in result
        assert "in_uncertain_zone" in result
        assert "confidence" in result
        assert "clinical_indices" in result
        assert "data_quality" in result
        assert "labelDescription" in result

    def test_predict_rules_fired_always_empty(self, mock_engine, sample_cbc_data):
        """v2 has no clinical rules — rulesFired should always be []."""
        result = mock_engine.predict(sample_cbc_data)
        assert result["rulesFired"] == []

    def test_predict_shap_values_always_empty(self, mock_engine, sample_cbc_data):
        """v2 does not support SHAP — shap_values should always be {}."""
        result = mock_engine.predict(sample_cbc_data, include_shap=True)
        assert result["indices"]["shap_values"] == {}

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
        engine.config = None

        with pytest.raises(MLModelNotReadyError):
            engine.predict(sample_cbc_data)

    def test_predict_uncertain_zone_triggers_stage2(self, mock_engine, sample_cbc_data):
        """When p_stage1 is in uncertain zone, stage2 should fire."""
        import numpy as np
        mock_engine.stage1.predict_proba.return_value = np.array([[0.7, 0.3]])  # in [0.1, 0.6]

        result = mock_engine.predict(sample_cbc_data)

        assert result["in_uncertain_zone"] is True
        assert result["p_stage2"] is not None
        mock_engine.stage2.predict_proba.assert_called_once()

    def test_predict_outside_zone_still_runs_stage2(self, mock_engine, sample_cbc_data):
        """Stage2 now runs on ALL patients (Normal gate needs p_stage2)."""
        import numpy as np
        mock_engine.stage1.predict_proba.return_value = np.array([[0.95, 0.05]])  # below zone

        result = mock_engine.predict(sample_cbc_data)

        assert result["in_uncertain_zone"] is False
        assert result["p_stage2"] is not None
        mock_engine.stage2.predict_proba.assert_called_once()


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

    def test_data_quality_flags_out_of_range(self, mock_engine):
        """data_quality should flag values outside valid ranges."""
        cbc = {'Hb': 30.0, 'MCV': 90.0, 'MCH': 30.0, 'MCHC': 34.0,
               'RBC': 5.0, 'HCT': 42.0, 'RDW': 13.0, 'WBC': 7.0,
               'Platelets': 250.0, 'Sex': 'M', 'Age': 35,
               'Neutrophils': 60.0, 'Lymphocytes': 30.0}
        result = mock_engine.predict(cbc)
        assert result['data_quality']['valid'] is False
        assert len(result['data_quality']['warnings']) > 0


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
            'label': 'Normal',
            'probabilities': {'normal': 0.85, 'borderline': 0.1, 'deficient': 0.05},
        }
        with patch('apps.screening.ml_engine.get_ml_engine') as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.predict.return_value = mock_result
            mock_get_engine.return_value = mock_engine

            result = await predict_async(sample_cbc_data)
            assert result == mock_result
            mock_engine.predict.assert_called_once_with(sample_cbc_data, include_shap=False)

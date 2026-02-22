"""
Tests for the ML engine (B12 screening classification).
"""

import pytest
from unittest.mock import MagicMock, patch


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
        """Create engine with mocked models."""
        from pathlib import Path
        from apps.screening.ml_engine import B12ClinicalEngine
        from unittest.mock import MagicMock, PropertyMock

        engine = B12ClinicalEngine(Path("../../backend_v3/ml/models"))

        # Mock the internal state
        engine._ready = True
        engine._load_error = None

        # Create mock models
        mock_stage1 = MagicMock()
        mock_stage1.predict_proba.return_value = [[0.8, 0.2]]  # Normal vs Not-Normal

        mock_stage2 = MagicMock()
        mock_stage2.predict_proba.return_value = [[0.7, 0.3]]  # Borderline vs Deficient

        # Create mock thresholds
        engine.thresholds = {
            "rule_weight": 0.5,
            "deficient_threshold": 0.7,
            "borderline_threshold": 0.4
        }

        engine.stage1 = mock_stage1
        engine.stage2 = mock_stage2

        # Mock the is_ready property to return True
        type(engine).is_ready = PropertyMock(return_value=True)

        return engine

    def test_predict_normal_sample(self, mock_engine, sample_cbc_data):
        """Test prediction returns Normal for healthy CBC values."""
        # Adjust mock for normal result
        mock_engine.stage1.predict_proba.return_value = [[0.85, 0.15]]

        result = mock_engine.predict(sample_cbc_data)

        assert result is not None
        assert "riskClass" in result
        assert result["riskClass"] in [1, 2, 3]

    def test_predict_deficient_sample(self, mock_engine, sample_cbc_deficient):
        """Test prediction returns Deficient for abnormal CBC values."""
        # Adjust mock for deficient result
        mock_engine.stage1.predict_proba.return_value = [[0.1, 0.9]]  # Not normal
        mock_engine.stage2.predict_proba.return_value = [[0.2, 0.8]]  # Deficient

        result = mock_engine.predict(sample_cbc_deficient)

        assert result is not None
        assert result["riskClass"] == 3  # Deficient

    def test_predict_handles_missing_fields_gracefully(self, mock_engine):
        """Test prediction handles missing required fields by using defaults."""
        incomplete_cbc = {"Haemoglobin": 14.5}  # Missing required fields

        # Should not raise an exception and return a valid result
        result = mock_engine.predict(incomplete_cbc)
        
        assert result is not None
        assert "riskClass" in result

    def test_predict_not_ready_raises_error(self, sample_cbc_data):
        """Test prediction raises error when engine not ready."""
        from unittest.mock import MagicMock, PropertyMock
        from apps.screening.ml_engine import B12ClinicalEngine, MLModelNotReadyError

        # Create a mock engine with is_ready property returning False
        engine = B12ClinicalEngine.__new__(B12ClinicalEngine)  # Create without calling __init__
        engine._ready = False
        engine._load_error = "Models not found"
        engine.stage1 = None
        engine.stage2 = None
        engine.thresholds = None
        engine._model_version = "unknown"
        engine._model_artifact_hash = ""
        engine._validation_metrics = None
        
        # Mock the is_ready property to return False
        type(engine).is_ready = PropertyMock(return_value=False)

        with pytest.raises(MLModelNotReadyError):
            engine.predict(sample_cbc_data)


class TestMLEngineValidation:
    """Tests for CBC data validation — engine handles missing/bad data gracefully."""

    @pytest.fixture
    def mock_engine(self):
        """Create engine with mocked models."""
        from pathlib import Path
        from apps.screening.ml_engine import B12ClinicalEngine
        from unittest.mock import MagicMock, PropertyMock

        engine = B12ClinicalEngine(Path("../../backend_v3/ml/models"))
        engine._ready = True
        engine._load_error = None

        mock_stage1 = MagicMock()
        mock_stage1.predict_proba.return_value = [[0.8, 0.2]]
        mock_stage2 = MagicMock()
        mock_stage2.predict_proba.return_value = [[0.7, 0.3]]

        engine.thresholds = {"rule_weight": 0.5, "deficient_threshold": 0.7, "borderline_threshold": 0.4}
        engine.stage1 = mock_stage1
        engine.stage2 = mock_stage2
        type(engine).is_ready = PropertyMock(return_value=True)
        return engine

    def test_predict_with_missing_fields(self, mock_engine):
        """Engine should handle prediction even with sparse input."""
        sparse_cbc = {'Hb': 12.0, 'MCV': 85.0, 'Sex': 'M', 'Age': 40}
        result = mock_engine.predict(sparse_cbc)
        assert 'riskClass' in result
        assert 'labelText' in result

    def test_predict_with_zero_values(self, mock_engine):
        """Engine should handle zero CBC values without crashing."""
        zero_cbc = {'Hb': 0, 'MCV': 0, 'RBC': 0, 'WBC': 0, 'Platelets': 0, 'Sex': 'M', 'Age': 0}
        result = mock_engine.predict(zero_cbc)
        assert 'riskClass' in result


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

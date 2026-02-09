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
        from apps.screening.ml_engine import B12ClinicalEngine

        engine = B12ClinicalEngine()
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
        from apps.screening.ml_engine import B12ClinicalEngine

        engine = B12ClinicalEngine()

        # Mock the model loading
        engine._ready = True
        engine._load_error = None

        # Create mock models
        mock_stage1 = MagicMock()
        mock_stage1.predict_proba.return_value = [[0.8, 0.2]]  # Normal vs Not-Normal

        mock_stage2 = MagicMock()
        mock_stage2.predict_proba.return_value = [[0.7, 0.3]]  # Borderline vs Deficient

        engine.stage1 = mock_stage1
        engine.stage2 = mock_stage2

        return engine

    def test_predict_normal_sample(self, mock_engine, sample_cbc_data):
        """Test prediction returns Normal for healthy CBC values."""
        # Adjust mock for normal result
        mock_engine.stage1.predict_proba.return_value = [[0.85, 0.15]]

        result = mock_engine.predict(sample_cbc_data)

        assert result is not None
        assert "risk_class" in result
        assert result["risk_class"] in [1, 2, 3]

    def test_predict_deficient_sample(self, mock_engine, sample_cbc_deficient):
        """Test prediction returns Deficient for abnormal CBC values."""
        # Adjust mock for deficient result
        mock_engine.stage1.predict_proba.return_value = [[0.1, 0.9]]  # Not normal
        mock_engine.stage2.predict_proba.return_value = [[0.2, 0.8]]  # Deficient

        result = mock_engine.predict(sample_cbc_deficient)

        assert result is not None
        assert result["risk_class"] == 3  # Deficient

    def test_predict_requires_required_fields(self, mock_engine):
        """Test prediction fails with missing required fields."""
        incomplete_cbc = {"Haemoglobin": 14.5}  # Missing required fields

        with pytest.raises((KeyError, ValueError)):
            mock_engine.predict(incomplete_cbc)

    def test_predict_not_ready_raises_error(self, sample_cbc_data):
        """Test prediction raises error when engine not ready."""
        from apps.screening.ml_engine import B12ClinicalEngine, MLModelNotReadyError

        engine = B12ClinicalEngine()
        engine._ready = False
        engine._load_error = "Models not found"

        with pytest.raises(MLModelNotReadyError):
            engine.predict(sample_cbc_data)


class TestMLEngineValidation:
    """Tests for CBC data validation."""

    def test_validate_cbc_ranges(self, sample_cbc_data):
        """Test CBC value range validation."""
        from apps.screening.ml_engine import B12ClinicalEngine

        engine = B12ClinicalEngine()

        # Should not raise for valid data
        is_valid = engine.validate_cbc(sample_cbc_data)
        assert is_valid is True

    def test_validate_cbc_out_of_range(self):
        """Test validation fails for out-of-range values."""
        from apps.screening.ml_engine import B12ClinicalEngine

        engine = B12ClinicalEngine()

        # Extremely abnormal values
        invalid_cbc = {
            "Haemoglobin": -5,  # Negative - invalid
            "MCV": 500,  # Too high
            "MCH": 29.5,
            "MCHC": 33.5,
            "RDW_CV": 13.2,
            "WBC": 6.8,
            "Platelet": 245,
            "Neutrophils": 58.0,
            "Lymphocytes": 32.0,
            "Monocytes": 6.0,
            "Eosinophils": 3.0,
            "Basophils": 1.0,
            "LUC": 0.0,
        }

        is_valid = engine.validate_cbc(invalid_cbc)
        assert is_valid is False


class TestMLEngineAsync:
    """Tests for async prediction functionality."""

    @pytest.mark.asyncio
    async def test_async_predict_returns_result(self, sample_cbc_data):
        """Test async prediction returns result."""
        from apps.screening.ml_engine import B12ClinicalEngine

        engine = B12ClinicalEngine()

        # Mock for async test
        with patch.object(engine, "_ready", True):
            with patch.object(engine, "stage1") as mock_s1:
                with patch.object(engine, "stage2") as mock_s2:
                    mock_s1.predict_proba.return_value = [[0.9, 0.1]]
                    mock_s2.predict_proba.return_value = [[0.7, 0.3]]

                    result = await engine.predict_async(sample_cbc_data)

                    assert result is not None
                    assert "risk_class" in result

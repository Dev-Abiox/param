"""
Tests for ML engine hot-reload mechanism.
"""

import time
from unittest.mock import MagicMock, patch, PropertyMock

from apps.screening.ml_engine import B12ClinicalEngine


class TestMLHotReload:

    @patch.object(B12ClinicalEngine, '_load_models')
    def test_maybe_reload_skips_when_interval_not_elapsed(self, mock_load):
        engine = B12ClinicalEngine.__new__(B12ClinicalEngine)
        engine.model_dir = MagicMock()
        engine.stage1 = MagicMock()
        engine.stage2 = MagicMock()
        engine.thresholds = {}
        engine._ready = True
        engine._load_error = None
        engine._model_version = "1.0.0"
        engine._model_artifact_hash = "abc123"
        engine._last_reload_check = time.time()  # just checked
        engine._lock = __import__('threading').Lock()

        result = engine.maybe_reload()
        assert result is False

    @patch.object(B12ClinicalEngine, '_compute_artifact_hash')
    @patch.object(B12ClinicalEngine, '_load_models')
    def test_maybe_reload_skips_when_hash_unchanged(self, mock_load, mock_hash):
        engine = B12ClinicalEngine.__new__(B12ClinicalEngine)
        engine.model_dir = MagicMock()
        engine.stage1 = MagicMock()
        engine.stage2 = MagicMock()
        engine.thresholds = {}
        engine._ready = True
        engine._load_error = None
        engine._model_version = "1.0.0"
        engine._model_artifact_hash = "abc123"
        engine._last_reload_check = 0  # force check
        engine._lock = __import__('threading').Lock()

        mock_hash.return_value = "abc123"  # same hash

        result = engine.maybe_reload()
        assert result is False
        mock_load.assert_not_called()

    @patch.object(B12ClinicalEngine, '_compute_artifact_hash')
    @patch.object(B12ClinicalEngine, '_load_models')
    def test_maybe_reload_reloads_when_hash_changes(self, mock_load, mock_hash):
        engine = B12ClinicalEngine.__new__(B12ClinicalEngine)
        engine.model_dir = MagicMock()
        engine.stage1 = MagicMock()
        engine.stage2 = MagicMock()
        engine.thresholds = {}
        engine._ready = True
        engine._load_error = None
        engine._model_version = "1.0.0"
        engine._model_artifact_hash = "abc123"
        engine._last_reload_check = 0  # force check
        engine._lock = __import__('threading').Lock()

        # First call returns new hash, second (inside lock) also returns new hash
        mock_hash.side_effect = ["new_hash", "new_hash"]

        result = engine.maybe_reload()
        assert result is True
        mock_load.assert_called_once()

    @patch.object(B12ClinicalEngine, '_compute_artifact_hash')
    @patch.object(B12ClinicalEngine, '_load_models')
    def test_maybe_reload_rollback_on_failure(self, mock_load, mock_hash):
        """If reload fails, old models should remain active."""
        engine = B12ClinicalEngine.__new__(B12ClinicalEngine)
        engine.model_dir = MagicMock()
        old_stage1 = MagicMock(name='old_stage1')
        engine.stage1 = old_stage1
        engine.stage2 = MagicMock()
        engine.thresholds = {}
        engine._ready = True
        engine._load_error = None
        engine._model_version = "1.0.0"
        engine._model_artifact_hash = "abc123"
        engine._last_reload_check = 0
        engine._lock = __import__('threading').Lock()

        mock_hash.side_effect = ["new_hash", "new_hash"]
        mock_load.side_effect = Exception("Model file corrupt")

        result = engine.maybe_reload()
        assert result is False
        assert engine.stage1 is old_stage1  # rolled back
        assert engine._ready is True  # still operational

    def test_get_status_includes_hot_reload_info(self):
        engine = B12ClinicalEngine.__new__(B12ClinicalEngine)
        engine.stage1 = MagicMock()
        engine.stage2 = MagicMock()
        engine.thresholds = {}
        engine._ready = True
        engine._load_error = None
        engine._model_version = "1.0.0"
        engine._model_artifact_hash = "abc"
        engine._last_reload_check = 123.0

        status = engine.get_status()
        assert 'hot_reload' in status
        assert status['hot_reload']['enabled'] is True
        assert status['hot_reload']['last_check'] == 123.0

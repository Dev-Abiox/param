"""
Tests for analytics cache invalidation utility.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestAnalyticsCacheInvalidation:

    @patch("apps.analytics.cache.cache")
    @patch("apps.analytics.cache.connection")
    def test_invalidate_deletes_expected_keys(self, mock_conn, mock_cache):
        """invalidate_analytics_caches should delete all known cache keys."""
        from apps.analytics.cache import invalidate_analytics_caches

        mock_conn.schema_name = "test_org"

        invalidate_analytics_caches(user_id=42, doctor_code="D001")

        call_args = mock_cache.delete_many.call_args[0][0]
        # Should include summary, labs, doctors, population, cohorts, comparison keys
        assert any("summary:42" in k for k in call_args)
        assert any("labs" in k for k in call_args)
        assert any("doctors:D001" in k for k in call_args)
        assert any("doctors:all" in k for k in call_args)
        assert any("population_trends" in k for k in call_args)
        assert any("population_cohorts" in k for k in call_args)
        assert any("lab_comparison" in k for k in call_args)

    @patch("apps.analytics.cache.cache")
    @patch("apps.analytics.cache.connection")
    def test_invalidate_without_user_id(self, mock_conn, mock_cache):
        """Should work without user_id (summary key omitted)."""
        from apps.analytics.cache import invalidate_analytics_caches

        mock_conn.schema_name = "test_org"

        invalidate_analytics_caches()

        call_args = mock_cache.delete_many.call_args[0][0]
        assert not any("summary" in k for k in call_args)

    @patch("apps.analytics.cache.cache")
    @patch("apps.analytics.cache.connection")
    def test_invalidate_handles_redis_failure(self, mock_conn, mock_cache):
        """Should not raise if Redis is down."""
        from redis.exceptions import RedisError

        from apps.analytics.cache import invalidate_analytics_caches

        mock_conn.schema_name = "test_org"
        mock_cache.delete_many.side_effect = RedisError("Connection refused")

        # Should not raise
        invalidate_analytics_caches(user_id=1)

    @patch("apps.analytics.cache.connection")
    def test_cache_key_includes_schema(self, mock_conn):
        """Cache keys should be scoped to the tenant schema."""
        from apps.analytics.cache import _cache_key

        mock_conn.schema_name = "org_acme"
        key = _cache_key("summary", 1)
        assert key == "analytics:org_acme:summary:1"

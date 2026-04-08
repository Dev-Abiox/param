"""
Analytics cache invalidation utilities.

Call `invalidate_analytics_caches()` after creating a new screening to
ensure dashboards reflect up-to-date data.
"""

import logging

from django.core.cache import cache
from django.db import connection
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def _cache_key(*parts) -> str:
    schema = getattr(connection, 'schema_name', 'public')
    return "analytics:" + ":".join(str(p) for p in [schema, *parts])


def invalidate_analytics_caches(
    user_id: str | int | None = None,
    doctor_code: str | None = None,
) -> None:
    """
    Bust all analytics caches for the current tenant after a new screening.

    Args:
        user_id: The requesting user's PK (for SummaryView per-user cache).
        doctor_code: The doctor code (for DoctorStatsView per-doctor cache).
    """
    keys_to_delete = [
        _cache_key('labs'),
        _cache_key('doctors', doctor_code or 'all'),
        _cache_key('doctors', 'all'),
        _cache_key('population_trends', 6),   # default months
        _cache_key('population_trends', 12),
        _cache_key('population_cohorts'),
        _cache_key('lab_comparison'),
    ]
    if user_id:
        keys_to_delete.append(_cache_key('summary', user_id))

    try:
        cache.delete_many(keys_to_delete)
    except (RedisError, Exception):
        logger.warning("analytics_cache_invalidation_failed", exc_info=True)

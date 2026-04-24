"""Tests for the Screening age-bucket / sex-code helpers (P0-4c)."""

import pytest


class TestAgeBucketFor:
    def test_pediatric_boundaries(self):
        from apps.screening.models import age_bucket_for
        assert age_bucket_for(0) == 'pediatric'
        assert age_bucket_for(5) == 'pediatric'
        assert age_bucket_for(17) == 'pediatric'

    def test_young_adult_boundaries(self):
        from apps.screening.models import age_bucket_for
        assert age_bucket_for(18) == 'young_adult'
        assert age_bucket_for(30) == 'young_adult'
        assert age_bucket_for(39) == 'young_adult'

    def test_middle_aged_boundaries(self):
        from apps.screening.models import age_bucket_for
        assert age_bucket_for(40) == 'middle_aged'
        assert age_bucket_for(55) == 'middle_aged'
        assert age_bucket_for(59) == 'middle_aged'

    def test_elderly_boundaries(self):
        from apps.screening.models import age_bucket_for
        assert age_bucket_for(60) == 'elderly'
        assert age_bucket_for(80) == 'elderly'
        assert age_bucket_for(120) == 'elderly'

    def test_non_numeric_returns_unknown(self):
        from apps.screening.models import age_bucket_for
        assert age_bucket_for(None) == ''
        assert age_bucket_for('') == ''
        assert age_bucket_for('unknown') == ''
        assert age_bucket_for([]) == ''

    def test_negative_returns_unknown(self):
        from apps.screening.models import age_bucket_for
        assert age_bucket_for(-1) == ''

    def test_numeric_string_coerced(self):
        from apps.screening.models import age_bucket_for
        assert age_bucket_for('42') == 'middle_aged'
        assert age_bucket_for('17') == 'pediatric'

    def test_float_coerced(self):
        from apps.screening.models import age_bucket_for
        assert age_bucket_for(42.7) == 'middle_aged'


class TestSexCodeFor:
    def test_single_letter_forms(self):
        from apps.screening.models import sex_code_for
        assert sex_code_for('M') == 'M'
        assert sex_code_for('F') == 'F'
        assert sex_code_for('m') == 'M'
        assert sex_code_for('f') == 'F'

    def test_full_word_forms(self):
        from apps.screening.models import sex_code_for
        assert sex_code_for('Male') == 'M'
        assert sex_code_for('female') == 'F'
        assert sex_code_for('FEMALE') == 'F'

    def test_whitespace_stripped(self):
        from apps.screening.models import sex_code_for
        assert sex_code_for('  M  ') == 'M'
        assert sex_code_for(' female ') == 'F'

    def test_unknown_returns_empty(self):
        from apps.screening.models import sex_code_for
        assert sex_code_for('X') == ''
        assert sex_code_for('other') == ''
        assert sex_code_for(None) == ''
        assert sex_code_for('') == ''

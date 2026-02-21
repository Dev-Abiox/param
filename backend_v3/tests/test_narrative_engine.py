"""
Tests for the clinical narrative engine.
"""

from unittest.mock import MagicMock, patch

from apps.screening.narrative_engine import (
    DIFFERENTIAL_TABLE,
    TEMPLATES,
    NarrativeEngine,
)


# ── Age Group Classification ─────────────────────────────────────────────────

class TestAgeGroupClassification:

    def test_pediatric_lower_bound(self):
        engine = NarrativeEngine()
        assert engine.classify_age_group(0) == 'pediatric'

    def test_pediatric_upper_bound(self):
        engine = NarrativeEngine()
        assert engine.classify_age_group(17) == 'pediatric'

    def test_young_adult(self):
        engine = NarrativeEngine()
        assert engine.classify_age_group(25) == 'young_adult'

    def test_young_adult_boundary(self):
        engine = NarrativeEngine()
        assert engine.classify_age_group(18) == 'young_adult'
        assert engine.classify_age_group(39) == 'young_adult'

    def test_middle_aged(self):
        engine = NarrativeEngine()
        assert engine.classify_age_group(45) == 'middle_aged'

    def test_middle_aged_boundary(self):
        engine = NarrativeEngine()
        assert engine.classify_age_group(40) == 'middle_aged'
        assert engine.classify_age_group(59) == 'middle_aged'

    def test_elderly(self):
        engine = NarrativeEngine()
        assert engine.classify_age_group(70) == 'elderly'

    def test_elderly_boundary(self):
        engine = NarrativeEngine()
        assert engine.classify_age_group(60) == 'elderly'


# ── Template Selection ────────────────────────────────────────────────────────

class TestTemplateSelection:

    def test_macrocytic_high_risk(self):
        engine = NarrativeEngine()
        key = engine.select_template_key(3, 'middle_aged', 'M', ['Macrocytosis', 'High RDW'])
        assert key == 'macrocytic_high_risk'

    def test_borderline_elderly(self):
        engine = NarrativeEngine()
        key = engine.select_template_key(2, 'elderly', 'F', [])
        assert key == 'borderline_elderly'

    def test_normal_young_adult(self):
        engine = NarrativeEngine()
        key = engine.select_template_key(1, 'young_adult', 'M', [])
        assert key == 'normal_young'

    def test_normal_pediatric(self):
        engine = NarrativeEngine()
        key = engine.select_template_key(1, 'pediatric', 'F', [])
        assert key == 'normal_young'

    def test_deficient_with_trend(self):
        engine = NarrativeEngine()
        key = engine.select_template_key(3, 'middle_aged', 'M', ['High RDW'])
        assert key == 'deficient_with_trend'

    def test_borderline_low_mcv(self):
        engine = NarrativeEngine()
        key = engine.select_template_key(2, 'middle_aged', 'F', ['Preserved cell counts'])
        assert key == 'borderline_low_mcv'

    def test_normal_elderly_uses_default(self):
        engine = NarrativeEngine()
        key = engine.select_template_key(1, 'elderly', 'M', [])
        assert key == 'normal_default'

    def test_borderline_with_macrocytosis_uses_default(self):
        engine = NarrativeEngine()
        key = engine.select_template_key(2, 'young_adult', 'M', ['Macrocytosis'])
        assert key == 'borderline_default'

    def test_all_template_keys_exist_in_templates(self):
        engine = NarrativeEngine()
        combos = [
            (3, 'middle_aged', 'M', ['Macrocytosis']),
            (2, 'elderly', 'F', []),
            (1, 'young_adult', 'M', []),
            (3, 'young_adult', 'M', []),
            (2, 'middle_aged', 'F', []),
            (1, 'elderly', 'F', []),
            (1, 'middle_aged', 'M', []),
        ]
        for risk, age_g, sex, rules in combos:
            key = engine.select_template_key(risk, age_g, sex, rules)
            assert key in TEMPLATES, f"Key {key} not in TEMPLATES"


# ── Differential Suggestions ─────────────────────────────────────────────────

class TestDifferentialSuggestions:

    def test_macrocytosis_differentials(self):
        engine = NarrativeEngine()
        diffs = engine.get_differential_suggestions(3, ['Macrocytosis'], {})
        assert 'Vitamin B12 deficiency' in diffs
        assert 'Folate deficiency' in diffs

    def test_multiple_rules_deduplicates(self):
        engine = NarrativeEngine()
        diffs = engine.get_differential_suggestions(
            3, ['Macrocytosis', 'Pancytopenia'], {},
        )
        # Severe B12 deficiency appears in Pancytopenia table
        assert 'Severe B12 deficiency' in diffs
        # Myelodysplastic syndrome appears in both tables but should appear once
        count = diffs.count('Myelodysplastic syndrome')
        assert count == 1

    def test_empty_rules_borderline_returns_subclinical(self):
        engine = NarrativeEngine()
        diffs = engine.get_differential_suggestions(2, [], {})
        assert 'Subclinical B12 deficiency' in diffs

    def test_empty_rules_normal_returns_empty(self):
        engine = NarrativeEngine()
        diffs = engine.get_differential_suggestions(1, [], {})
        assert diffs == []

    def test_high_mentzer_adds_iron_deficiency(self):
        engine = NarrativeEngine()
        diffs = engine.get_differential_suggestions(3, [], {'mentzer': 15.0})
        assert 'Iron deficiency anemia' in diffs

    def test_mentzer_not_duplicated_with_erythropoiesis(self):
        engine = NarrativeEngine()
        diffs = engine.get_differential_suggestions(
            3, ['Ineffective erythropoiesis'], {'mentzer': 15.0},
        )
        count = diffs.count('Iron deficiency anemia')
        assert count == 1


# ── Trend Fragment ────────────────────────────────────────────────────────────

class TestTrendFragment:
    """Tests for build_trend_fragment which uses values_list query."""

    def _mock_screening_qs(self, mock_screening_cls, risk_values):
        """Set up mock chain: .filter().order_by().values_list()[:5] → risk_values."""
        mock_qs = MagicMock()
        mock_screening_cls.objects.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.values_list.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=risk_values)

    @patch('apps.screening.models.Screening')
    def test_no_patient_returns_empty(self, mock_screening_cls):
        self._mock_screening_qs(mock_screening_cls, [])

        engine = NarrativeEngine()
        result = engine.build_trend_fragment('UNKNOWN', 2)
        assert result == ''

    @patch('apps.screening.models.Screening')
    def test_no_history_returns_empty(self, mock_screening_cls):
        self._mock_screening_qs(mock_screening_cls, [])

        engine = NarrativeEngine()
        result = engine.build_trend_fragment('P001', 2)
        assert result == ''

    @patch('apps.screening.models.Screening')
    def test_worsening_trend(self, mock_screening_cls):
        # All prior risk classes < current (3) → worsening
        self._mock_screening_qs(mock_screening_cls, [1, 2])

        engine = NarrativeEngine()
        result = engine.build_trend_fragment('P001', 3)
        assert 'worsening' in result.lower()

    @patch('apps.screening.models.Screening')
    def test_improving_trend(self, mock_screening_cls):
        # All prior risk classes > current (1) → improving
        self._mock_screening_qs(mock_screening_cls, [3, 2])

        engine = NarrativeEngine()
        result = engine.build_trend_fragment('P001', 1)
        assert 'improving' in result.lower()

    @patch('apps.screening.models.Screening')
    def test_stable_trend(self, mock_screening_cls):
        # All prior risk classes == current (2) → stable
        self._mock_screening_qs(mock_screening_cls, [2, 2, 2])

        engine = NarrativeEngine()
        result = engine.build_trend_fragment('P001', 2)
        assert 'stable' in result.lower()


# ── Full Narrative Generation ─────────────────────────────────────────────────

class TestFullGeneration:

    @patch.object(NarrativeEngine, 'build_trend_fragment', return_value='')
    def test_deficient_macrocytic_narrative(self, mock_trend):
        engine = NarrativeEngine()
        narrative = engine.generate(
            risk_class=3,
            label_text='DEFICIENT',
            probabilities={'normal': 0.05, 'borderline': 0.15, 'deficient': 0.8},
            rules_fired=['Macrocytosis', 'High RDW'],
            indices={'mentzer': 15.0, 'greenKing': 80.0, 'nlr': 2.5, 'pancytopenia': 0},
            cbc_snapshot={'MCV': 108, 'RDW': 18.5},
            age=55,
            sex='M',
            patient_id='P001',
        )
        assert len(narrative) > 50
        assert 'DEFICIENT' in narrative
        assert '108' in narrative  # MCV value
        assert 'serum B12' in narrative.lower() or 'b12' in narrative.lower()

    @patch.object(NarrativeEngine, 'build_trend_fragment', return_value='')
    def test_normal_young_narrative(self, mock_trend):
        engine = NarrativeEngine()
        narrative = engine.generate(
            risk_class=1,
            label_text='NORMAL',
            probabilities={'normal': 0.9, 'borderline': 0.07, 'deficient': 0.03},
            rules_fired=['No macrocytosis / no pancytopenia', 'Preserved cell counts'],
            indices={'mentzer': 11.0, 'greenKing': 50.0, 'nlr': 1.8, 'pancytopenia': 0},
            cbc_snapshot={'MCV': 87, 'RDW': 13.2},
            age=25,
            sex='F',
            patient_id='P002',
        )
        assert 'normal' in narrative.lower()
        assert 'young adult' in narrative.lower()

    @patch.object(NarrativeEngine, 'build_trend_fragment', return_value='')
    def test_borderline_elderly_narrative(self, mock_trend):
        engine = NarrativeEngine()
        narrative = engine.generate(
            risk_class=2,
            label_text='BORDERLINE',
            probabilities={'normal': 0.3, 'borderline': 0.45, 'deficient': 0.25},
            rules_fired=['High RDW'],
            indices={'mentzer': 12.5, 'greenKing': 60.0, 'nlr': 2.0, 'pancytopenia': 0},
            cbc_snapshot={'MCV': 95, 'RDW': 16.0},
            age=72,
            sex='M',
            patient_id='P003',
        )
        assert 'elderly' in narrative.lower()
        assert 'age-related' in narrative.lower() or 'absorption' in narrative.lower()

    @patch.object(NarrativeEngine, 'build_trend_fragment', return_value='')
    def test_borderline_low_mcv_narrative(self, mock_trend):
        engine = NarrativeEngine()
        narrative = engine.generate(
            risk_class=2,
            label_text='BORDERLINE',
            probabilities={'normal': 0.35, 'borderline': 0.4, 'deficient': 0.25},
            rules_fired=['Preserved cell counts'],
            indices={'mentzer': 10.5, 'greenKing': 40.0, 'nlr': 1.5, 'pancytopenia': 0},
            cbc_snapshot={'MCV': 75, 'RDW': 14.0},
            age=35,
            sex='F',
            patient_id='P004',
        )
        assert '75' in narrative  # Low MCV value
        assert 'iron' in narrative.lower() or 'thalassemia' in narrative.lower()

    @patch.object(NarrativeEngine, 'build_trend_fragment', return_value='')
    def test_deficient_without_macrocytosis_no_trend(self, mock_trend):
        """When template is deficient_with_trend but no trend data, falls back to deficient_default."""
        engine = NarrativeEngine()
        narrative = engine.generate(
            risk_class=3,
            label_text='DEFICIENT',
            probabilities={'normal': 0.1, 'borderline': 0.2, 'deficient': 0.7},
            rules_fired=['High RDW', 'Ineffective erythropoiesis'],
            indices={'mentzer': 14.0, 'greenKing': 70.0, 'nlr': 3.0, 'pancytopenia': 0},
            cbc_snapshot={'MCV': 95, 'RDW': 17.0},
            age=50,
            sex='M',
            patient_id=None,
        )
        assert 'DEFICIENT' in narrative
        assert 'serum B12' in narrative.lower() or 'b12' in narrative.lower()

    @patch.object(NarrativeEngine, 'build_trend_fragment', return_value='')
    def test_narrative_includes_differentials(self, mock_trend):
        engine = NarrativeEngine()
        narrative = engine.generate(
            risk_class=3,
            label_text='DEFICIENT',
            probabilities={'normal': 0.05, 'borderline': 0.1, 'deficient': 0.85},
            rules_fired=['Macrocytosis', 'Pancytopenia'],
            indices={'mentzer': 16.0, 'greenKing': 90.0, 'nlr': 4.0, 'pancytopenia': 1},
            cbc_snapshot={'MCV': 110, 'RDW': 19.0},
            age=60,
            sex='F',
            patient_id='P005',
        )
        assert 'differential' in narrative.lower()
        assert 'B12 deficiency' in narrative or 'b12 deficiency' in narrative.lower()

    @patch.object(NarrativeEngine, 'build_trend_fragment',
                  return_value='This represents a worsening trend compared to prior screenings. ')
    def test_narrative_with_trend_data(self, mock_trend):
        engine = NarrativeEngine()
        narrative = engine.generate(
            risk_class=3,
            label_text='DEFICIENT',
            probabilities={'normal': 0.05, 'borderline': 0.15, 'deficient': 0.8},
            rules_fired=['Macrocytosis'],
            indices={'mentzer': 15.0, 'greenKing': 80.0, 'nlr': 2.5, 'pancytopenia': 0},
            cbc_snapshot={'MCV': 105, 'RDW': 16.0},
            age=55,
            sex='M',
            patient_id='P006',
        )
        assert 'worsening trend' in narrative.lower()

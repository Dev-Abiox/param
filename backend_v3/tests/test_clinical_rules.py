"""Unit tests for apps.screening.clinical_rules.

These rule modules are deliberately Django-free — pure functions over a
CBC dict — so the tests are pure pytest, no ``django_db`` marker, no
fixtures beyond the in-file CBC builders.
"""

from __future__ import annotations

from apps.screening.clinical_rules import (
    all_clinical_rules,
    anemia_subtype_suspicion,
    iron_deficiency_recommendation,
    macrocytic_anemia_recommendation,
    thalassemia_trait_recommendation,
)


# ── helpers ───────────────────────────────────────────────────────────

def _cbc(**overrides) -> dict:
    """Return a healthy adult-male CBC, overridable per test."""
    base = {
        'Hb': 14.5, 'RBC': 4.8, 'HCT': 43.0,
        'MCV': 88.0, 'MCH': 29.5, 'MCHC': 33.5, 'RDW': 13.2,
        'WBC': 6.8, 'Platelets': 245.0,
        'Neutrophils': 58.0, 'Lymphocytes': 32.0,
        'Sex': 'M', 'Age': 35,
    }
    base.update(overrides)
    return base


# ── Module 1: iron deficiency ─────────────────────────────────────────

class TestIronDeficiency:
    def test_healthy_does_not_flag(self):
        out = iron_deficiency_recommendation(_cbc())
        assert out['flag'] is False
        assert out['reasoning'] == []
        assert out['recommendation'] is None

    def test_classic_ida_pattern_flags_high(self):
        # Hb 9, MCV 70, MCHC 30, RBC 4.0, RDW 17, female (anemia threshold 12)
        # Microcytic ✓ → mentzer = 70/4.0 = 17.5 > 13 (IDA-favoring)
        # green_king = 70²·17/(9·100) = 92.5 > 65 (IDA-favoring)
        # plus microcytic_hypochromic + anisocytosis + low_hb = 5 triggers
        out = iron_deficiency_recommendation(
            _cbc(Hb=9.0, MCV=70.0, MCHC=30.0, RBC=4.0, RDW=17.0, Sex='F')
        )
        assert out['flag'] is True
        assert out['confidence'] == 'high'
        assert 'microcytic_hypochromic_anemia' in out['reasoning']
        assert 'mentzer_gt_13_ida_favored_over_btt' in out['reasoning']
        assert 'green_king_gt_65_ida_favored_over_btt' in out['reasoning']
        assert 'anisocytosis_with_microcytosis' in out['reasoning']
        assert 'low_hb_with_low_normal_mcv' in out['reasoning']
        assert out['recommendation'] == 'Consider reflex ferritin and iron studies testing'

    def test_mentzer_lt_13_does_not_flag_iron(self):
        # MCV=70, RBC=5.5 → mentzer=12.7 < 13.  This is the BTT direction,
        # so the iron module must NOT cite Mentzer as evidence here.
        out = iron_deficiency_recommendation(
            _cbc(Hb=12.0, MCV=70.0, RBC=5.5, RDW=13.0, MCHC=33.0, Sex='M')
        )
        # Iron module may still flag via low_hb/microcytic_hypochromic, but
        # Mentzer must not be in the reasoning.
        assert 'mentzer_gt_13_ida_favored_over_btt' not in out['reasoning']

    def test_green_king_not_evaluated_in_non_microcytic(self):
        # Healthy-adult CBC has Green-King ≈ 70 mathematically, but the
        # rule is gated on microcytic — must not fire here.
        out = iron_deficiency_recommendation(
            _cbc(Hb=14.0, MCV=85.0, RBC=4.5, RDW=13.0, MCHC=33.0)
        )
        assert out['flag'] is False
        assert 'green_king_gt_65_ida_favored_over_btt' not in out['reasoning']

    def test_low_hb_with_low_normal_mcv_male_threshold(self):
        # Male, Hb 12 (< 13 threshold), MCV 84 (< 85)
        out = iron_deficiency_recommendation(
            _cbc(Hb=12.0, MCV=84.0, Sex='M', RBC=4.5, RDW=13.0, MCHC=33.0)
        )
        assert out['flag'] is True
        assert 'low_hb_with_low_normal_mcv' in out['reasoning']

    def test_female_anemia_threshold_12(self):
        # Female, Hb 12.5 → above threshold, no anemia flag
        out = iron_deficiency_recommendation(
            _cbc(Hb=12.5, MCV=84.0, Sex='F', RBC=4.5, RDW=13.0, MCHC=33.0)
        )
        # Hb >= 12 for female → low_hb_with_low_normal_mcv must NOT trigger
        assert 'low_hb_with_low_normal_mcv' not in out['reasoning']

    def test_two_rules_yields_medium_confidence(self):
        # Pick a non-microcytic anemic profile so Mentzer / Green-King are
        # skipped (gated on MCV<80) and only two rules can fire.
        # Hb=11 (anemic male), MCV=81 (>=80 → not microcytic), RDW=14.6
        # Triggers: anisocytosis_with_microcytosis (RDW>14.5, MCV<82),
        # low_hb_with_low_normal_mcv (Hb<13 M, MCV<85) = 2.
        out = iron_deficiency_recommendation(
            _cbc(Hb=11.0, MCV=81.0, RBC=4.5, RDW=14.6, MCHC=33.0, Sex='M')
        )
        assert out['flag'] is True
        assert out['confidence'] == 'medium'
        assert len(out['reasoning']) == 2

    def test_insufficient_data_no_hb(self):
        cbc = _cbc()
        cbc['Hb'] = None
        out = iron_deficiency_recommendation(cbc)
        assert out['flag'] is False
        assert out['reasoning'] == ['insufficient_data']

    def test_insufficient_data_zero_rbc(self):
        # Mentzer would divide by zero → must short-circuit cleanly
        out = iron_deficiency_recommendation(_cbc(RBC=0.0))
        assert out['flag'] is False
        assert out['reasoning'] == ['insufficient_data']

    def test_non_numeric_value_treated_as_missing(self):
        out = iron_deficiency_recommendation(_cbc(Hb='nope'))
        assert out['flag'] is False
        assert out['reasoning'] == ['insufficient_data']


# ── Module 2: beta-thalassemia trait ──────────────────────────────────

class TestThalassemiaTrait:
    def test_not_microcytic_does_not_screen(self):
        out = thalassemia_trait_recommendation(_cbc(MCV=88.0))
        assert out['flag'] is False
        assert 'not_microcytic' in out['reasoning']

    def test_classic_btt_pattern_flags_high(self):
        # Microcytic + high RBC + low Mentzer + Shine-Lal low + uniform cells
        # MCV=70, RBC=5.5 → mentzer=12.7, shine_lal=70^2*22/100=1078 < 1530
        # RBC>=5.0 and MCV<78 → microcytic_high_rbc_btt_pattern
        # Hb 11, RDW 13 → microcytic_uniform_cells_btt_pattern
        out = thalassemia_trait_recommendation(
            _cbc(MCV=70.0, RBC=5.5, MCH=22.0, Hb=11.0, RDW=13.0)
        )
        assert out['flag'] is True
        assert out['confidence'] == 'high'
        assert 'mentzer_lt_13_btt_suspected' in out['reasoning']
        assert 'shine_lal_lt_1530_btt_suspected' in out['reasoning']
        assert 'microcytic_high_rbc_btt_pattern' in out['reasoning']
        assert 'microcytic_uniform_cells_btt_pattern' in out['reasoning']

    def test_microcytic_but_no_indicators(self):
        # MCV=78, RBC=3.5 → mentzer=22.3 (high, IDA-like), MCH=30 → shine_lal=70^2*30/100=4680 NO
        # MCV=78 means RBC<5 fails high_rbc test, RDW=16 fails uniform-cells
        out = thalassemia_trait_recommendation(
            _cbc(MCV=78.0, RBC=3.5, MCH=30.0, Hb=11.0, RDW=16.0)
        )
        assert out['flag'] is False
        assert out['reasoning'] == ['microcytic_but_no_btt_indicators']

    def test_mentzer_only_yields_low(self):
        # MCV=78, RBC=6.5 → mentzer=12.0
        # MCH=30 → shine_lal=78^2*30/100=1825 > 1530 NO
        # RBC>=5 + MCV<78? MCV=78 not <78 → microcytic_high_rbc fails
        # Hb 13 not <12 → uniform-cells fails
        # England-Fraser: 78 - 6.5 - 5*13 - 3.4 = 3.1 NOT <0
        out = thalassemia_trait_recommendation(
            _cbc(MCV=78.0, RBC=6.5, MCH=30.0, Hb=13.0, RDW=14.0)
        )
        assert out['flag'] is True
        assert out['confidence'] == 'low'
        assert out['reasoning'] == ['mentzer_lt_13_btt_suspected']

    def test_england_fraser_trigger(self):
        # MCV - RBC - 5*Hb - 3.4 < 0
        # MCV=70, RBC=5, Hb=15 → 70 - 5 - 75 - 3.4 = -13.4 < 0 ✓
        out = thalassemia_trait_recommendation(
            _cbc(MCV=70.0, RBC=5.0, MCH=22.0, Hb=15.0, RDW=14.5)
        )
        assert out['flag'] is True
        assert 'england_fraser_negative_btt_suspected' in out['reasoning']

    def test_recommendation_text(self):
        out = thalassemia_trait_recommendation(
            _cbc(MCV=70.0, RBC=5.5, MCH=22.0, Hb=11.0, RDW=13.0)
        )
        assert out['recommendation'] == (
            'Consider reflex Hb electrophoresis (HbA2 quantitation) testing'
        )

    def test_insufficient_data_no_mcv(self):
        out = thalassemia_trait_recommendation(_cbc(MCV=None))
        assert out['flag'] is False
        assert out['reasoning'] == ['insufficient_data']

    def test_insufficient_data_zero_rbc(self):
        out = thalassemia_trait_recommendation(_cbc(MCV=70.0, RBC=0.0))
        assert out['flag'] is False
        assert out['reasoning'] == ['insufficient_data']


# ── Module 3: macrocytic / megaloblastic ──────────────────────────────

class TestMacrocyticAnemia:
    def test_normocytic_does_not_flag(self):
        out = macrocytic_anemia_recommendation(_cbc(MCV=88.0))
        assert out['flag'] is False
        assert out['reasoning'] == []

    def test_classic_macrocytosis_alone(self):
        out = macrocytic_anemia_recommendation(_cbc(MCV=104.0))
        assert out['flag'] is True
        assert out['confidence'] == 'low'
        assert out['reasoning'] == ['macrocytic_mcv_gt_100']

    def test_borderline_macrocytic_with_anisocytosis(self):
        # MCV=97, RDW=15.5 → triggers borderline rule but not >100
        out = macrocytic_anemia_recommendation(
            _cbc(MCV=97.0, RDW=15.5, MCH=30.0)
        )
        assert out['flag'] is True
        assert 'borderline_macrocytic_with_anisocytosis' in out['reasoning']
        assert 'macrocytic_mcv_gt_100' not in out['reasoning']

    def test_hyperchromic_pattern(self):
        # MCV=98, MCH=33
        out = macrocytic_anemia_recommendation(
            _cbc(MCV=98.0, MCH=33.0, RDW=13.0)
        )
        assert out['flag'] is True
        assert 'macrocytic_hyperchromic_pattern' in out['reasoning']

    def test_megaloblastic_pancytopenia(self):
        # Anemic male (Hb<13), platelets<150, WBC<4, MCV>90
        out = macrocytic_anemia_recommendation(
            _cbc(MCV=95.0, Hb=11.0, Platelets=120.0, WBC=3.0, Sex='M', RDW=14.0, MCH=30.0)
        )
        assert out['flag'] is True
        assert 'possible_megaloblastic_pancytopenia' in out['reasoning']

    def test_two_rules_yields_high_confidence(self):
        # MCV=102 (>100) + MCH=33 + MCV>95 → hyperchromic + macrocytic_mcv_gt_100
        out = macrocytic_anemia_recommendation(_cbc(MCV=102.0, MCH=33.5, RDW=13.0))
        assert out['flag'] is True
        assert out['confidence'] == 'high'
        assert len(out['reasoning']) >= 2

    def test_recommendation_text(self):
        out = macrocytic_anemia_recommendation(_cbc(MCV=104.0))
        assert out['recommendation'] == (
            'Consider reflex serum vitamin B12 and folate testing'
        )

    def test_insufficient_data_no_mcv(self):
        out = macrocytic_anemia_recommendation(_cbc(MCV=None))
        assert out['flag'] is False
        assert out['reasoning'] == ['insufficient_data']


# ── Module 4: composite anemia subtype ────────────────────────────────

class TestAnemiaSubtype:
    def test_not_anemic_short_circuits(self):
        out = anemia_subtype_suspicion(_cbc(Hb=14.5, Sex='M'))
        assert out['anemic'] is False
        assert out['suspected_subtype'] is None

    def test_btt_signature(self):
        # Hb 9 + MCV 70 + RBC 5.5 + RDW 13 → classic BTT
        out = anemia_subtype_suspicion(
            _cbc(Hb=9.0, MCV=70.0, RBC=5.5, MCH=22.0, MCHC=32.0, RDW=13.0, Sex='F')
        )
        assert out['anemic'] is True
        assert out['suspected_subtype'] == 'beta_thalassemia_trait'

    def test_iron_deficiency_signature(self):
        # Hb 9 + MCV 75 + RBC 4.2 + RDW 16 → classic IDA, NOT BTT (Mentzer ~17.9)
        out = anemia_subtype_suspicion(
            _cbc(Hb=9.0, MCV=75.0, RBC=4.2, MCH=21.0, MCHC=30.0, RDW=16.0, Sex='F')
        )
        assert out['anemic'] is True
        assert out['suspected_subtype'] == 'iron_deficiency_anemia'

    def test_macrocytic_signature(self):
        # Anemic + MCV 105 + RDW 16 + MCH 33 → macrocytic + hyperchromic
        out = anemia_subtype_suspicion(
            _cbc(Hb=9.0, MCV=105.0, RBC=2.8, MCH=33.0, MCHC=33.0, RDW=16.0, Sex='F')
        )
        assert out['anemic'] is True
        assert out['suspected_subtype'] == 'megaloblastic_or_macrocytic'

    def test_anemic_unspecified_when_no_pattern(self):
        # Anemic but no rule fires medium/high → "unspecified"
        # Hb 11.5 (anemic male), MCV 88, RBC 4.0 → only low_hb_with_low_normal_mcv
        # BUT MCV=88 NOT <85, so even that doesn't fire. So iron has no flag at all.
        out = anemia_subtype_suspicion(
            _cbc(Hb=11.5, MCV=88.0, RBC=4.0, MCH=29.0, MCHC=33.0, RDW=13.0, Sex='M')
        )
        assert out['anemic'] is True
        assert out['suspected_subtype'] == 'unspecified'

    def test_mentzer_disambiguates_overlap(self):
        # Pattern that initially flags both IDA and BTT
        # MCV=70, RBC=5.5 → mentzer=12.7 < 13 → BTT wins, IDA dropped
        out = anemia_subtype_suspicion(
            _cbc(Hb=11.0, MCV=70.0, RBC=5.5, MCH=22.0, MCHC=31.0, RDW=15.0, Sex='F')
        )
        assert out['anemic'] is True
        # Either BTT picked or IDA picked — but never both retained as "all_suspicions"
        if 'all_suspicions' in out:
            subtypes = [s['subtype'] for s in out['all_suspicions']]
            assert not ('iron_deficiency_anemia' in subtypes
                        and 'beta_thalassemia_trait' in subtypes)

    def test_insufficient_data_no_hb(self):
        cbc = _cbc()
        cbc['Hb'] = None
        out = anemia_subtype_suspicion(cbc)
        assert out['anemic'] is None
        assert out['reasoning'] == ['insufficient_data']


# ── Composite entry point ─────────────────────────────────────────────

class TestAllClinicalRules:
    def test_returns_all_four_modules(self):
        out = all_clinical_rules(_cbc())
        assert set(out.keys()) == {
            'iron_deficiency', 'thalassemia_trait',
            'macrocytic_anemia', 'anemia_subtype',
        }

    def test_healthy_cbc_no_flags(self):
        out = all_clinical_rules(_cbc())
        assert out['iron_deficiency']['flag'] is False
        assert out['thalassemia_trait']['flag'] is False
        assert out['macrocytic_anemia']['flag'] is False
        assert out['anemia_subtype']['anemic'] is False

    def test_btt_signature_propagates(self):
        out = all_clinical_rules(
            _cbc(Hb=9.0, MCV=70.0, RBC=5.5, MCH=22.0, MCHC=32.0, RDW=13.0, Sex='F')
        )
        assert out['thalassemia_trait']['flag'] is True
        assert out['anemia_subtype']['suspected_subtype'] == 'beta_thalassemia_trait'

    def test_does_not_raise_on_garbage_input(self):
        # Empty CBC must yield insufficient_data across the board, never raise
        out = all_clinical_rules({})
        assert out['iron_deficiency']['reasoning'] == ['insufficient_data']
        assert out['thalassemia_trait']['reasoning'] == ['insufficient_data']
        assert out['macrocytic_anemia']['reasoning'] == ['insufficient_data']
        assert out['anemia_subtype']['reasoning'] == ['insufficient_data']

    def test_does_not_raise_on_none(self):
        # Defensive: dict-like object with all-None values
        cbc = {k: None for k in (
            'Hb', 'RBC', 'MCV', 'MCH', 'MCHC', 'RDW', 'WBC', 'Platelets',
        )}
        cbc['Sex'] = 'M'
        out = all_clinical_rules(cbc)
        assert all(out[m]['reasoning'] == ['insufficient_data']
                   for m in ('iron_deficiency', 'thalassemia_trait',
                             'macrocytic_anemia', 'anemia_subtype'))


# ── Isolation contract: rule output is purely a function of CBC ───────

class TestIsolation:
    """The rule modules must not depend on Django, the ML engine, or any
    shared state.  These tests pin the contract so a future refactor that
    introduces hidden coupling fails loudly."""

    def test_module_imports_no_django(self):
        # Reading the source file directly (no need to import Django).
        import inspect
        from apps.screening import clinical_rules

        src = inspect.getsource(clinical_rules)
        for forbidden in ('from django', 'import django',
                          'from apps.screening.ml_engine',
                          'from apps.screening.models'):
            assert forbidden not in src, (
                f'clinical_rules.py must not contain "{forbidden}" — '
                'see §A.6 isolation contract'
            )

    def test_pure_function_same_input_same_output(self):
        cbc = _cbc(Hb=9.0, MCV=70.0, RBC=5.5, MCH=22.0)
        a = all_clinical_rules(cbc)
        b = all_clinical_rules(cbc)
        assert a == b

    def test_input_dict_not_mutated(self):
        cbc = _cbc(Hb=9.0, MCV=70.0, RBC=5.5, MCH=22.0)
        snapshot = dict(cbc)
        all_clinical_rules(cbc)
        assert cbc == snapshot

"""Rule-based clinical workflow recommendations beyond B12.

Four published-index workflow modules — iron deficiency, beta-thalassemia
trait, macrocytic anemia/megaloblastic suspicion, and a composite anemia
subtype suspicion — each producing a workflow recommendation dict.

Hard isolation contract with the B12 ML pipeline:
  - Pure functions, deterministic, no imports from ml_engine /
    narrative_engine / models.
  - Take a CBC dict, return a result dict.  Never raise on missing keys —
    return ``{'flag': False, 'confidence': None, 'reasoning': ['insufficient_data']}``
    so callers can treat the rule output as advisory regardless of input
    quality.
  - All numeric thresholds are published hematology indices; per-index
    citations live in the Device Master File.
  - The composite tier sensitivity/specificity numbers are engineering
    plausibility estimates pending lab validation; per-index numbers are
    the only ones that should appear in regulatory documentation.

CBC dict keys this module reads:
  ``Hb`` (g/dL), ``RBC`` (10^6/μL), ``MCV`` (fL), ``MCH`` (pg),
  ``MCHC`` (g/dL), ``RDW`` (%), ``WBC`` (10^3/μL),
  ``Platelets`` (10^3/μL), ``Sex`` ('M'/'F'), ``Age`` (int).
"""

from __future__ import annotations

from typing import Any


_INSUFFICIENT_DATA: dict[str, Any] = {
    'flag': False,
    'confidence': None,
    'reasoning': ['insufficient_data'],
    'recommendation': None,
}


def _f(cbc: dict, key: str) -> float | None:
    """Coerce a CBC value to float, returning None on missing/non-numeric."""
    v = cbc.get(key)
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _sex(cbc: dict) -> str:
    raw = cbc.get('Sex') or cbc.get('sex') or ''
    return str(raw).strip().upper()


def _hb_anemia_threshold(sex: str) -> float:
    return 13.0 if sex == 'M' else 12.0


def _confidence_for(n_triggered: int) -> str:
    if n_triggered >= 3:
        return 'high'
    if n_triggered == 2:
        return 'medium'
    return 'low'


# ── Module 1: iron deficiency reflex testing ──────────────────────────

def iron_deficiency_recommendation(cbc: dict) -> dict[str, Any]:
    """Workflow recommendation for iron deficiency reflex testing.

    Triggers on a composite of microcytic-hypochromic indicators plus the
    Mentzer and Green-King indices applied within their published clinical
    domain.  Returns a dict with::

        {'flag': bool, 'confidence': 'high'|'medium'|'low'|None,
         'reasoning': list[str], 'recommendation': str|None}

    Two deliberate deviations from the handover-doc rule list:

    1. Mentzer and Green-King are *gated on microcytic profile*
       (``MCV < 80``).  Both are IDA-vs-BTT discrimination indices —
       outside microcytic patients they fire on healthy CBCs (e.g.,
       Green-King at MCV=88, RDW=13.2, Hb=14.5 = 70.5, which exceeds the
       65 threshold) and are clinically meaningless.

    2. Mentzer threshold direction in the IDA module is the published
       direction: ``MCV/RBC > 13`` favors IDA over BTT (IDA reduces both
       MCV and RBC; BTT reduces MCV alone, leaving the ratio low).  The
       handover-doc draft used ``< 13`` which is the BTT direction —
       belongs in :func:`thalassemia_trait_recommendation`, not here.
    """
    hb = _f(cbc, 'Hb')
    mcv = _f(cbc, 'MCV')
    mchc = _f(cbc, 'MCHC')
    rbc = _f(cbc, 'RBC')
    rdw = _f(cbc, 'RDW')
    sex = _sex(cbc)

    if hb is None or mcv is None or rbc is None or rbc == 0:
        return dict(_INSUFFICIENT_DATA)

    triggered: list[str] = []
    is_microcytic = mcv < 80

    if mchc is not None and hb < 12 and mcv < 80 and mchc < 32:
        triggered.append('microcytic_hypochromic_anemia')

    if is_microcytic:
        mentzer = mcv / rbc
        if mentzer > 13:
            triggered.append('mentzer_gt_13_ida_favored_over_btt')

    if is_microcytic and rdw is not None and hb > 0:
        green_king = (mcv * mcv * rdw) / (hb * 100.0)
        if green_king > 65:
            triggered.append('green_king_gt_65_ida_favored_over_btt')

    if rdw is not None and rdw > 14.5 and mcv < 82:
        triggered.append('anisocytosis_with_microcytosis')

    if hb < _hb_anemia_threshold(sex) and mcv < 85:
        triggered.append('low_hb_with_low_normal_mcv')

    if not triggered:
        return {
            'flag': False,
            'confidence': None,
            'reasoning': [],
            'recommendation': None,
        }

    return {
        'flag': True,
        'confidence': _confidence_for(len(triggered)),
        'reasoning': triggered,
        'recommendation': 'Consider reflex ferritin and iron studies testing',
    }


# ── Module 2: beta-thalassemia trait screening ────────────────────────

def thalassemia_trait_recommendation(cbc: dict) -> dict[str, Any]:
    """Workflow recommendation for beta-thalassemia trait reflex testing.

    Pre-filtered to microcytic patients (MCV < 80) — BTT in normocytic
    patients is rare and out of scope.  Composes Mentzer, Shine-Lal,
    England-Fraser, and BTT-pattern heuristics.
    """
    mcv = _f(cbc, 'MCV')
    rbc = _f(cbc, 'RBC')
    mch = _f(cbc, 'MCH')
    hb = _f(cbc, 'Hb')
    rdw = _f(cbc, 'RDW')

    if mcv is None or rbc is None or rbc == 0:
        return dict(_INSUFFICIENT_DATA)

    if mcv >= 80:
        return {
            'flag': False,
            'confidence': None,
            'reasoning': ['not_microcytic'],
            'recommendation': None,
        }

    triggered: list[str] = []

    mentzer = mcv / rbc
    if mentzer < 13:
        triggered.append('mentzer_lt_13_btt_suspected')

    if mch is not None:
        shine_lal = (mcv * mcv * mch) / 100.0
        if shine_lal < 1530:
            triggered.append('shine_lal_lt_1530_btt_suspected')

    if rbc >= 5.0 and mcv < 78:
        triggered.append('microcytic_high_rbc_btt_pattern')

    if hb is not None and rdw is not None and hb < 12 and rdw < 14 and mcv < 80:
        triggered.append('microcytic_uniform_cells_btt_pattern')

    if hb is not None:
        england_fraser = mcv - rbc - 5 * hb - 3.4
        if england_fraser < 0:
            triggered.append('england_fraser_negative_btt_suspected')

    if not triggered:
        return {
            'flag': False,
            'confidence': None,
            'reasoning': ['microcytic_but_no_btt_indicators'],
            'recommendation': None,
        }

    return {
        'flag': True,
        'confidence': _confidence_for(len(triggered)),
        'reasoning': triggered,
        'recommendation': 'Consider reflex Hb electrophoresis (HbA2 quantitation) testing',
    }


# ── Module 3: macrocytic anemia / megaloblastic suspicion ─────────────

def macrocytic_anemia_recommendation(cbc: dict) -> dict[str, Any]:
    """Workflow recommendation for macrocytic-pattern reflex testing.

    Sensitivity for Indian B12 deficiency is poor (~15%) per the v3 cohort
    analysis — this rule is an *adjunct* to the B12 ML classifier, not a
    replacement.  Use it for clinically obvious macrocytic patients.
    """
    mcv = _f(cbc, 'MCV')
    rdw = _f(cbc, 'RDW')
    mch = _f(cbc, 'MCH')
    hb = _f(cbc, 'Hb')
    plt = _f(cbc, 'Platelets')
    wbc = _f(cbc, 'WBC')
    sex = _sex(cbc)

    if mcv is None:
        return dict(_INSUFFICIENT_DATA)

    triggered: list[str] = []

    if mcv > 100:
        triggered.append('macrocytic_mcv_gt_100')

    if rdw is not None and mcv > 95 and rdw > 14.5:
        triggered.append('borderline_macrocytic_with_anisocytosis')

    if mch is not None and mcv > 95 and mch > 32:
        triggered.append('macrocytic_hyperchromic_pattern')

    if (hb is not None and plt is not None and wbc is not None
            and hb < _hb_anemia_threshold(sex)
            and plt < 150 and wbc < 4 and mcv > 90):
        triggered.append('possible_megaloblastic_pancytopenia')

    if not triggered:
        return {
            'flag': False,
            'confidence': None,
            'reasoning': [],
            'recommendation': None,
        }

    confidence = 'high' if len(triggered) >= 2 else 'low'
    return {
        'flag': True,
        'confidence': confidence,
        'reasoning': triggered,
        'recommendation': 'Consider reflex serum vitamin B12 and folate testing',
    }


# ── Module 4: composite anemia-subtype suspicion ──────────────────────

_CONFIDENCE_RANK = {'high': 0, 'medium': 1, 'low': 2}


def anemia_subtype_suspicion(cbc: dict) -> dict[str, Any]:
    """One-shot subtype suspicion when the patient is anemic.

    Composes the iron / thalassemia / macrocytic modules and disambiguates
    overlapping IDA-vs-BTT cases via the Mentzer index.  Non-anemic
    patients return ``{'anemic': False}`` so callers can short-circuit
    cleanly.
    """
    hb = _f(cbc, 'Hb')
    if hb is None:
        return {
            'anemic': None,
            'suspected_subtype': None,
            'reasoning': ['insufficient_data'],
            'recommendation': None,
        }

    sex = _sex(cbc)
    if hb >= _hb_anemia_threshold(sex):
        return {
            'anemic': False,
            'suspected_subtype': None,
            'reasoning': [],
            'recommendation': None,
        }

    iron = iron_deficiency_recommendation(cbc)
    thal = thalassemia_trait_recommendation(cbc)
    macro = macrocytic_anemia_recommendation(cbc)

    suspected: list[tuple[str, str]] = []
    if iron['flag'] and iron['confidence'] in ('medium', 'high'):
        suspected.append(('iron_deficiency_anemia', iron['confidence']))
    if thal['flag'] and thal['confidence'] in ('medium', 'high'):
        suspected.append(('beta_thalassemia_trait', thal['confidence']))
    if macro['flag']:
        suspected.append(('megaloblastic_or_macrocytic', macro['confidence'] or 'low'))

    iron_flag = any(s[0] == 'iron_deficiency_anemia' for s in suspected)
    btt_flag = any(s[0] == 'beta_thalassemia_trait' for s in suspected)
    if iron_flag and btt_flag:
        rbc = _f(cbc, 'RBC')
        mcv = _f(cbc, 'MCV')
        if rbc and mcv and rbc > 0:
            mentzer = mcv / rbc
            if mentzer < 13:
                suspected = [s for s in suspected if s[0] != 'iron_deficiency_anemia']
            else:
                suspected = [s for s in suspected if s[0] != 'beta_thalassemia_trait']

    if not suspected:
        return {
            'anemic': True,
            'suspected_subtype': 'unspecified',
            'reasoning': [],
            'recommendation': (
                'Anemic profile, no specific subtype pattern identified. '
                'Consider full anemia workup.'
            ),
        }

    suspected.sort(key=lambda s: _CONFIDENCE_RANK.get(s[1], 99))
    primary = suspected[0][0]
    return {
        'anemic': True,
        'suspected_subtype': primary,
        'all_suspicions': [
            {'subtype': name, 'confidence': conf}
            for name, conf in suspected
        ],
        'recommendation': f'Anemia profile suggests {primary}; reflex testing recommended.',
    }


# ── Composite entry point used by the screening API ────────────────────

def all_clinical_rules(cbc: dict) -> dict[str, dict[str, Any]]:
    """Run every rule module on a CBC dict and return a single bundle.

    Wrapped in a try/except per-module so a bug in one rule cannot break
    the screening response — each rule degrades to insufficient_data.
    """
    out: dict[str, dict[str, Any]] = {}
    for name, fn in (
        ('iron_deficiency', iron_deficiency_recommendation),
        ('thalassemia_trait', thalassemia_trait_recommendation),
        ('macrocytic_anemia', macrocytic_anemia_recommendation),
        ('anemia_subtype', anemia_subtype_suspicion),
    ):
        try:
            out[name] = fn(cbc)
        except Exception:  # noqa: BLE001
            out[name] = dict(_INSUFFICIENT_DATA)
    return out

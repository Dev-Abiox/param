"""
Template-based clinical narrative engine for B12 screening results.

Generates human-readable clinical interpretations from screening results
using clinical indices, confidence levels, and parameterized sentence
fragments. No external API calls — purely deterministic.

v2: Driven by clinical_indices (mentzer, green_king, nlr), p_stage1,
    and confidence instead of rule_score / rulesFired.
"""

import logging

logger = logging.getLogger(__name__)


# ── Templates ─────────────────────────────────────────────────────────────────

TEMPLATES = {
    'macrocytic_high_risk': (
        "This patient presents with macrocytic indices (MCV {mcv} fL) alongside "
        "{findings_summary}. The screening model classifies this as {label_text} "
        "with {deficient_pct}% probability of B12 deficiency. "
        "{confidence_fragment}"
        "{trend_fragment}"
        "Given the macrocytic picture, serum B12 and "
        "methylmalonic acid measurements are strongly recommended."
    ),
    'borderline_elderly': (
        "In this {age_group} patient ({age}y, {sex}), the CBC shows borderline "
        "features: {findings_summary}. Model confidence for deficiency is "
        "{deficient_pct}%, placing the patient in the Borderline category. "
        "{confidence_fragment}"
        "{trend_fragment}"
        "Age-related absorption decline should be considered. "
        "Serum B12 measurement is advisable."
    ),
    'normal_young': (
        "CBC parameters for this {age_group} patient ({age}y, {sex}) are within "
        "normal limits. No macrocytosis, preserved cell counts, and a Mentzer "
        "index of {mentzer} suggest no B12 deficiency. Model confidence for "
        "normal is {normal_pct}%. {trend_fragment}"
        "No further B12 workup indicated at this time."
    ),
    'deficient_with_trend': (
        "This screening identifies {label_text} risk (model probability "
        "{deficient_pct}%). Clinical findings include {findings_summary}. "
        "{confidence_fragment}"
        "{trend_fragment}"
        "The pattern warrants urgent serum B12 measurement and possible "
        "empiric supplementation pending results."
    ),
    'borderline_low_mcv': (
        "Despite borderline model classification ({borderline_pct}% probability), "
        "the MCV of {mcv} fL is low rather than elevated. This pattern is "
        "atypical for isolated B12 deficiency and may indicate concurrent "
        "iron deficiency or thalassemia trait. "
        "{confidence_fragment}"
        "{trend_fragment}"
        "Consider iron studies alongside B12 measurement."
    ),
    'borderline_megaloblastic': (
        "The screening model classifies this result as {label_text} with "
        "{borderline_pct}% probability. The elevated Mentzer index ({mentzer}) "
        "suggests megaloblastic tendency, which may indicate early B12 depletion. "
        "{confidence_fragment}"
        "{trend_fragment}"
        "Serum B12 measurement is recommended to clarify the clinical picture."
    ),
    'low_confidence': (
        "The screening model classifies this result as {label_text}. However, "
        "classification confidence is low (p_stage1={p_stage1}), and the result "
        "falls within the model's uncertain zone. "
        "{findings_summary_sentence}"
        "{trend_fragment}"
        "Confirmatory serum B12 testing is recommended regardless of the "
        "screening classification."
    ),
    'iron_deficiency_pattern': (
        "The CBC pattern (MCV {mcv} fL, MCH {mch} pg) is consistent with "
        "microcytic hypochromic anemia, suggesting iron deficiency rather than "
        "B12 deficiency. The screening model classifies this as {label_text}. "
        "{confidence_fragment}"
        "{trend_fragment}"
        "Iron studies are recommended. B12 deficiency is less likely in this context."
    ),
    # Fallback templates
    'deficient_default': (
        "The screening model classifies this result as {label_text} with "
        "{deficient_pct}% probability of deficiency. {findings_summary_sentence}"
        "{confidence_fragment}"
        "{trend_fragment}"
        "Serum B12 measurement is recommended."
    ),
    'borderline_default': (
        "The screening model classifies this result as {label_text} with "
        "{borderline_pct}% probability of borderline status. "
        "{findings_summary_sentence}"
        "{confidence_fragment}"
        "{trend_fragment}"
        "Consider serum B12 measurement if clinically indicated."
    ),
    'normal_default': (
        "The screening model classifies this result as {label_text} with "
        "{normal_pct}% probability of normal status. "
        "{findings_summary_sentence}"
        "{confidence_fragment}"
        "{trend_fragment}"
        "B12 deficiency is unlikely based on CBC parameters."
    ),
}


# ── Differential Diagnosis Lookup ─────────────────────────────────────────────

DIFFERENTIAL_TABLE = {
    'macrocytosis': [
        'Vitamin B12 deficiency',
        'Folate deficiency',
        'Myelodysplastic syndrome',
        'Liver disease',
        'Hypothyroidism',
    ],
    'severe_macrocytosis': [
        'Vitamin B12 deficiency',
        'Folate deficiency',
        'Myelodysplastic syndrome',
    ],
    'high_rdw_macrocytic': [
        'Combined deficiency (B12 + iron)',
        'Early B12 deficiency',
        'Chronic disease',
    ],
    'pancytopenia': [
        'Severe B12 deficiency',
        'Aplastic anemia',
        'Myelodysplastic syndrome',
        'Bone marrow infiltration',
    ],
    'megaloblastic': [
        'B12 deficiency',
        'Folate deficiency',
        'Myelodysplastic syndrome',
    ],
    'iron_deficiency_pattern': [
        'Iron deficiency anemia',
        'Thalassemia trait',
        'Anemia of chronic disease',
        'Sideroblastic anemia',
    ],
}


class NarrativeEngine:
    """
    Template-based clinical narrative generator.

    v2: Uses clinical_indices and confidence from the new two-stage engine
    instead of rulesFired from the old rule-based system.
    """

    AGE_GROUPS = {
        'pediatric': (0, 17),
        'young_adult': (18, 39),
        'middle_aged': (40, 59),
        'elderly': (60, 200),
    }

    def classify_age_group(self, age: int) -> str:
        for group, (lo, hi) in self.AGE_GROUPS.items():
            if lo <= age <= hi:
                return group
        return 'middle_aged'

    def _derive_clinical_findings(self, cbc_snapshot: dict, indices: dict) -> list[str]:
        """
        Derive clinical finding labels from CBC values and indices.
        Replaces the old rulesFired with index-driven findings.
        """
        findings = []
        mcv = cbc_snapshot.get('MCV', 0) or 0
        mch = cbc_snapshot.get('MCH', 0) or 0
        mchc = cbc_snapshot.get('MCHC', 0) or 0
        rdw = cbc_snapshot.get('RDW', 0) or 0
        hb = cbc_snapshot.get('Hb', 0) or 0
        wbc = cbc_snapshot.get('WBC', 0) or 0
        platelets = cbc_snapshot.get('Platelets', 0) or 0
        mentzer = indices.get('mentzer', 0)
        green_king = indices.get('green_king', 0) or indices.get('greenKing', 0)

        if mcv > 115:
            findings.append('severe macrocytosis (MCV > 115)')
        elif mcv > 100:
            findings.append('macrocytosis (MCV > 100)')

        if rdw > 15 and mcv >= 95:
            findings.append('elevated RDW in macrocytic context')
        elif rdw > 15:
            findings.append('elevated RDW')

        if hb < 12 and wbc < 4 and platelets < 150:
            findings.append('pancytopenia')

        if mentzer > 20:
            findings.append(f'elevated Mentzer index ({mentzer})')
        elif mentzer > 13 and mcv >= 95:
            findings.append(f'Mentzer index {mentzer} suggesting megaloblastic tendency')

        if green_king > 100:
            findings.append(f'elevated Green-King index ({green_king})')

        # Iron deficiency pattern
        if 0 < mcv < 80 and 0 < mch < 27 and 0 < mchc < 32:
            findings.append('microcytic hypochromic pattern (iron deficiency)')
        elif 0 < mcv < 90 and ((0 < mch < 27) or (0 < mchc < 32)):
            findings.append('mildly microcytic/hypochromic pattern')

        return findings

    def _get_clinical_flags(self, cbc_snapshot: dict, indices: dict) -> dict:
        """Compute boolean clinical flags from CBC and indices."""
        mcv = cbc_snapshot.get('MCV', 0) or 0
        mch = cbc_snapshot.get('MCH', 0) or 0
        mchc = cbc_snapshot.get('MCHC', 0) or 0
        rdw = cbc_snapshot.get('RDW', 0) or 0
        hb = cbc_snapshot.get('Hb', 0) or 0
        wbc = cbc_snapshot.get('WBC', 0) or 0
        platelets = cbc_snapshot.get('Platelets', 0) or 0
        mentzer = indices.get('mentzer', 0)
        green_king = indices.get('green_king', 0) or indices.get('greenKing', 0)

        return {
            'has_macrocytosis': mcv > 100,
            'has_severe_macrocytosis': mcv > 115,
            'has_high_rdw_macro': rdw > 15 and mcv >= 95,
            'has_pancytopenia': hb < 12 and wbc < 4 and platelets < 150,
            'has_megaloblastic_tendency': mentzer > 20 or (mentzer > 13 and mcv >= 95),
            'has_high_green_king': green_king > 100,
            'has_iron_def_pattern': (
                0 < mcv < 90
                and ((0 < mch < 27) or (0 < mchc < 32))
            ),
            'has_strong_iron_def': (
                0 < mcv < 80 and 0 < mch < 27 and 0 < mchc < 32
            ),
        }

    def select_template_key(
        self,
        risk_class: int,
        age_group: str,
        sex: str,
        cbc_snapshot: dict,
        indices: dict,
        confidence: str = 'moderate',
    ) -> str:
        """
        Determine which template to use based on clinical context.
        Uses clinical indices and CBC values instead of rulesFired.
        """
        flags = self._get_clinical_flags(cbc_snapshot, indices)

        # Low confidence → always recommend confirmatory testing
        if confidence == 'low':
            return 'low_confidence'

        # Iron deficiency pattern overrides
        if flags['has_strong_iron_def']:
            return 'iron_deficiency_pattern'

        if risk_class == 3 and flags['has_macrocytosis']:
            return 'macrocytic_high_risk'
        if risk_class == 2 and age_group == 'elderly':
            return 'borderline_elderly'
        if risk_class == 1 and age_group in ('young_adult', 'pediatric'):
            return 'normal_young'
        if risk_class == 3:
            return 'deficient_with_trend'
        if risk_class == 2 and flags['has_megaloblastic_tendency']:
            return 'borderline_megaloblastic'
        if risk_class == 2 and not flags['has_macrocytosis']:
            mcv = cbc_snapshot.get('MCV', 0) or 0
            if mcv < 95:
                return 'borderline_low_mcv'

        # Fallbacks by risk class
        if risk_class == 3:
            return 'deficient_default'
        if risk_class == 2:
            return 'borderline_default'
        return 'normal_default'

    def build_trend_fragment(self, patient_id: str, current_risk_class: int) -> str:
        """
        Generate a sentence fragment describing trend from historical screenings.
        """
        from apps.screening.models import Screening

        risk_trajectory = list(
            Screening.objects
            .filter(patient__patient_id=patient_id)
            .order_by('-created_at')
            .values_list('risk_class', flat=True)[:5]
        )

        if not risk_trajectory:
            return ''

        if all(r < current_risk_class for r in risk_trajectory):
            return 'This represents a worsening trend compared to prior screenings. '
        elif all(r > current_risk_class for r in risk_trajectory):
            return 'This represents an improving trend compared to prior screenings. '
        elif all(r == current_risk_class for r in risk_trajectory):
            return 'Risk classification remains stable across recent screenings. '
        else:
            return (
                f'Risk classification has fluctuated across the last '
                f'{len(risk_trajectory)} screenings. '
            )

    def _build_confidence_fragment(self, confidence: str) -> str:
        """Build a sentence fragment about classification confidence."""
        if confidence == 'high':
            return 'Classification confidence is high. '
        elif confidence == 'moderate':
            return 'Classification confidence is moderate. '
        else:
            return 'Classification confidence is low — confirmatory serum B12 testing recommended. '

    def get_differential_suggestions(
        self,
        risk_class: int,
        cbc_snapshot: dict,
        indices: dict,
    ) -> list[str]:
        """
        Lookup table for differential diagnosis suggestions.
        Driven by clinical indices and CBC values instead of rulesFired.
        """
        flags = self._get_clinical_flags(cbc_snapshot, indices)
        seen = set()
        result = []

        def _add(key):
            for dx in DIFFERENTIAL_TABLE.get(key, []):
                if dx not in seen:
                    seen.add(dx)
                    result.append(dx)

        if flags['has_severe_macrocytosis']:
            _add('severe_macrocytosis')
        elif flags['has_macrocytosis']:
            _add('macrocytosis')

        if flags['has_high_rdw_macro']:
            _add('high_rdw_macrocytic')

        if flags['has_pancytopenia']:
            _add('pancytopenia')

        if flags['has_megaloblastic_tendency']:
            _add('megaloblastic')

        if flags['has_iron_def_pattern']:
            _add('iron_deficiency_pattern')

        if not result and risk_class >= 2:
            result.append('Subclinical B12 deficiency')

        return result

    def generate(
        self,
        risk_class: int,
        label_text: str,
        probabilities: dict,
        rules_fired: list[str],
        indices: dict,
        cbc_snapshot: dict,
        age: int,
        sex: str,
        patient_id: str | None = None,
        confidence: str = 'moderate',
        p_stage1: float | None = None,
        clinical_indices: dict | None = None,
    ) -> str:
        """
        Main entry point. Returns a multi-paragraph clinical narrative string.

        Args:
            risk_class: 1/2/3
            label_text: NORMAL/BORDERLINE/DEFICIENT
            probabilities: {normal, borderline, deficient}
            rules_fired: Legacy field (ignored in v2, kept for API compat)
            indices: {mentzer, greenKing, nlr, pancytopenia, shap_values}
            cbc_snapshot: Raw CBC values
            age: Patient age
            sex: M/F
            patient_id: For trend analysis
            confidence: "high"/"moderate"/"low" from v2 engine
            p_stage1: Raw deficiency probability from v2 engine
            clinical_indices: {mentzer, green_king, nlr} from v2 engine
        """
        age_group = self.classify_age_group(age)

        # Merge clinical_indices into indices for unified access
        effective_indices = dict(indices or {})
        if clinical_indices:
            effective_indices.update(clinical_indices)

        # Derive clinical findings from CBC + indices
        findings = self._derive_clinical_findings(cbc_snapshot, effective_indices)

        template_key = self.select_template_key(
            risk_class, age_group, sex, cbc_snapshot, effective_indices,
            confidence=confidence,
        )

        # Build trend fragment
        trend_fragment = ''
        if patient_id:
            try:
                trend_fragment = self.build_trend_fragment(patient_id, risk_class)
            except Exception as e:
                logger.warning("Trend analysis failed: %s", e)

        # If template expects trend but none available, swap to default
        if template_key == 'deficient_with_trend' and not trend_fragment:
            template_key = 'deficient_default'

        # Prepare template parameters
        findings_summary = ', '.join(findings) if findings else 'no significant CBC abnormalities'
        findings_summary_sentence = (
            f'Clinical findings include {findings_summary}. ' if findings
            else ''
        )
        sex_display = 'Male' if sex in ('M', 'm') else 'Female'
        confidence_fragment = self._build_confidence_fragment(confidence)

        params = {
            'mcv': cbc_snapshot.get('MCV', 'N/A'),
            'mch': cbc_snapshot.get('MCH', 'N/A'),
            'findings_summary': findings_summary,
            'findings_summary_sentence': findings_summary_sentence,
            'label_text': label_text,
            'deficient_pct': round(probabilities.get('deficient', 0) * 100, 1),
            'borderline_pct': round(probabilities.get('borderline', 0) * 100, 1),
            'normal_pct': round(probabilities.get('normal', 0) * 100, 1),
            'trend_fragment': trend_fragment,
            'confidence_fragment': confidence_fragment,
            'age_group': age_group.replace('_', ' '),
            'age': age,
            'sex': sex_display,
            'mentzer': effective_indices.get('mentzer', 'N/A'),
            'p_stage1': round(p_stage1, 4) if p_stage1 is not None else 'N/A',
        }

        template = TEMPLATES.get(template_key, TEMPLATES['normal_default'])
        narrative = template.format(**params)

        # Append differential considerations
        differentials = self.get_differential_suggestions(
            risk_class, cbc_snapshot, effective_indices,
        )
        if differentials:
            dx_list = '; '.join(differentials)
            narrative += (
                f'\n\nDifferential considerations: {dx_list}.'
            )

        return narrative

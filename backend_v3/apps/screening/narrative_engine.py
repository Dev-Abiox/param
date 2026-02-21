"""
Template-based clinical narrative engine for B12 screening results.

Generates human-readable clinical interpretations from screening results
using rule-driven template selection and parameterized sentence fragments.
No external API calls — purely deterministic.
"""

import logging

logger = logging.getLogger(__name__)


# ── Templates ─────────────────────────────────────────────────────────────────

TEMPLATES = {
    'macrocytic_high_risk': (
        "This patient presents with macrocytic indices (MCV {mcv} fL) alongside "
        "{rules_summary}. The screening model classifies this as {label_text} "
        "with {deficient_pct}% probability of B12 deficiency. "
        "{trend_fragment}"
        "Given the macrocytic picture with elevated RDW, serum B12 and "
        "methylmalonic acid measurements are strongly recommended."
    ),
    'borderline_elderly': (
        "In this {age_group} patient ({age}y, {sex}), the CBC shows borderline "
        "features: {rules_summary}. Model confidence for deficiency is "
        "{deficient_pct}%, placing the patient in the Borderline category. "
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
        "{deficient_pct}%). Clinical findings include {rules_summary}. "
        "{trend_fragment}"
        "The pattern warrants urgent serum B12 measurement and possible "
        "empiric supplementation pending results."
    ),
    'borderline_low_mcv': (
        "Despite borderline model classification ({borderline_pct}% probability), "
        "the MCV of {mcv} fL is low rather than elevated. This pattern is "
        "atypical for isolated B12 deficiency and may indicate concurrent "
        "iron deficiency or thalassemia trait. "
        "{trend_fragment}"
        "Consider iron studies alongside B12 measurement."
    ),
    # Fallback templates
    'deficient_default': (
        "The screening model classifies this result as {label_text} with "
        "{deficient_pct}% probability of deficiency. Clinical findings include "
        "{rules_summary}. {trend_fragment}"
        "Serum B12 measurement is recommended."
    ),
    'borderline_default': (
        "The screening model classifies this result as {label_text} with "
        "{borderline_pct}% probability of borderline status. "
        "Clinical findings include {rules_summary}. "
        "{trend_fragment}"
        "Consider serum B12 measurement if clinically indicated."
    ),
    'normal_default': (
        "The screening model classifies this result as {label_text} with "
        "{normal_pct}% probability of normal status. "
        "Clinical findings: {rules_summary}. "
        "{trend_fragment}"
        "B12 deficiency is unlikely based on CBC parameters."
    ),
}


# ── Differential Diagnosis Lookup ─────────────────────────────────────────────

DIFFERENTIAL_TABLE = {
    'Macrocytosis': [
        'Vitamin B12 deficiency',
        'Folate deficiency',
        'Myelodysplastic syndrome',
        'Liver disease',
        'Hypothyroidism',
    ],
    'High RDW': [
        'Combined deficiency (B12 + iron)',
        'Early B12 deficiency',
        'Chronic disease',
    ],
    'Pancytopenia': [
        'Severe B12 deficiency',
        'Aplastic anemia',
        'Myelodysplastic syndrome',
        'Bone marrow infiltration',
    ],
    'Ineffective erythropoiesis': [
        'B12 deficiency',
        'Thalassemia trait',
        'Iron deficiency anemia',
    ],
}


class NarrativeEngine:
    """
    Template-based clinical narrative generator.

    Generates human-readable clinical interpretations from screening
    results using rule-driven template selection and parameterized
    sentence fragments. No external API calls.
    """

    AGE_GROUPS = {
        'pediatric': (0, 17),
        'young_adult': (18, 39),
        'middle_aged': (40, 59),
        'elderly': (60, 200),
    }

    def classify_age_group(self, age: int) -> str:
        """Map numeric age to age group string."""
        for group, (lo, hi) in self.AGE_GROUPS.items():
            if lo <= age <= hi:
                return group
        return 'middle_aged'

    def select_template_key(
        self,
        risk_class: int,
        age_group: str,
        sex: str,
        rules_fired: list[str],
    ) -> str:
        """
        Determine which template to use based on clinical context.

        Returns one of the template keys defined in TEMPLATES.
        """
        has_macrocytosis = 'Macrocytosis' in rules_fired

        if risk_class == 3 and has_macrocytosis:
            return 'macrocytic_high_risk'
        if risk_class == 2 and age_group == 'elderly':
            return 'borderline_elderly'
        if risk_class == 1 and age_group in ('young_adult', 'pediatric'):
            return 'normal_young'
        if risk_class == 3:
            return 'deficient_with_trend'
        if risk_class == 2 and not has_macrocytosis:
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

        Queries the most recent 5 Screening records for the patient
        (excluding the current one), compares risk trajectory.
        Returns empty string if no history exists.
        """
        from apps.screening.models import Patient, Screening

        try:
            patient = Patient.objects.get(patient_id=patient_id)
        except Patient.DoesNotExist:
            return ''

        # Narrative is generated before the current screening is persisted,
        # so all results here are genuine historical records.
        history = list(
            Screening.objects
            .filter(patient=patient)
            .order_by('-created_at')[:5]
        )

        if not history:
            return ''

        risk_trajectory = [s.risk_class for s in history]

        if all(r < current_risk_class for r in risk_trajectory):
            return 'This represents a worsening trend compared to prior screenings. '
        elif all(r > current_risk_class for r in risk_trajectory):
            return 'This represents an improving trend compared to prior screenings. '
        elif all(r == current_risk_class for r in risk_trajectory):
            return 'Risk classification remains stable across recent screenings. '
        else:
            return (
                f'Risk classification has fluctuated across the last '
                f'{len(history)} screenings. '
            )

    def get_differential_suggestions(
        self,
        risk_class: int,
        rules_fired: list[str],
        indices: dict,
    ) -> list[str]:
        """
        Lookup table for differential diagnosis suggestions.

        Based on rules_fired and index values, return a deduplicated list of
        differential considerations.
        """
        seen = set()
        result = []

        for rule in rules_fired:
            for dx in DIFFERENTIAL_TABLE.get(rule, []):
                if dx not in seen:
                    seen.add(dx)
                    result.append(dx)

        # Add index-based differentials
        mentzer = indices.get('mentzer', 0)
        if mentzer and mentzer > 13 and 'Iron deficiency anemia' not in seen:
            result.append('Iron deficiency anemia')
            seen.add('Iron deficiency anemia')

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
    ) -> str:
        """
        Main entry point. Returns a multi-paragraph clinical narrative string.

        Structure:
        1. Main template paragraph (classification + findings + trend)
        2. Differential considerations paragraph (if any)
        """
        age_group = self.classify_age_group(age)

        template_key = self.select_template_key(
            risk_class, age_group, sex, rules_fired,
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
        rules_summary = ', '.join(rules_fired) if rules_fired else 'no significant clinical rules triggered'
        sex_display = 'Male' if sex in ('M', 'm') else 'Female'

        params = {
            'mcv': cbc_snapshot.get('MCV', 'N/A'),
            'rules_summary': rules_summary,
            'label_text': label_text,
            'deficient_pct': round(probabilities.get('deficient', 0) * 100, 1),
            'borderline_pct': round(probabilities.get('borderline', 0) * 100, 1),
            'normal_pct': round(probabilities.get('normal', 0) * 100, 1),
            'trend_fragment': trend_fragment,
            'age_group': age_group.replace('_', ' '),
            'age': age,
            'sex': sex_display,
            'mentzer': indices.get('mentzer', 'N/A'),
        }

        template = TEMPLATES.get(template_key, TEMPLATES['normal_default'])
        narrative = template.format(**params)

        # Append differential considerations
        differentials = self.get_differential_suggestions(
            risk_class, rules_fired, indices,
        )
        if differentials:
            dx_list = '; '.join(differentials)
            narrative += (
                f'\n\nDifferential considerations: {dx_list}.'
            )

        return narrative

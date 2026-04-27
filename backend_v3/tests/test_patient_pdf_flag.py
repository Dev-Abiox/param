"""Patient PDF Disclosure Spec — Option A flag tests.

These are DB-free declaration tests — they verify the field exists on
the Lab model with the expected default and that the
ScreeningSerializer surfaces it under the right key.  Behavioural tests
that need a real Lab row + a Screening + an HTTP request live in the
DB-backed integration suite (Postgres-only) and run in CI.
"""

from __future__ import annotations

import pytest


class TestLabFieldDeclaration:
    def test_field_exists_with_default_false(self):
        from apps.screening.models import Lab

        field = Lab._meta.get_field('patient_pdf_workflow_recs_enabled')
        assert field.default is False
        assert field.get_internal_type() == 'BooleanField'

    def test_field_help_text_mentions_default_off(self):
        from apps.screening.models import Lab

        field = Lab._meta.get_field('patient_pdf_workflow_recs_enabled')
        # Catch a future refactor that drops the off-by-default
        # rationale from the field — that's the contract counsel is
        # signing off on, so it stays load-bearing.
        assert 'default' in field.help_text.lower()


class TestScreeningSerializerField:
    def test_serializer_declares_lab_workflow_recs_enabled(self):
        from apps.screening.serializers import ScreeningSerializer

        # The field is a SerializerMethodField, so it lives on the
        # serializer class, not the model.
        fields = ScreeningSerializer.Meta.fields
        assert 'lab_workflow_recs_enabled' in fields

    def test_serializer_method_handles_missing_lab(self):
        from apps.screening.serializers import ScreeningSerializer

        # A Screening with no Lab attached must serialise to False
        # (fail-closed) rather than raising.  We don't need a DB to
        # exercise this — the method is pure conditional logic.
        ser = ScreeningSerializer.__new__(ScreeningSerializer)

        class _Stub:
            lab = None

        assert ser.get_lab_workflow_recs_enabled(_Stub()) is False

    def test_serializer_method_returns_lab_flag_value(self):
        from apps.screening.serializers import ScreeningSerializer

        ser = ScreeningSerializer.__new__(ScreeningSerializer)

        class _LabStub:
            patient_pdf_workflow_recs_enabled = True

        class _ScreeningStub:
            lab = _LabStub()

        assert ser.get_lab_workflow_recs_enabled(_ScreeningStub()) is True

        class _LabStubOff:
            patient_pdf_workflow_recs_enabled = False

        class _ScreeningStubOff:
            lab = _LabStubOff()

        assert ser.get_lab_workflow_recs_enabled(_ScreeningStubOff()) is False


class TestMigrationPresence:
    def test_option_a_migration_file_exists(self):
        # If somebody renames or deletes the migration without thinking
        # about Option A, this test fails loudly.  The presence of the
        # file is the audit trail.
        import importlib

        mod = importlib.import_module(
            'apps.screening.migrations.0013_lab_patient_pdf_workflow_recs',
        )
        assert hasattr(mod, 'Migration')
        ops = mod.Migration.operations
        assert len(ops) == 1
        assert ops[0].name == 'patient_pdf_workflow_recs_enabled'
        assert ops[0].field.default is False


class TestClinicalRulesIsolation:
    """The §A.6 contract holds — clinical_rules.py still has zero
    knowledge of the patient-PDF flag."""

    def test_clinical_rules_module_does_not_reference_flag(self):
        import inspect
        from apps.screening import clinical_rules

        src = inspect.getsource(clinical_rules)
        for forbidden in (
            'patient_pdf_workflow_recs',
            'labWorkflowRecsEnabled',
            'lab_workflow_recs_enabled',
        ):
            assert forbidden not in src, (
                f'clinical_rules.py must not reference "{forbidden}" — '
                'that flag is purely a presentation-layer gate, not part '
                'of the rule logic.'
            )

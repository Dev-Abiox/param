"""
Tests for the audit-log PHI sanitiser (P1-10).
"""

from apps.core.audit import FREE_TEXT_MAX_LEN, sanitise_details


class TestSanitiseDetails:
    def test_empty_input_returns_empty_dict(self):
        assert sanitise_details(None) == {}
        assert sanitise_details({}) == {}

    def test_non_phi_keys_pass_through(self):
        details = {
            'screening_id': 'abc-123',
            'risk_class': 3,
            'model_version': 'v1.2.3',
            'records_returned': 42,
            'has_consent': True,
        }
        out = sanitise_details(details)
        assert out == details

    def test_patient_name_redacted(self):
        out = sanitise_details({'patient_name': 'Rajesh Kumar'})
        assert out == {'patient_name': '<redacted:phi>'}

    def test_age_redacted(self):
        out = sanitise_details({'patient_age': 45, 'age_years': 45})
        assert out['patient_age'] == '<redacted:phi>'
        assert out['age_years'] == '<redacted:phi>'

    def test_sex_and_gender_redacted(self):
        out = sanitise_details({'sex': 'F', 'gender': 'female'})
        assert out['sex'] == '<redacted:phi>'
        assert out['gender'] == '<redacted:phi>'

    def test_contact_fields_redacted(self):
        details = {
            'email': 'rajesh@example.com',
            'phone': '+91-9876543210',
            'mobile': '9876543210',
            'address': '12 MG Road, Ahmedabad',
            'dob': '1980-01-15',
            'date_of_birth': '1980-01-15',
        }
        out = sanitise_details(details)
        for key in details:
            assert out[key] == '<redacted:phi>', f'{key} should be redacted'

    def test_cbc_values_redacted(self):
        details = {
            'hb_g_dl': 11.2,
            'mcv_fl': 102.3,
            'rdw_cv_percent': 16.1,
            'wbc_10e3': 7.4,
            'neutrophils_percent': 55.0,
            'platelets': 220.0,
            'cbc_snapshot': {'hb': 11.2, 'mcv': 102.3},
        }
        out = sanitise_details(details)
        for key in details:
            assert out[key] == '<redacted:phi>', f'{key} should be redacted'

    def test_clinical_note_redacted(self):
        out = sanitise_details({
            'clinical_note': 'Patient reports fatigue for 3 weeks',
            'narrative': 'Short narrative',
        })
        assert out['clinical_note'] == '<redacted:phi>'
        assert out['narrative'] == '<redacted:phi>'

    def test_case_insensitive_matching(self):
        out = sanitise_details({
            'PatientName': 'John',
            'MCV_FL': 100.0,
            'Clinical_Note': 'x',
        })
        for k, v in out.items():
            assert v == '<redacted:phi>'

    def test_nested_dict_sanitised(self):
        out = sanitise_details({
            'filters': {
                'labId': 'LAB-001',
                'patient_name': 'Rajesh',  # deep PHI — must redact
                'dateFrom': '2026-01-01',
            },
        })
        assert out['filters']['labId'] == 'LAB-001'
        assert out['filters']['patient_name'] == '<redacted:phi>'
        assert out['filters']['dateFrom'] == '2026-01-01'

    def test_nested_list_of_dicts_sanitised(self):
        out = sanitise_details({
            'errors': [
                {'row': 1, 'patient_name': 'John', 'message': 'bad age'},
                {'row': 2, 'email': 'x@y.com', 'message': 'dup'},
            ],
        })
        assert out['errors'][0]['patient_name'] == '<redacted:phi>'
        assert out['errors'][0]['row'] == 1
        assert out['errors'][1]['email'] == '<redacted:phi>'

    def test_long_free_text_hashed(self):
        long_msg = 'x' * (FREE_TEXT_MAX_LEN + 50)
        out = sanitise_details({'error_detail': long_msg})
        assert out['error_detail'].startswith('<redacted:len=')
        assert f'len={FREE_TEXT_MAX_LEN + 50}' in out['error_detail']
        assert 'sha256=' in out['error_detail']

    def test_short_free_text_preserved(self):
        out = sanitise_details({'error_detail': 'simple error'})
        assert out['error_detail'] == 'simple error'

    def test_numeric_and_bool_values_preserved(self):
        out = sanitise_details({
            'count': 42,
            'ratio': 0.876,
            'is_expired': False,
        })
        assert out == {'count': 42, 'ratio': 0.876, 'is_expired': False}

    def test_does_not_mutate_input(self):
        original = {'patient_name': 'Rajesh', 'screening_id': 'abc'}
        snapshot = dict(original)
        sanitise_details(original)
        assert original == snapshot

    def test_realistic_audit_call_site_unchanged(self):
        """The current well-behaved call sites should pass through untouched."""
        details = {
            'screening_id': 'abc-123',
            'risk_class': 3,
            'model_version': 'v1.2.3',
        }
        assert sanitise_details(details) == details

    def test_realistic_buggy_call_site_sanitised(self):
        """If a buggy call site ever leaks PHI, sanitise it defensively."""
        buggy = {
            'screening_id': 'abc-123',
            'patient_name': 'SHOULD NOT BE HERE',
            'cbc_snapshot': {'Hb_g_dL': 11.2, 'MCV_fL': 102},
        }
        out = sanitise_details(buggy)
        assert out['screening_id'] == 'abc-123'
        assert out['patient_name'] == '<redacted:phi>'
        assert out['cbc_snapshot'] == '<redacted:phi>'

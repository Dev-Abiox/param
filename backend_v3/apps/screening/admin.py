"""
Django Admin configuration for Screening models.
"""

from django.contrib import admin

from .models import Consent, Doctor, Lab, Patient, Screening


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'tier', 'is_active', 'created_at']
    list_filter = ['tier', 'is_active']
    search_fields = ['code', 'name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'department', 'lab', 'is_active']
    list_filter = ['lab', 'department', 'is_active']
    search_fields = ['code', 'name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['patient_id', 'age', 'sex', 'lab', 'created_at']
    list_filter = ['sex', 'lab']
    search_fields = ['patient_id']
    readonly_fields = ['id', 'created_at', 'updated_at']

    # Note: name_encrypted is not shown to protect PHI


@admin.register(Screening)
class ScreeningAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient', 'risk_class', 'label_text', 'lab', 'doctor', 'created_at']
    list_filter = ['risk_class', 'lab', 'doctor', 'created_at']
    search_fields = ['patient__patient_id', 'performed_by']
    readonly_fields = [
        'id', 'patient', 'lab', 'doctor', 'performed_by',
        'risk_class', 'label_text', 'probabilities', 'rules_fired',
        'cbc_snapshot', 'indices', 'model_version', 'model_artifact_hash',
        'request_hash', 'response_hash', 'screening_hash', 'created_at'
    ]

    def has_add_permission(self, request):
        return False  # Screenings are created via API only

    def has_change_permission(self, request, obj=None):
        return False  # Screenings are immutable

    def has_delete_permission(self, request, obj=None):
        return False  # Screenings should not be deleted


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'consent_type', 'status', 'consent_method', 'consented_at']
    list_filter = ['status', 'consent_type', 'consent_method']
    search_fields = ['patient__patient_id', 'consented_by']
    readonly_fields = ['id', 'created_at', 'updated_at']

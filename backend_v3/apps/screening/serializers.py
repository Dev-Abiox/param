"""
Serializers for Screening API endpoints.
"""

from rest_framework import serializers

from .models import Consent, Doctor, Lab, Patient, Screening


class CBCSerializer(serializers.Serializer):
    """CBC (Complete Blood Count) data serializer."""
    Hb_g_dL = serializers.FloatField(source='Hb')
    RBC_million_uL = serializers.FloatField(source='RBC')
    HCT_percent = serializers.FloatField(source='HCT')
    MCV_fL = serializers.FloatField(source='MCV')
    MCH_pg = serializers.FloatField(source='MCH')
    MCHC_g_dL = serializers.FloatField(source='MCHC')
    RDW_percent = serializers.FloatField(source='RDW')
    WBC_10_3_uL = serializers.FloatField(source='WBC')
    Platelets_10_3_uL = serializers.FloatField(source='Platelets')
    Neutrophils_percent = serializers.FloatField(source='Neutrophils')
    Lymphocytes_percent = serializers.FloatField(source='Lymphocytes')
    Age = serializers.IntegerField()
    Sex = serializers.CharField(max_length=1)


class ScreeningRequestSerializer(serializers.Serializer):
    """Screening prediction request serializer."""
    patientId = serializers.CharField(max_length=100)
    patientName = serializers.CharField(max_length=255, required=False, allow_blank=True)
    labId = serializers.CharField(max_length=50, required=False, allow_blank=True)
    doctorId = serializers.CharField(max_length=50, required=False, allow_blank=True)
    consentId = serializers.CharField(max_length=100, required=False, allow_null=True)
    cbc = CBCSerializer()


class ScreeningResponseSerializer(serializers.Serializer):
    """Screening prediction response serializer."""
    id = serializers.UUIDField()
    patientId = serializers.CharField()
    label = serializers.IntegerField()
    labelText = serializers.CharField()
    probabilities = serializers.DictField()
    indices = serializers.DictField()
    recommendation = serializers.CharField()
    rulesFired = serializers.ListField(child=serializers.CharField())
    modelVersion = serializers.CharField()


class LabSerializer(serializers.ModelSerializer):
    """Lab serializer."""
    doctors_count = serializers.SerializerMethodField()
    cases_count = serializers.SerializerMethodField()

    class Meta:
        model = Lab
        fields = ['id', 'code', 'name', 'tier', 'doctors_count', 'cases_count', 'is_active']

    def get_doctors_count(self, obj):
        return obj.doctors.count()

    def get_cases_count(self, obj):
        return obj.screenings.count()


class DoctorSerializer(serializers.ModelSerializer):
    """Doctor serializer."""
    lab_name = serializers.SerializerMethodField()
    cases_count = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = ['id', 'code', 'name', 'department', 'lab', 'lab_name', 'cases_count', 'is_active']

    def get_lab_name(self, obj):
        return obj.lab.name if obj.lab else None

    def get_cases_count(self, obj):
        return obj.screenings.count()


class PatientSerializer(serializers.ModelSerializer):
    """Patient serializer with decrypted name."""
    name = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = ['id', 'patient_id', 'name', 'age', 'sex', 'lab', 'referring_doctor', 'created_at']

    def get_name(self, obj):
        return obj.name  # Uses property which decrypts


class ScreeningSerializer(serializers.ModelSerializer):
    """Screening record serializer."""
    patient_id = serializers.CharField(source='patient.patient_id')
    patient_name = serializers.SerializerMethodField()
    lab_name = serializers.SerializerMethodField()
    doctor_name = serializers.SerializerMethodField()

    class Meta:
        model = Screening
        fields = [
            'id', 'patient_id', 'patient_name', 'risk_class', 'label_text',
            'probabilities', 'rules_fired', 'indices', 'cbc_snapshot',
            'model_version', 'lab_name', 'doctor_name', 'created_at'
        ]

    def get_patient_name(self, obj):
        return obj.patient.name if obj.patient else None

    def get_lab_name(self, obj):
        return obj.lab.name if obj.lab else None

    def get_doctor_name(self, obj):
        return obj.doctor.name if obj.doctor else None


class ConsentRecordSerializer(serializers.Serializer):
    """Consent recording request serializer."""
    patientId = serializers.CharField(max_length=100)
    consentType = serializers.CharField(max_length=50, default='screening')
    consentText = serializers.CharField()
    consentMethod = serializers.ChoiceField(
        choices=['verbal', 'written', 'electronic'],
        default='verbal'
    )


class ConsentSerializer(serializers.ModelSerializer):
    """Consent serializer."""
    patient_id = serializers.CharField(source='patient.patient_id')

    class Meta:
        model = Consent
        fields = [
            'id', 'patient_id', 'consent_type', 'status',
            'consent_method', 'consented_at', 'revoked_at'
        ]

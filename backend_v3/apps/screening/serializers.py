"""
Serializers for Screening API endpoints.
"""

from rest_framework import serializers

from .models import Consent, Doctor, Lab, Patient, Screening


class CBCSerializer(serializers.Serializer):
    """CBC (Complete Blood Count) data serializer with clinical range validation."""
    Hb_g_dL = serializers.FloatField(source='Hb', min_value=1.0, max_value=25.0)
    RBC_million_uL = serializers.FloatField(source='RBC', min_value=0.5, max_value=10.0)
    HCT_percent = serializers.FloatField(source='HCT', min_value=5.0, max_value=75.0)
    MCV_fL = serializers.FloatField(source='MCV', min_value=30.0, max_value=160.0)
    MCH_pg = serializers.FloatField(source='MCH', min_value=10.0, max_value=60.0)
    MCHC_g_dL = serializers.FloatField(source='MCHC', min_value=20.0, max_value=45.0)
    RDW_percent = serializers.FloatField(source='RDW', min_value=5.0, max_value=40.0)
    WBC_10_3_uL = serializers.FloatField(source='WBC', min_value=0.1, max_value=100.0)
    Platelets_10_3_uL = serializers.FloatField(source='Platelets', min_value=1.0, max_value=2000.0)
    Neutrophils_percent = serializers.FloatField(source='Neutrophils', min_value=0.0, max_value=100.0)
    Lymphocytes_percent = serializers.FloatField(source='Lymphocytes', min_value=0.0, max_value=100.0)
    Age = serializers.IntegerField(min_value=0, max_value=150)
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
    narrative = serializers.CharField(required=False, allow_blank=True)


class LabSerializer(serializers.ModelSerializer):
    """Lab serializer.

    For optimal performance, annotate the queryset with doctors_count and
    cases_count before passing to this serializer::

        Lab.objects.annotate(
            doctors_count=Count('doctors'),
            cases_count=Count('screenings'),
        )

    Falls back to per-object queries if annotations are missing.
    """
    doctors_count = serializers.IntegerField(read_only=True, default=None)
    cases_count = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Lab
        fields = ['id', 'code', 'name', 'tier', 'doctors_count', 'cases_count', 'is_active']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if ret['doctors_count'] is None:
            ret['doctors_count'] = instance.doctors.count()
        if ret['cases_count'] is None:
            ret['cases_count'] = instance.screenings.count()
        return ret


class DoctorSerializer(serializers.ModelSerializer):
    """Doctor serializer.

    For optimal performance, annotate with cases_count and use
    select_related('lab')::

        Doctor.objects.select_related('lab').annotate(
            cases_count=Count('screenings'),
        )
    """
    lab_name = serializers.SerializerMethodField()
    cases_count = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Doctor
        fields = ['id', 'code', 'name', 'department', 'lab', 'lab_name', 'cases_count', 'is_active']

    def get_lab_name(self, obj):
        return obj.lab.name if obj.lab else None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if ret['cases_count'] is None:
            ret['cases_count'] = instance.screenings.count()
        return ret


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
            'model_version', 'lab_name', 'doctor_name', 'created_at',
            # 3.2 work queue
            'status',
            # 3.3 review workflow
            'is_reviewed', 'reviewed_at', 'reviewed_by', 'clinical_note',
            # Clinical narrative
            'narrative',
        ]

    def get_patient_name(self, obj):
        return obj.patient.name if obj.patient else None

    def get_lab_name(self, obj):
        return obj.lab.name if obj.lab else None

    def get_doctor_name(self, obj):
        return obj.doctor.name if obj.doctor else None


class ReviewScreeningSerializer(serializers.Serializer):
    """Validates clinical_note input for the review endpoint."""
    clinical_note = serializers.CharField(
        max_length=5000, required=False, allow_blank=True,
    )


class AdminLabUpdateSerializer(serializers.Serializer):
    """Validates admin lab update fields."""
    name = serializers.CharField(max_length=255, required=False)
    tier = serializers.ChoiceField(
        choices=['standard', 'enterprise', 'pilot'], required=False,
    )
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class AdminDoctorUpdateSerializer(serializers.Serializer):
    """Validates admin doctor update fields."""
    name = serializers.CharField(max_length=255, required=False)
    department = serializers.CharField(max_length=255, required=False, allow_blank=True)
    specialization = serializers.CharField(max_length=255, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    lab_id = serializers.UUIDField(required=False)


class ConsentRecordSerializer(serializers.Serializer):
    """Consent recording request serializer."""
    labId = serializers.CharField(max_length=100, required=True)
    patientId = serializers.CharField(max_length=100)
    consentType = serializers.CharField(max_length=50, default='screening')
    consentText = serializers.CharField(max_length=10000)
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

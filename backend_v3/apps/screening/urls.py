"""
URL configuration for Screening API.
"""

from django.urls import path

from .views import (
    AdminDoctorDetailView,
    AdminDoctorView,
    AdminLabDetailView,
    AdminLabView,
    BulkImportStatusView,
    BulkImportView,
    CaseListView,
    ConsentRecordView,
    ConsentRevokeView,
    ConsentStatusView,
    DoctorListView,
    ExplainView,
    FHIRBundleView,
    LabListView,
    PredictView,
    ReviewScreeningView,
    ScreeningStatusView,
    WorkQueueView,
)

urlpatterns = [
    # Screening
    path('predict', PredictView.as_view(), name='screening-predict'),

    # Labs and Doctors
    path('labs', LabListView.as_view(), name='screening-labs'),
    path('doctors', DoctorListView.as_view(), name='screening-doctors'),
    path('cases', CaseListView.as_view(), name='screening-cases'),

    # Work queue (3.2)
    path('queue', WorkQueueView.as_view(), name='screening-queue'),
    path('cases/<uuid:screening_id>/status', ScreeningStatusView.as_view(), name='screening-status'),

    # Doctor review (3.3)
    path('cases/<uuid:screening_id>/review', ReviewScreeningView.as_view(), name='screening-review'),

    # SHAP Explainability
    path('cases/<uuid:screening_id>/explain', ExplainView.as_view(), name='screening-explain'),

    # Bulk Import (5.3)
    path('bulk-import', BulkImportView.as_view(), name='screening-bulk-import'),
    path('bulk-import/<uuid:job_id>/status', BulkImportStatusView.as_view(), name='screening-bulk-import-status'),

    # FHIR R4 (5.4)
    path('fhir/bundle', FHIRBundleView.as_view(), name='screening-fhir-bundle'),

    # Consent
    path('consent/record', ConsentRecordView.as_view(), name='consent-record'),
    path('consent/status/<str:patient_id>', ConsentStatusView.as_view(), name='consent-status'),
    path('consent/revoke/<uuid:consent_id>', ConsentRevokeView.as_view(), name='consent-revoke'),

    # Admin — Lab Management
    path('admin/labs', AdminLabView.as_view(), name='admin-labs'),
    path('admin/labs/<uuid:lab_id>', AdminLabDetailView.as_view(), name='admin-lab-detail'),

    # Admin — Doctor Management
    path('admin/doctors', AdminDoctorView.as_view(), name='admin-doctors'),
    path('admin/doctors/<uuid:doctor_id>', AdminDoctorDetailView.as_view(), name='admin-doctor-detail'),
]

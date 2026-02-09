"""
URL configuration for Screening API.
"""

from django.urls import path

from .views import (
    CaseListView,
    ConsentRecordView,
    ConsentRevokeView,
    ConsentStatusView,
    DoctorListView,
    LabListView,
    PredictView,
)

urlpatterns = [
    # Screening
    path('predict', PredictView.as_view(), name='screening-predict'),

    # Labs and Doctors
    path('labs', LabListView.as_view(), name='screening-labs'),
    path('doctors', DoctorListView.as_view(), name='screening-doctors'),
    path('cases', CaseListView.as_view(), name='screening-cases'),

    # Consent
    path('consent/record', ConsentRecordView.as_view(), name='consent-record'),
    path('consent/status/<str:patient_id>', ConsentStatusView.as_view(), name='consent-status'),
    path('consent/revoke/<uuid:consent_id>', ConsentRevokeView.as_view(), name='consent-revoke'),
]

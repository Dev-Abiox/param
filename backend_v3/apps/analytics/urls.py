from django.urls import path

from .views import CaseStatsView, DoctorStatsView, LabStatsView, PatientTrendView, ScreeningDetailView, SummaryView

urlpatterns = [
    # Dashboard summary
    path("summary", SummaryView.as_view(), name="analytics-summary"),

    # Lab-level statistics
    path("labs", LabStatsView.as_view(), name="analytics-labs"),

    # Doctor-level statistics
    path("doctors", DoctorStatsView.as_view(), name="analytics-doctors"),

    # Case-level list
    path("cases", CaseStatsView.as_view(), name="analytics-cases"),

    # Full screening detail (View Details / Download Report)
    path("screening/<uuid:screening_id>", ScreeningDetailView.as_view(), name="analytics-screening-detail"),

    # Patient CBC trend (3.4)
    path("trend/<str:patient_id>", PatientTrendView.as_view(), name="analytics-patient-trend"),
]

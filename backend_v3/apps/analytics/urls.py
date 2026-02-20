from django.urls import path

from .views import (
    CaseStatsView,
    DoctorStatsView,
    LabComparisonView,
    LabStatsView,
    PatientTrendView,
    PopulationCohortsView,
    PopulationTrendsView,
    ScreeningDetailView,
    SummaryView,
)

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

    # ── Population Health Analytics ─────────────────────────────────────────────
    # Monthly risk trend across all patients
    path("population/trends", PopulationTrendsView.as_view(), name="analytics-population-trends"),

    # Risk distribution by age group and sex
    path("population/cohorts", PopulationCohortsView.as_view(), name="analytics-population-cohorts"),

    # Cross-lab deficiency rate comparison
    path("population/labs/compare", LabComparisonView.as_view(), name="analytics-lab-comparison"),
]

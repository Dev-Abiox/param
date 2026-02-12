from django.urls import path

from .views import SummaryView, LabStatsView, DoctorStatsView, CaseStatsView

urlpatterns = [
    # Dashboard summary
    path("summary", SummaryView.as_view(), name="analytics-summary"),
    
    # Lab-level statistics
    path("labs", LabStatsView.as_view(), name="analytics-labs"),
    
    # Doctor-level statistics
    path("doctors", DoctorStatsView.as_view(), name="analytics-doctors"),
    
    # Case-level details
    path("cases", CaseStatsView.as_view(), name="analytics-cases"),
]

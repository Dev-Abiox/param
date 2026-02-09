"""
URL configuration for Analytics API.
"""

from django.urls import path

from .views import CaseStatsView, DoctorStatsView, LabStatsView, SummaryView

urlpatterns = [
    path('summary', SummaryView.as_view(), name='analytics-summary'),
    path('labs', LabStatsView.as_view(), name='analytics-labs'),
    path('doctors', DoctorStatsView.as_view(), name='analytics-doctors'),
    path('cases', CaseStatsView.as_view(), name='analytics-cases'),
]

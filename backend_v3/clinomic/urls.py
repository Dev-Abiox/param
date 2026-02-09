"""
URL configuration for Clinomic B12 Screening Platform.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apps.core.urls')),
    path('api/screening/', include('apps.screening.urls')),
    path('api/analytics/', include('apps.analytics.urls')),
]

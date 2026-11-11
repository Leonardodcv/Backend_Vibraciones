from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.HealthView.as_view(), name='health'),
    path('modelo/estado/', views.ModelStatusView.as_view(), name='model-status'),
    path('vibraciones/ultima/', views.LatestView.as_view(), name='latest'),
    path('vibraciones/historico/', views.HistoryView.as_view(), name='history'),
    path('vibraciones/serie-temporal/', views.TimelineView.as_view(), name='timeline'),
    path('vibraciones/anomalias/', views.AnomaliesView.as_view(), name='anomalies'),
    path('vibraciones/proyeccion/', views.ForecastView.as_view(), name='forecast'),
    path('vibraciones/variables/', views.VariablesView.as_view(), name='variables'),
    path('vibraciones/calidad/', views.QualityView.as_view(), name='quality'),
]

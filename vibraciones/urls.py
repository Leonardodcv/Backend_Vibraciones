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
    path('vibraciones/estado/', views.EstadoOperativoView.as_view(), name='operational-status'),
    path('vibraciones/regimenes/', views.RegimenesView.as_view(), name='speed-regimes'),
    path('vibraciones/diagnosticos/ultima/', views.DiagnosticosUltimaView.as_view(), name='plc-diagnostics-latest'),
    path('vibraciones/diagnosticos/historico/', views.DiagnosticosHistoricoView.as_view(), name='plc-diagnostics-history'),
    path('vibraciones/diagnosticos/resumen/', views.DiagnosticosResumenView.as_view(), name='plc-diagnostics-summary'),
]

"""API REST de consulta; entrenamiento y scoring solo mediante comandos de Django."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from rest_framework.response import Response
from rest_framework.views import APIView

from . import db, forecasting, modeling
from .fields import COLUMNS_BY_GROUP, NEW_SENSOR_OFFSETS, VFD_CONTEXT_CANDIDATES

logger = logging.getLogger('vibraciones')
MEXICO = ZoneInfo('America/Mexico_City')


def _params(request, values):
    """values: nombre:(predeterminado,minimo,maximo,tipo)."""
    parsed = {}
    for key, (default, low, high, typ) in values.items():
        try:
            val = typ(request.query_params.get(key, default))
            if not math.isfinite(val) or not low <= val <= high:
                raise ValueError(key)
            parsed[key] = val
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f'Parametro {key} debe estar entre {low} y {high}')
    return parsed


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _with_local_dates(row: dict) -> dict:
    """No altera fechas SQL; agrega sus representaciones con offset -06:00."""
    item = dict(row)
    if isinstance(item.get('fecha_registro_utc'), datetime):
        item['fecha_registro_mexico'] = _utc(item['fecha_registro_utc']).astimezone(MEXICO).isoformat()
    if isinstance(item.get('fecha_calculo_utc'), datetime):
        item['fecha_calculo_mexico'] = _utc(item['fecha_calculo_utc']).astimezone(MEXICO).isoformat()
    stamp = item.get('captura_unix_ms')
    try:
        if stamp is not None:
            item['fecha_captura_mexico'] = datetime.fromtimestamp(
                int(stamp) / 1000, tz=timezone.utc
            ).astimezone(MEXICO).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        item['fecha_captura_mexico'] = None
    return item


def _json_safe(obj):
    if isinstance(obj, datetime):
        return _utc(obj).isoformat().replace('+00:00', 'Z')
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _db_unavailable(exc: Exception):
    logger.exception('No se pudo consultar SQL Server: %s', type(exc).__name__)
    return Response({'error': 'sql_no_disponible',
                     'mensaje': 'No se pudo consultar la base de datos.'}, status=503)


def _active_version():
    bundle = modeling.load_bundle()
    return bundle['metadata']['version'] if bundle else None


class HealthView(APIView):
    allow_public_health = True

    def get(self, request):
        try:
            ok = db.ping()
        except Exception:
            ok = False
        return Response({'estado': 'ok' if ok else 'degradado',
                         'sql': 'conectado' if ok else 'no_disponible',
                         'version': modeling.APP_VERSION}, status=200 if ok else 503)


class ModelStatusView(APIView):
    def get(self, request):
        try:
            return Response(modeling.model_status())
        except Exception:
            logger.exception('Modelo incompatible o danado')
            return Response({'error': 'modelo_incompatible_o_danado'}, status=503)


class LatestView(APIView):
    def get(self, request):
        try:
            row = db.latest()
        except Exception as exc:
            return _db_unavailable(exc)
        if not row:
            return Response({'estado': 'sin_lecturas', 'lectura': None, 'prediccion': None})
        try:
            score = modeling.score_row(row)
        except Exception:
            logger.exception('No se pudo evaluar el modelo')
            return Response({'error': 'modelo_no_disponible'}, status=503)
        return Response(_json_safe({'lectura': _with_local_dates(row), 'prediccion': score}))


class HistoryView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'hours': (6, 1, 168, int), 'limit': (2000, 1, 5000, int)})
            version = _active_version()
            rows = db.history_rows(**p, version=version)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        return Response(_json_safe({**p, 'count': len(rows), 'version_modelo': version,
                                    'timezone_presentacion': 'America/Mexico_City',
                                    'results': [_with_local_dates(row) for row in rows]}))


class TimelineView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'hours': (6, 1, 168, int),
                                  'interval_minutes': (1, 1, 60, int)})
            if p['interval_minutes'] not in (1, 5, 15, 30, 60):
                raise ValueError('interval_minutes debe ser 1, 5, 15, 30 o 60')
            version = _active_version()
            rows = db.timeline_rows(**p, version=version)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        return Response(_json_safe({**p, 'count': len(rows), 'version_modelo': version,
                                    'timezone_presentacion': 'America/Mexico_City',
                                    'results': [_with_local_dates(row) for row in rows]}))


class AnomaliesView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'hours': (24, 1, 168, int),
                                  'min_score': (60.0, 0., 100., float),
                                  'limit': (200, 1, 1000, int)})
            version = _active_version()
            rows = db.anomalies_rows(**p, version=version)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        return Response(_json_safe({'count': len(rows), 'version_modelo': version,
                                    'results': [_with_local_dates(row) for row in rows]}))


class ForecastView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'window_minutes': (60, 30, 60, int),
                                  'horizon_minutes': (30, 5, 60, int)})
            # Datos limitados para proteger SQL. Ultima hora maximo 3600 muestras a 1s.
            rows = db.history_rows(hours=1, limit=5000)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        if rows:
            last = max(int(r['captura_unix_ms']) for r in rows)
            cutoff = last - p['window_minutes'] * 60000
            rows = [r for r in rows if int(r['captura_unix_ms']) >= cutoff]
        result = forecasting.forecast_vrms(rows, p['horizon_minutes'])
        return Response(_json_safe(result))


class VariablesView(APIView):
    """Diccionario del esquema para el frontend y trazabilidad de TIA."""
    def get(self, request):
        try:
            bundle = modeling.load_bundle()
        except Exception:
            logger.exception('No se pudo cargar el modelo')
            return Response({'error': 'modelo_incompatible_o_danado'}, status=503)
        return Response({
            'tabla': 'MantenimientoPredictivo.dbo.LecturasVibraciones',
            'plc_ip': '192.168.0.5',
            'campos_total': sum(map(len, COLUMNS_BY_GROUP.values())),
            'grupos': {k: list(v) for k, v in COLUMNS_BY_GROUP.items()},
            'offsets_sensores_confirmados': NEW_SENSOR_OFFSETS,
            'contexto_vfd_candidato': list(VFD_CONTEXT_CANDIDATES),
            'features_modelo_actual': list(bundle['features']) if bundle else None,
            'medidor_en_indice_anomalia': False,
            'fecha_registro_utc': 'UTC; fecha_registro_mexico se anade en API',
        })


class QualityView(APIView):
    def get(self, request):
        try:
            p = _params(request, {'hours': (24, 1, 168, int)})
            result = db.coverage_rows(**p)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            return _db_unavailable(exc)
        if not result:
            return Response({'hours': p['hours'], 'total': 0, 'cobertura_pct': {}})
        total = int(result['total'] or 0)
        coverage = {
            key: round(100. * int(value or 0) / total, 2) if total else 0.
            for key, value in result.items() if key not in ('total', 'ultima_captura_unix_ms')
        }
        last = result.get('ultima_captura_unix_ms')
        age = (db.now_ms() - int(last)) / 1000 if last is not None else None
        return Response({'hours': p['hours'], 'total': total,
                         'ultima_captura_unix_ms': last,
                         'antiguedad_segundos': round(age, 1) if age is not None else None,
                         'cobertura_pct': coverage,
                         'nota': 'Cobertura no implica que los valores del sensor sean fisicamente validos.'})

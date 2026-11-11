from datetime import datetime, timezone
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings


@override_settings(VIBRATIONS_API_KEY='clave-de-pruebas', DEBUG=False,
                   ALLOWED_HOSTS=['testserver', 'localhost'])
class ApiTests(SimpleTestCase):
    headers = {'HTTP_X_API_KEY': 'clave-de-pruebas'}

    def test_api_key_required(self):
        r = Client().get('/api/v1/modelo/estado/')
        self.assertEqual(r.status_code, 403)

    def test_public_health(self):
        with patch('vibraciones.views.db.ping', return_value=True):
            r = Client().get('/api/v1/health/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['sql'], 'conectado')

    def test_health_unavailable(self):
        with patch('vibraciones.views.db.ping', side_effect=RuntimeError('secret')):
            r = Client().get('/api/v1/health/')
        self.assertEqual(r.status_code, 503)
        self.assertNotIn('secret', r.content.decode())

    def test_history_limit_validation(self):
        r = Client().get('/api/v1/vibraciones/historico/?hours=999', **self.headers)
        self.assertEqual(r.status_code, 400)

    def test_latest_third_channel_and_local_time(self):
        row = {'id': 22, 'captura_unix_ms': 1794438548684,
               'fecha_registro_utc': datetime(2026, 11, 11, 17, 9, 8, 684000),
               's1_vrms_mm_s': 1., 's2_vrms_mm_s': 2., 's3_vrms_mm_s': 3.}
        with patch('vibraciones.views.db.latest', return_value=row), \
             patch('vibraciones.views.modeling.score_row', return_value={
                 'estado': 'NO_ENTRENADO', 'indice_anomalia': None,
             }):
            r = Client().get('/api/v1/vibraciones/ultima/', **self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['lectura']['s3_vrms_mm_s'], 3.)
        self.assertEqual(r.json()['lectura']['fecha_registro_utc'],
                         '2026-11-11T17:09:08.684000Z')
        self.assertTrue(r.json()['lectura']['fecha_registro_mexico'].startswith(
            '2026-11-11T11:09:08.684000-06:00'
        ))

    def test_variables_endpoint(self):
        with patch('vibraciones.views.modeling.load_bundle', return_value=None):
            r = Client().get('/api/v1/vibraciones/variables/', **self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['campos_total'], 74)
        self.assertEqual(r.json()['medidor_en_indice_anomalia'], False)

    def test_timeline_accepted(self):
        with patch('vibraciones.views.modeling.load_bundle', return_value=None), \
             patch('vibraciones.views.db.timeline_rows', return_value=[]):
            r = Client().get(
                '/api/v1/vibraciones/serie-temporal/?hours=24&interval_minutes=5',
                **self.headers,
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['count'], 0)

    def test_coverage_percentage(self):
        with patch('vibraciones.views.db.coverage_rows', return_value={
            'total': 10, 'ultima_captura_unix_ms': 1794438548684,
            's1_vrms': 10, 's2_vrms': 10, 's3_vrms': 5,
        }):
            r = Client().get('/api/v1/vibraciones/calidad/?hours=24', **self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['cobertura_pct']['s3_vrms'], 50.0)

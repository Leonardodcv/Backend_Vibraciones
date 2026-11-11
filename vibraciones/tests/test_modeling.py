from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from django.test import SimpleTestCase, override_settings

from vibraciones.forecasting import forecast_vrms
from vibraciones.modeling import (
    APP_VERSION, CORE_FEATURES, InsufficientData, details_for_sql,
    feature_vector, load_bundle, rpm_with_source, save_bundle, score_row, train_rows,
)


def synthetic_rows(count=1200, interval_ms=1000, *, slope=0.0, with_vfd=True):
    """Solo datos artificiales para tests, no son mediciones reales."""
    rg = np.random.default_rng(20261111)
    start = int(datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp() * 1000)
    rows = []
    for i in range(count):
        speed = 1500 + rg.normal(0, 12)
        row = {
            'id': i + 1,
            'captura_unix_ms': start + i * interval_ms,
            'modo_captura': 'ACTIVO',
            'motor_activo': 1,
            'rpm_sm1281': 0,  # comportamiento real observado en el PLC
            'rpm_vfd': speed,
            'vfd_frecuencia_salida_hz': 50 + rg.normal(0, .7) if with_vfd else None,
            'corriente_vfd_a': 2.4 + rg.normal(0, .13) if with_vfd else None,
            'vfd_voltaje_bus_dc_v': 320 + rg.normal(0, 8) if with_vfd else None,
        }
        for j in (1, 2, 3):
            baseline = 1.0 + .3 * j
            vrms = max(.05, baseline + .001 * (speed - 1500) + rg.normal(0, .09) + slope * i)
            arms = max(.05, 1 + .25 * j + rg.normal(0, .11))
            row.update({
                f's{j}_vrms_mm_s': vrms,
                f's{j}_arms_m_s2': arms,
                f's{j}_peak_m_s2': arms * (3.2 + rg.normal(0, .08)),
                f's{j}_dkw': 1 + .16 * j + rg.normal(0, .06),
                f's{j}_qc_vrms': 1,
                f's{j}_qc_arms': 1,
                f's{j}_qc_dkw': 1,
            })
        rows.append(row)
    return rows


@override_settings(VIBRATIONS_MIN_RPM=300, VIBRATIONS_SCORE_WARNING=60,
                   VIBRATIONS_SCORE_ALERT=85, VIBRATIONS_MIN_TRAIN_SAMPLES=300,
                   VIBRATIONS_MIN_TRAIN_MINUTES=15, VIBRATIONS_USE_VFD_CONTEXT=True)
class ModelingTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows = synthetic_rows()
        cls.bundle = train_rows(cls.rows)

    def test_training_temporal_separation_and_three_sensors(self):
        meta = self.bundle['metadata']
        self.assertGreater(meta['filas_entrenamiento'], meta['filas_calibracion'])
        self.assertEqual(meta['filas_validas'], 1200)
        self.assertEqual(meta['sensores_requeridos'], 3)
        self.assertEqual(meta['version_backend'], APP_VERSION)
        self.assertEqual(list(self.bundle['features'][:len(CORE_FEATURES)]), list(CORE_FEATURES))
        self.assertFalse(meta['medidor_jaritza_en_modelo'])

    def test_rpm_fallback_when_sm1281_reads_zero(self):
        self.assertEqual(rpm_with_source(self.rows[0])[1], 'VFD')
        output = score_row(self.rows[0], self.bundle)
        self.assertEqual(output['fuente_rpm'], 'VFD')
        self.assertEqual(len(output['sensores']), 3)

    def test_outlier_in_sensor3_higher_than_normal(self):
        normal = score_row(self.rows[-1], self.bundle)
        abnormal = dict(self.rows[-1],
                        s3_vrms_mm_s=20., s3_arms_m_s2=12.,
                        s3_peak_m_s2=49., s3_dkw=9.)
        exceptional = score_row(abnormal, self.bundle)
        self.assertIsNotNone(normal['indice_anomalia'])
        self.assertGreater(exceptional['indice_anomalia'], normal['indice_anomalia'])
        self.assertGreaterEqual(exceptional['indice_anomalia'], 60)
        self.assertLessEqual(len(details_for_sql(exceptional)), 1000)
        self.assertFalse(exceptional['es_probabilidad_falla'])

    def test_missing_third_sensor_must_not_score_as_normal(self):
        missing = dict(self.rows[0], s3_vrms_mm_s=None)
        score = score_row(missing, self.bundle)
        self.assertEqual(score['estado'], 'SIN_DATOS')
        self.assertIsNone(score['indice_anomalia'])

    def test_rest_and_post_stop(self):
        rest = dict(self.rows[0], modo_captura='REPOSO', motor_activo=0,
                    rpm_sm1281=0, rpm_vfd=0)
        self.assertEqual(score_row(rest, self.bundle)['estado'], 'REPOSO')
        post = dict(self.rows[0], modo_captura='POST_PARO')
        self.assertEqual(score_row(post, self.bundle)['estado'], 'TRANSICION')

    def test_training_rejects_old_rows_without_sensor3(self):
        old = [dict(r, s3_vrms_mm_s=None) for r in self.rows]
        with self.assertRaises(InsufficientData):
            train_rows(old)

    def test_training_rejects_short_reference(self):
        with self.assertRaises(InsufficientData):
            train_rows(self.rows[:200])

    def test_not_a_match_when_speed_regime_changes(self):
        high = dict(self.rows[0], rpm_vfd=2900.)
        self.assertEqual(score_row(high, self.bundle)['estado'], 'FUERA_RANGO_RPM')

    def test_crest_and_pairs(self):
        vector, reason = feature_vector(self.rows[0])
        self.assertIsNone(reason)
        vals = dict(zip(CORE_FEATURES, vector))
        self.assertAlmostEqual(vals['s3_factor_cresta'],
                               self.rows[0]['s3_peak_m_s2'] / self.rows[0]['s3_arms_m_s2'])
        self.assertAlmostEqual(vals['vrms_diff_1_3'],
                               abs(self.rows[0]['s1_vrms_mm_s'] - self.rows[0]['s3_vrms_mm_s']))

    def test_optional_vfd_context_requires_real_values(self):
        self.assertGreater(len(self.bundle['metadata']['features_vfd_activas']), 0)
        name = self.bundle['metadata']['features_vfd_activas'][0]
        missing = dict(self.rows[0], **{name: None})
        score = score_row(missing, self.bundle)
        self.assertEqual(score['estado'], 'SIN_DATOS')
        self.assertIn('contexto_vfd', score['razon'])

    def test_artifact_roundtrip(self):
        with TemporaryDirectory() as td:
            path = Path(td) / 'modelo_v1_1.joblib'
            save_bundle(self.bundle, path)
            loaded = load_bundle(path)
            self.assertEqual(loaded['metadata']['version'], self.bundle['metadata']['version'])
            self.assertAlmostEqual(score_row(self.rows[30], loaded)['indice_anomalia'],
                                   score_row(self.rows[30], self.bundle)['indice_anomalia'])


@override_settings(VIBRATIONS_MIN_RPM=300)
class ForecastTests(SimpleTestCase):
    def test_forecast_all_three_channels(self):
        rows = synthetic_rows(count=40, interval_ms=60000, slope=.018)
        forecast = forecast_vrms(rows, horizon_minutes=30)
        self.assertTrue(forecast['disponible'])
        self.assertEqual(set(forecast['sensores']), {'sensor_1', 'sensor_2', 'sensor_3'})
        self.assertGreater(forecast['sensores']['sensor_3']['vrms_proyectado_mm_s'],
                           forecast['sensores']['sensor_3']['vrms_actual_mm_s'])
        self.assertIsNone(forecast['tiempo_hasta_falla'])

    def test_forecast_disallows_old_data_without_sensor3(self):
        old = [dict(row, s3_vrms_mm_s=None) for row in synthetic_rows(40, 60000)]
        result = forecast_vrms(old)
        self.assertFalse(result['disponible'])

    def test_variable_rpm_disables_extrapolation(self):
        rows = synthetic_rows(40, interval_ms=60000)
        for i, row in enumerate(rows):
            row['rpm_vfd'] = 800 if i % 2 else 1900
        self.assertEqual(forecast_vrms(rows)['razon'], 'rpm_variable_no_comparable')

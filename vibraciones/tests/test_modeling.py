"""Tests v1.3. Datos sinteticos, no accede al PLC ni a SQL Server."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from django.test import SimpleTestCase, override_settings

from vibraciones import modeling, operacion
from vibraciones.forecasting import forecast_vrms


def synthetic_rows(speeds=(5., 10., 15., 20.), samples_per_speed=400):
    rg = np.random.default_rng(20261112)
    base = int(datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp() * 1000)
    out = []
    for speed in speeds:
        for _ in range(samples_per_speed):
            i = len(out)
            hz = speed + rg.normal(0, .03)
            row = {'id': i+1, 'captura_unix_ms': base+i*3000,
                   'modo_captura': 'ACTIVO', 'motor_activo': 1,
                   'rpm_sm1281': 0, 'qc_rpm_sm1281': 0,
                   'rpm_vfd': 30*hz, 'vfd_frecuencia_salida_hz': hz,
                   'vfd_voltaje_bus_dc_v': 300, 'vfd_fault': 0,
                   'orden_marcha_vfd': 1}
            for j in (1, 2, 3):
                vrms = .12*j + .023*speed**1.3 + rg.normal(0,.025)
                arms = .15*j + .026*speed**1.1 + rg.normal(0,.025)
                row.update({f's{j}_vrms_mm_s': vrms,
                            f's{j}_arms_m_s2': arms,
                            f's{j}_peak_m_s2': arms*(3.2+rg.normal(0,.05)),
                            f's{j}_dkw': .3*j+.01*speed+rg.normal(0,.02)})
            out.append(row)
    return out


@override_settings(VIBRATIONS_MIN_TRAIN_SAMPLES=300,
                   VIBRATIONS_MIN_TRAIN_MINUTES=15,
                   VIBRATIONS_SPEED_SOURCE='vfd_hz',
                   VIBRATIONS_SPEED_BAND_WIDTH=2.,
                   VIBRATIONS_SCORE_WARNING=60, VIBRATIONS_SCORE_ALERT=85,
                   VIBRATIONS_EVENTS_CSV=None)
class ModelVersion13Tests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows = synthetic_rows()
        cls.bundle = modeling.train_rows(cls.rows, confirm_normal=True)

    def test_four_speed_regimes_separate_calibration(self):
        self.assertEqual(self.bundle['metadata']['n_regimenes'], 4)
        self.assertTrue(self.bundle['metadata']['multivelocidad_validada'])
        self.assertEqual(len(self.bundle['features']), 21)
        self.assertEqual(self.bundle['metadata']['version_backend'], '1.3.0')
        self.assertFalse(self.bundle['metadata']['medidor_jaritza_en_modelo'])
        self.assertFalse(self.bundle['metadata']['alarmas_sm1281_son_features_modelo'])
        self.assertFalse(self.bundle['metadata']['db13_espejo_son_features_modelo'])

    def test_speed_changes_are_not_automatically_failure(self):
        for group in range(4):
            normal = modeling.score_row(self.rows[group*400+250], self.bundle, eventos=())
            self.assertIsNotNone(normal['indice_anomalia'])
            self.assertIn(normal['estado'], ('NORMAL', 'OBSERVACION', 'ANOMALIA'))
        # Una velocidad SIN entrenamiento no se fuerza a la mas cercana.
        unknown = dict(self.rows[0], vfd_frecuencia_salida_hz=12.5, rpm_vfd=375)
        result = modeling.score_row(unknown, self.bundle, eventos=())
        self.assertEqual(result['estado'], 'SIN_MODELO_PARA_ESTA_VELOCIDAD')
        self.assertIsNone(result['indice_anomalia'])

    def test_third_sensor_anomaly_increases_index(self):
        row = self.rows[900]
        baseline = modeling.score_row(row, self.bundle, eventos=())
        broken = dict(row, s3_vrms_mm_s=row['s3_vrms_mm_s']*12,
                      s3_arms_m_s2=row['s3_arms_m_s2']*8,
                      s3_peak_m_s2=row['s3_peak_m_s2']*10,
                      s3_dkw=row['s3_dkw']*9)
        out = modeling.score_row(broken, self.bundle, eventos=())
        self.assertGreaterEqual(out['indice_anomalia'], baseline['indice_anomalia'])
        self.assertLessEqual(len(modeling.details_for_sql(out)), 1000)

    def test_rest_vs_unconfirmed_power(self):
        rest = dict(self.rows[0], vfd_frecuencia_salida_hz=0, rpm_vfd=0,
                    modo_captura='REPOSO', motor_activo=False)
        result = modeling.score_row(rest, self.bundle, eventos=())
        self.assertEqual(result['estado'], 'ENERGIZADO_EN_REPOSO')
        self.assertIsNone(result['indice_anomalia'])
        off = dict(rest, vfd_voltaje_bus_dc_v=0)
        state = operacion.estado_operativo(off)
        self.assertEqual(state['estado'], 'SIN_GIRO_ENERGIA_NO_CONFIRMADA')

    def test_operator_relay_annotation_priority(self):
        row = self.rows[0]
        evt = operacion.Evento(row['captura_unix_ms'], row['captura_unix_ms']+3001,
                               'FALLA_ELECTRICA_CONFIRMADA', None, False, 'Relevador')
        score = modeling.score_row(row, self.bundle, eventos=(evt,))
        self.assertEqual(score['estado'], 'FALLA_ELECTRICA_CONFIRMADA')
        self.assertIsNone(score['indice_anomalia'])

    def test_missing_third_sensor_not_imputed(self):
        row = dict(self.rows[5], s3_vrms_mm_s=None)
        self.assertEqual(modeling.score_row(row, self.bundle, eventos=())['estado'], 'SIN_DATOS')

    def test_transition_excluded(self):
        before = self.rows[100]
        next_speed = dict(self.rows[101], vfd_frecuencia_salida_hz=16, rpm_vfd=480)
        self.assertEqual(modeling.score_row(next_speed, self.bundle,
                         previous=before, eventos=())['estado'], 'TRANSICION')

    def test_artifact_is_new_and_separate(self):
        self.assertIn('v1_3', modeling.bundle_path().name)
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'model.joblib'
            modeling.save_bundle(self.bundle, path)
            model = modeling.load_bundle(path)
            self.assertEqual(model['metadata']['version'], self.bundle['metadata']['version'])

    def test_events_require_confirmed_healthy(self):
        with self.assertRaises(modeling.InsufficientData):
            modeling.train_rows(self.rows[:500], confirm_normal=False)

    def test_forecast_three_sensors(self):
        rows = synthetic_rows(speeds=(20.,), samples_per_speed=40)
        for i,row in enumerate(rows):
            row['captura_unix_ms']+=i*57000
        result = forecast_vrms(rows)
        self.assertTrue(result['disponible'])
        self.assertEqual(set(result['sensores']), {'sensor_1','sensor_2','sensor_3'})

    def test_plc_alarm_annotates_but_not_auto_failure(self):
        row = dict(self.rows[900], s1_sm1281_mon_dkw_bits=8,
                   s1_sm1281_tiene_alarma=True, s1_sm1281_sensorstate_bits=2,
                   s1_sm1281_faulttype_bits=1)
        score = modeling.score_row(row, self.bundle, eventos=())
        self.assertIsNotNone(score['indice_anomalia'])
        self.assertIn({'sensor': 1, 'nivel': 'ALARMA_PLC'},
                      score['diagnostico_sm1281']['alertas_plc'])

    def test_sensor_disconnected_does_not_generate_anomaly_score(self):
        row = dict(self.rows[900], s3_sm1281_sensorstate_bits=0,
                   s3_sm1281_sensor_conectado=False)
        score = modeling.score_row(row, self.bundle, eventos=())
        self.assertEqual(score['estado'], 'CALIDAD_INSTRUMENTACION_INVALIDA')
        self.assertIsNone(score['indice_anomalia'])

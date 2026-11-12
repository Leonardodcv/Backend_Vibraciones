"""Casos basados en la lectura S7 y el registro SQL 221331 del usuario."""
from django.test import SimpleTestCase
from vibraciones import diagnosticos


class SM1281DiagnosticTests(SimpleTestCase):
    def example(self):
        r = {}
        for i, dkw in ((1, 8), (2, 4), (3, 2)):
            for k in diagnosticos.MONITORES:
                r[f's{i}_sm1281_mon_{k}_bits'] = (
                    1 if k in ('bpfo', 'bpfi', 'ftf', 'bsf')
                    else dkw if k == 'dkw' else 2
                )
            r.update({f's{i}_sm1281_sensorstate_bits': 2,
                      f's{i}_sm1281_faulttype_bits': 1,
                      f's{i}_sm1281_sensor_conectado': True,
                      f's{i}_sm1281_sensor_corto': False,
                      f's{i}_sm1281_sensor_cable_roto': False,
                      f's{i}_vrms_mm_s': .64,
                      f'db13_s{i}_vrms_mm_s': .64,
                      f's{i}_qc_vrms': 1, f's{i}_qc_arms': 1,
                      f's{i}_qc_dkw': 1})
        r['s1_sm1281_tiene_alarma'] = True
        r['s2_sm1281_tiene_aviso'] = True
        return r

    def test_raw_bitmasks(self):
        self.assertEqual(diagnosticos.monitor_estado(8)['estado'], 'ALARMA')
        self.assertEqual(diagnosticos.monitor_estado(4)['estado'], 'AVISO')
        self.assertEqual(diagnosticos.monitor_estado(2)['estado'], 'BUENO')
        self.assertEqual(diagnosticos.monitor_estado(1)['estado'], 'NO_VALIDO')
        self.assertEqual(diagnosticos.monitor_estado(None)['estado'], 'SIN_DATO')

    def test_real_example_alarms_and_unavailable_bearing_monitors(self):
        r = diagnosticos.diagnostic_summary(self.example())
        self.assertEqual(r['sensores']['sensor_1']['estado'], 'ALARMA_PLC')
        self.assertEqual(r['sensores']['sensor_2']['estado'], 'AVISO_PLC')
        self.assertEqual(r['sensores']['sensor_3']['estado'], 'SIN_ALERTA_EN_MONITORES_VALIDOS')
        for i in (1,2,3):
            self.assertEqual(r['sensores'][f'sensor_{i}']['monitores_no_validos'], 4)
            self.assertTrue(r['sensores'][f'sensor_{i}']['diagnostico_parcial'])
        self.assertEqual(r['sensores']['sensor_1']['espejo_db13']['estado'],
                         'COINCIDENTE_APROXIMADO')
        self.assertEqual(diagnosticos.quality_gate(self.example()), (True, []))

    def test_alarm_does_not_implicate_sensor_fault(self):
        row = self.example()
        row['s1_sm1281_mon_dkw_bits'] = 8
        self.assertTrue(diagnosticos.quality_gate(row)[0])

    def test_sensor_cable_broken_blocks_model(self):
        row = self.example()
        row['s1_sm1281_faulttype_bits'] = 4
        self.assertFalse(diagnosticos.quality_gate(row)[0])

    def test_qc_zero_blocks_model(self):
        row = self.example()
        row['s2_qc_dkw'] = 0
        self.assertFalse(diagnosticos.quality_gate(row)[0])

    def test_new_columns_historically_absent_do_not_create_faults(self):
        row = {'s1_vrms_mm_s': .5, 's1_arms_m_s2': .8}
        self.assertTrue(diagnosticos.quality_gate(row)[0])
        d = diagnosticos.diagnostic_summary(row)
        self.assertEqual(d['sensores']['sensor_1']['estado'], 'SIN_MONITORES_VALIDOS')

    def test_db13_discrepancy_is_not_replacement(self):
        row = self.example()
        row['db13_s2_vrms_mm_s'] = 42.0
        d = diagnosticos.diagnostic_summary(row)
        self.assertEqual(d['sensores']['sensor_2']['espejo_db13']['estado'],
                         'DIFERENCIA_DETECTADA')
        self.assertTrue(diagnosticos.quality_gate(row)[0])

    def test_old_132_flags_recalculated_from_raw(self):
        row = self.example()
        row['s1_sm1281_tiene_aviso'] = None
        row['s2_sm1281_tiene_alarma'] = None
        d = diagnosticos.diagnostic_summary(row)
        self.assertEqual(d['sensores']['sensor_1']['estado'], 'ALARMA_PLC')
        self.assertEqual(d['sensores']['sensor_2']['estado'], 'AVISO_PLC')

import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from vibraciones import db
from vibraciones.fields import ALL_COLUMNS, COLUMNS_BY_GROUP, MEDIDOR_FIELDS


class SchemaTests(SimpleTestCase):
    def test_193_columns_unique_and_three_sensor_groups(self):
        self.assertEqual(len(ALL_COLUMNS), 193)
        self.assertEqual(len(set(ALL_COLUMNS)), 193)
        self.assertIn('s3_vrms_mm_s', ALL_COLUMNS)
        self.assertIn('medidor_thd_corriente_l2_raw', ALL_COLUMNS)
        self.assertEqual(len(COLUMNS_BY_GROUP['sensor_3']), 8)
        self.assertEqual(len(MEDIDOR_FIELDS), 20)
        self.assertEqual(len(COLUMNS_BY_GROUP['velocidad_y_modulo_sm1281']), 16)
        self.assertEqual(len(COLUMNS_BY_GROUP['espejo_db13_sensor_3']), 7)
        self.assertEqual(len(COLUMNS_BY_GROUP['diagnostico_sm1281_sensor_1']), 18)
        self.assertIn('s3_sm1281_tiene_alarma', ALL_COLUMNS)

    def test_select_is_explicit_and_safe(self):
        self.assertNotIn('SELECT *', db.SELECT_COLUMNS)
        for name in ALL_COLUMNS:
            self.assertIn(f'l.[{name}]', db.SELECT_COLUMNS)

    @patch.dict(os.environ, {
        'SQL_AUTH': 'sql', 'SQL_USERNAME': 'testuser',
        'SQL_PASSWORD': 'a;b}c', 'SQL_HOST': '10.10.17.13',
        'SQL_PORT': '1433', 'SQL_DATABASE': 'MantenimientoPredictivo',
    }, clear=True)
    def test_connection_matches_existing_server_and_escapes_password(self):
        c = db._connection_string()
        self.assertIn('PWD={a;b}}c}', c)
        self.assertIn('DATABASE={MantenimientoPredictivo}', c)
        self.assertIn('SERVER={10.10.17.13,1433}', c)
        self.assertNotIn('SQL_PASSWORD', c)

    @patch.dict(os.environ, {
        'SQL_AUTH': 'sql', 'SQL_USERNAME': 'x', 'SQL_PASSWORD': 'y',
        'SQL_PORT': '', 'SQL_CONNECTION_TIMEOUT': '', 'SQL_QUERY_TIMEOUT': '',
    }, clear=True)
    def test_blank_sql_port_and_timeouts_use_safe_defaults(self):
        self.assertIn('SERVER={10.10.17.13,1433}', db._connection_string())
        self.assertEqual(db._env_int('SQL_CONNECTION_TIMEOUT', 5), 5)
        self.assertEqual(db._env_int('SQL_QUERY_TIMEOUT', 20), 20)

    @patch.dict(os.environ, {
        'SQL_AUTH': 'sql', 'SQL_USERNAME': 'x', 'SQL_PASSWORD': 'y',
        'SQL_PORT': 'abc',
    }, clear=True)
    def test_invalid_sql_port_is_reported_clearly(self):
        with self.assertRaisesRegex(ValueError, 'SQL_PORT debe ser un numero entero'):
            db._connection_string()

    @patch.dict(os.environ, {'SQL_AUTH': 'sql', 'SQL_USERNAME': 'x', 'SQL_PASSWORD': 'y'}, clear=True)
    @patch('vibraciones.db.pyodbc.connect')
    def test_connection_closes(self, connector):
        con = MagicMock()
        connector.return_value = con
        con.cursor.return_value.execute.return_value.fetchone.return_value = (1,)
        self.assertTrue(db.ping())
        con.close.assert_called_once()

    @patch.dict(os.environ, {'SQL_AUTH': 'sql', 'SQL_USERNAME': 'x', 'SQL_PASSWORD': 'y'}, clear=True)
    @patch('vibraciones.db.pyodbc.connect')
    def test_parameterized_scoring_insert(self, connector):
        connector.return_value = MagicMock()
        db.save_score(lectura_id=123, index=84.1,
                      version='v1.3.0-test', details_json='{"estado":"ANOMALIA"}')
        cursor = connector.return_value.cursor.return_value
        args, kwargs = cursor.execute.call_args
        self.assertIn('VALUES (?, ?, ?, ?, ?)', args[0])
        self.assertNotIn('84.1', args[0])
        self.assertEqual(args[1], 123)
        self.assertEqual(args[4], 123)
        connector.return_value.commit.assert_called_once()

    @patch.dict(os.environ, {'SQL_AUTH': 'sql', 'SQL_USERNAME': 'x', 'SQL_PASSWORD': 'y'}, clear=True)
    @patch('vibraciones.db.pyodbc.connect')
    def test_unscored_skips_rows_without_third_sensor(self, connector):
        connector.return_value = MagicMock()
        connector.return_value.cursor.return_value.execute.return_value.description = [('id',)]
        connector.return_value.cursor.return_value.execute.return_value.fetchall.return_value = []
        db.unscored_rows('version-1')
        query = connector.return_value.cursor.return_value.execute.call_args[0][0]
        self.assertIn('l.s3_vrms_mm_s IS NOT NULL', query)
        self.assertIn('l.modo_captura', query)
        self.assertIn('r.version_modelo', query)

    @patch.dict(os.environ, {'SQL_AUTH': 'sql', 'SQL_USERNAME': 'x', 'SQL_PASSWORD': 'y'}, clear=True)
    @patch('vibraciones.db.pyodbc.connect')
    def test_timeline_includes_three_sensors(self, connector):
        connector.return_value = MagicMock()
        connector.return_value.cursor.return_value.execute.return_value.description = [('x',)]
        connector.return_value.cursor.return_value.execute.return_value.fetchall.return_value = []
        db.timeline_rows(hours=24, interval_minutes=5, version='v1.1')
        sql = connector.return_value.cursor.return_value.execute.call_args[0][0]
        self.assertIn('s3_vrms_promedio_mm_s', sql)
        self.assertIn('medidor_frecuencia_promedio_hz', sql)

    @patch.dict(os.environ, {'SQL_AUTH': 'sql', 'SQL_USERNAME': 'x', 'SQL_PASSWORD': 'y'}, clear=True)
    @patch('vibraciones.db.pyodbc.connect')
    def test_diagnostic_history_is_parameterized(self, connector):
        connector.return_value = MagicMock()
        connector.return_value.cursor.return_value.execute.return_value.description = [('id',)]
        connector.return_value.cursor.return_value.execute.return_value.fetchall.return_value = []
        self.assertEqual(db.diagnostics_rows(hours=6, limit=20), [])
        args = connector.return_value.cursor.return_value.execute.call_args[0]
        self.assertIn('SELECT TOP (?)', args[0])
        self.assertIn('s1_sm1281_mon_dkw_bits', args[0])
        self.assertIn('db13_s3_vrms_mm_s', args[0])
        self.assertEqual(args[1], 20)

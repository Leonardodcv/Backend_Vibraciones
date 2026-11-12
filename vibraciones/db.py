"""Consultas parametrizadas a SQL Server EXISTENTE (sin ORM ni migraciones).

La lectura bruta se mantiene en dbo.LecturasVibraciones. Solo se insertan
resultados de inferencia en dbo.ResultadosAnomaliaVibraciones.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import pyodbc

from .fields import ALL_COLUMNS, MODEL_COLUMNS

TABLE = 'dbo.LecturasVibraciones'
RESULTS = 'dbo.ResultadosAnomaliaVibraciones'
MODEL_NAME = 'IsolationForest3S_Regimenes_SM1281'
BASE_COLUMNS = ALL_COLUMNS  # compatibilidad con comandos de la version 1.0
SELECT_COLUMNS = ', '.join('l.[' + c + ']' for c in BASE_COLUMNS)
SELECT_MODEL_COLUMNS = ', '.join('l.[' + c + ']' for c in MODEL_COLUMNS)
# La SQL de modelo no necesita 193 columnas, para reducir memoria.
DIAGNOSTIC_COLUMNS = tuple(dict.fromkeys((
    'id','fecha_registro_utc','captura_unix_ms','modo_captura',
    'rpm_vfd','vfd_frecuencia_salida_hz','estado_operativo_detalle',
    *(f's{i}_{k}' for i in (1,2,3) for k in ('vrms_mm_s','arms_m_s2','dkw',
                                             'peak_m_s2','qc_vrms','qc_arms','qc_dkw')),
    *(f's{i}_sm1281_{k}' for i in (1,2,3) for k in (
        'mon_vrms_bits','mon_arms_bits','mon_dkw_bits','mon_espectro_a_bits',
        'mon_espectro_v_bits','mon_envolvente_bits','mon_bpfo_bits',
        'mon_bpfi_bits','mon_ftf_bits','mon_bsf_bits','sensorstate_bits',
        'faulttype_bits','tiene_aviso','tiene_alarma','sensor_conectado',
        'sensor_corto','sensor_cable_roto')),
    *(f'db13_s{i}_{k}' for i in (1,2,3) for k in (
        'vrms_mm_s','arms_m_s2','dkw','peak_m_s2','qc_vrms','qc_arms','qc_dkw')),
)))
SELECT_DIAGNOSTIC_COLUMNS = ', '.join('l.[' + c + ']' for c in DIAGNOSTIC_COLUMNS)

# Deshabilitar pooling opcional ANTES de la primera conexion pyodbc.
if os.getenv('SQL_POOLING', 'no').strip().lower() in ('0', 'no', 'false', 'off'):
    pyodbc.pooling = False


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _connection_string() -> str:
    """Cadena ODBC, sin credenciales incrustadas en el proyecto ni logs."""
    driver = os.getenv('SQL_DRIVER', 'ODBC Driver 18 for SQL Server')
    host = os.getenv('SQL_HOST', '10.10.17.13')
    port = int(os.getenv('SQL_PORT', '1433'))
    database = os.getenv('SQL_DATABASE', 'MantenimientoPredictivo')
    if not 1 <= port <= 65535:
        raise ValueError('SQL_PORT fuera de rango')
    if not host or not database:
        raise ValueError('SQL_HOST y SQL_DATABASE son obligatorios')

    def quote(value: object) -> str:
        return '{' + str(value).replace('}', '}}') + '}'

    parts = [
        f'DRIVER={quote(driver)}',
        f'SERVER={quote(host + "," + str(port))}',
        f'DATABASE={quote(database)}',
        f'Encrypt={os.getenv("SQL_ENCRYPT", "no")}',
        f'TrustServerCertificate={os.getenv("SQL_TRUST_SERVER_CERTIFICATE", "yes")}',
        'APP=VibracionesDjangoV1_3',
    ]
    auth = os.getenv('SQL_AUTH', 'sql').strip().lower()
    if auth == 'windows':
        parts.append('Trusted_Connection=yes')
    elif auth == 'sql':
        user, password = os.getenv('SQL_USERNAME', ''), os.getenv('SQL_PASSWORD', '')
        if not user or not password:
            raise ValueError('Configurar SQL_USERNAME y SQL_PASSWORD en .env')
        parts += [f'UID={quote(user)}', f'PWD={quote(password)}']
    else:
        raise ValueError('SQL_AUTH debe ser sql o windows')
    return ';'.join(parts) + ';'


@contextmanager
def sql_connection(*, write: bool = False) -> Iterator[pyodbc.Connection]:
    conn = pyodbc.connect(
        _connection_string(),
        timeout=int(os.getenv('SQL_CONNECTION_TIMEOUT', '5')),
        autocommit=not write,
    )
    conn.timeout = int(os.getenv('SQL_QUERY_TIMEOUT', '20'))
    try:
        yield conn
        if write:
            conn.commit()
    except Exception:
        if write:
            conn.rollback()
        raise
    finally:
        conn.close()


def _rows(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _row(cursor: pyodbc.Cursor) -> dict[str, Any] | None:
    names = [c[0] for c in cursor.description]
    item = cursor.fetchone()
    return dict(zip(names, item)) if item is not None else None


def ping() -> bool:
    with sql_connection() as con:
        return con.cursor().execute('SELECT 1').fetchone()[0] == 1


def latest() -> dict | None:
    query = f'SELECT TOP (1) {SELECT_COLUMNS} FROM {TABLE} AS l ORDER BY l.id DESC;'
    with sql_connection() as con:
        return _row(con.cursor().execute(query))


def training_rows(start_ms: int, end_ms: int, limit: int = 50000) -> list[dict]:
    if not (1 <= limit <= 250000 and 0 < start_ms < end_ms):
        raise ValueError('Rango de entrenamiento o limit invalido')
    query = (
        f'SELECT TOP (?) {SELECT_MODEL_COLUMNS} FROM {TABLE} AS l '
        'WHERE l.captura_unix_ms >= ? AND l.captura_unix_ms < ? '
        'AND l.s3_vrms_mm_s IS NOT NULL '
        'ORDER BY l.captura_unix_ms DESC, l.id DESC;'
    )
    with sql_connection() as con:
        items = _rows(con.cursor().execute(query, limit, start_ms, end_ms))
    return list(reversed(items))


def history_rows(hours: int = 6, limit: int = 2000, *, version: str | None = None) -> list[dict]:
    if not (1 <= hours <= 168 and 1 <= limit <= 5000):
        raise ValueError('hours o limit fuera de rango')
    after = now_ms() - hours * 3600 * 1000
    query = (
        f'SELECT TOP (?) {SELECT_COLUMNS}, '
        'r.indice_anomalia, r.version_modelo, r.fecha_calculo_utc '
        f'FROM {TABLE} AS l OUTER APPLY ('
        'SELECT TOP (1) indice_anomalia, version_modelo, fecha_calculo_utc '
        f'FROM {RESULTS} AS r WHERE r.lectura_id = l.id '
        'AND r.modelo = ? AND r.version_modelo = ? ORDER BY r.id DESC) AS r '
        'WHERE l.captura_unix_ms >= ? '
        'ORDER BY l.captura_unix_ms DESC, l.id DESC;'
    )
    with sql_connection() as con:
        items = _rows(con.cursor().execute(query, limit, MODEL_NAME, version or '', after))
    return list(reversed(items))


def anomalies_rows(hours: int = 24, min_score: float = 60.0, limit: int = 200,
                   *, version: str | None = None) -> list[dict]:
    if not (1 <= hours <= 168 and 0 <= min_score <= 100 and 1 <= limit <= 1000):
        raise ValueError('Parametros fuera de rango')
    after = now_ms() - hours * 3600 * 1000
    query = (
        'SELECT TOP (?) l.id AS lectura_id, l.captura_unix_ms, l.modo_captura, '
        'l.rpm_sm1281, l.rpm_vfd, l.s1_vrms_mm_s, l.s2_vrms_mm_s, l.s3_vrms_mm_s, '
        'r.indice_anomalia, r.modelo, r.version_modelo, r.detalle, r.fecha_calculo_utc '
        f'FROM {RESULTS} AS r JOIN {TABLE} AS l ON l.id = r.lectura_id '
        'WHERE l.captura_unix_ms >= ? AND r.modelo = ? AND r.version_modelo = ? '
        'AND r.indice_anomalia >= ? ORDER BY r.id DESC;'
    )
    with sql_connection() as con:
        return _rows(con.cursor().execute(query, limit, after, MODEL_NAME,
                                          version or '', min_score))


def unscored_rows(version: str, *, limit: int = 200, since_id: int = 0) -> list[dict]:
    if not (1 <= limit <= 10000 and since_id >= 0 and version):
        raise ValueError('Parametros invalidos')
    # Excluir filas antiguas sin canal 3 y periodos en reposo para evitar que
    # una cola de miles de filas no calificables bloquee el scoring.
    query = (
        f'SELECT TOP (?) {SELECT_MODEL_COLUMNS} FROM {TABLE} AS l '
        'WHERE l.id > ? AND l.modo_captura = \'ACTIVO\' '
        'AND l.s3_vrms_mm_s IS NOT NULL AND l.s3_arms_m_s2 IS NOT NULL '
        'AND (l.rpm_vfd > ? OR l.vfd_frecuencia_salida_hz > ?) '
        f'AND NOT EXISTS (SELECT 1 FROM {RESULTS} AS r WHERE r.lectura_id = l.id '
        'AND r.modelo = ? AND r.version_modelo = ?) '
        'ORDER BY l.id DESC;'
    )
    from django.conf import settings
    with sql_connection() as con:
        return _rows(con.cursor().execute(
            query, limit, since_id, 20, 0.5, MODEL_NAME, version,
        ))


def save_score(*, lectura_id: int, index: float, version: str, details_json: str) -> None:
    """INSERT idempotente por lectura/modelo/version bajo UPDLOCK+HOLDLOCK."""
    if lectura_id <= 0 or not (0 <= index <= 100) or len(details_json) > 1000:
        raise ValueError('Resultado fuera de rango')
    query = (
        f'IF NOT EXISTS (SELECT 1 FROM {RESULTS} WITH (UPDLOCK, HOLDLOCK) '
        'WHERE lectura_id = ? AND modelo = ? AND version_modelo = ?) '
        f'INSERT INTO {RESULTS} (lectura_id, indice_anomalia, modelo, version_modelo, detalle) '
        'VALUES (?, ?, ?, ?, ?);'
    )
    with sql_connection(write=True) as con:
        con.cursor().execute(query, lectura_id, MODEL_NAME, version,
                             lectura_id, float(index), MODEL_NAME, version, details_json)


def timeline_rows(hours: int = 6, interval_minutes: int = 1,
                  *, version: str | None = None) -> list[dict]:
    if not (1 <= hours <= 168 and interval_minutes in (1, 5, 15, 30, 60)):
        raise ValueError('hours o interval_minutes invalidos')
    after = now_ms() - hours * 3600 * 1000
    bucket_ms = interval_minutes * 60000
    query = (
        'WITH serie AS ('
        'SELECT (l.captura_unix_ms / ?) AS bucket, '
        'COALESCE(NULLIF(l.rpm_sm1281,0), l.rpm_vfd) AS rpm_ref, '
        'l.s1_vrms_mm_s, l.s2_vrms_mm_s, l.s3_vrms_mm_s, '
        'l.s1_arms_m_s2, l.s2_arms_m_s2, l.s3_arms_m_s2, '
        'l.vfd_frecuencia_salida_hz, l.corriente_vfd_a, l.vfd_voltaje_bus_dc_v, '
        'l.medidor_frecuencia_hz, l.medidor_corriente_l1_a, l.medidor_corriente_l2_a, '
        'l.vfd_regimen_hz, l.vfd_cambio_hz_por_seg, '
        'l.s1_sm1281_tiene_alarma, l.s2_sm1281_tiene_alarma, l.s3_sm1281_tiene_alarma, '
        'l.s1_sm1281_tiene_aviso, l.s2_sm1281_tiene_aviso, l.s3_sm1281_tiene_aviso, '
        'r.indice_anomalia '
        f'FROM {TABLE} AS l '
        'OUTER APPLY (SELECT TOP (1) r.indice_anomalia '
        f'FROM {RESULTS} AS r WHERE r.lectura_id = l.id '
        'AND r.modelo = ? AND r.version_modelo = ? ORDER BY r.id DESC) AS r '
        'WHERE l.captura_unix_ms >= ?) '
        'SELECT bucket * ? AS captura_unix_ms, COUNT_BIG(*) AS muestras, '
        'COUNT(s3_vrms_mm_s) AS muestras_sensor_3, '
        'AVG(rpm_ref) AS rpm_promedio, '
        'AVG(s1_vrms_mm_s) AS s1_vrms_promedio_mm_s, '
        'AVG(s2_vrms_mm_s) AS s2_vrms_promedio_mm_s, '
        'AVG(s3_vrms_mm_s) AS s3_vrms_promedio_mm_s, '
        'AVG(s1_arms_m_s2) AS s1_arms_promedio_m_s2, '
        'AVG(s2_arms_m_s2) AS s2_arms_promedio_m_s2, '
        'AVG(s3_arms_m_s2) AS s3_arms_promedio_m_s2, '
        'AVG(vfd_frecuencia_salida_hz) AS vfd_frecuencia_promedio_hz, '
        'AVG(corriente_vfd_a) AS corriente_vfd_promedio_a, '
        'AVG(vfd_voltaje_bus_dc_v) AS voltaje_bus_dc_promedio_v, '
        'AVG(medidor_frecuencia_hz) AS medidor_frecuencia_promedio_hz, '
        'AVG(medidor_corriente_l1_a) AS medidor_corriente_l1_promedio_a, '
        'AVG(medidor_corriente_l2_a) AS medidor_corriente_l2_promedio_a, '
        'AVG(vfd_regimen_hz) AS vfd_regimen_promedio_hz, '
        'MAX(vfd_cambio_hz_por_seg) AS vfd_cambio_hz_por_seg_max, '
        'SUM(CASE WHEN s1_sm1281_tiene_alarma = 1 THEN 1 ELSE 0 END) AS muestras_alarma_sensor_1, '
        'SUM(CASE WHEN s2_sm1281_tiene_alarma = 1 THEN 1 ELSE 0 END) AS muestras_alarma_sensor_2, '
        'SUM(CASE WHEN s3_sm1281_tiene_alarma = 1 THEN 1 ELSE 0 END) AS muestras_alarma_sensor_3, '
        'SUM(CASE WHEN s1_sm1281_tiene_aviso = 1 THEN 1 ELSE 0 END) AS muestras_aviso_sensor_1, '
        'SUM(CASE WHEN s2_sm1281_tiene_aviso = 1 THEN 1 ELSE 0 END) AS muestras_aviso_sensor_2, '
        'SUM(CASE WHEN s3_sm1281_tiene_aviso = 1 THEN 1 ELSE 0 END) AS muestras_aviso_sensor_3, '
        'MAX(indice_anomalia) AS indice_anomalia_max '
        'FROM serie GROUP BY bucket ORDER BY bucket ASC;'
    )
    with sql_connection() as con:
        return _rows(con.cursor().execute(query, bucket_ms, MODEL_NAME,
                                          version or '', after, bucket_ms))


def coverage_rows(hours: int = 24) -> dict | None:
    """Completitud por grupo para evitar confundir NULL con sensor averiado."""
    if not 1 <= hours <= 168:
        raise ValueError('hours debe estar entre 1 y 168')
    after = now_ms() - hours * 3600 * 1000
    query = (
        'SELECT COUNT_BIG(*) AS total, '
        'MAX(l.captura_unix_ms) AS ultima_captura_unix_ms, '
        'COUNT(l.s1_vrms_mm_s) AS s1_vrms, '
        'COUNT(l.s2_vrms_mm_s) AS s2_vrms, '
        'COUNT(l.s3_vrms_mm_s) AS s3_vrms, '
        'COUNT(l.rpm_sm1281) AS rpm_sm1281, '
        'COUNT(l.rpm_vfd) AS rpm_vfd, '
        'COUNT(l.vfd_frecuencia_salida_hz) AS vfd_hz, '
        'COUNT(l.corriente_vfd_a) AS corriente_vfd, '
        'COUNT(l.medidor_frecuencia_hz) AS medidor_hz, '
        'COUNT(l.medidor_corriente_l1_a) AS medidor_corriente_l1, '
        'COUNT(l.medidor_thd_voltaje_l1_raw) AS medidor_thd_raw ' +
        ' '.join([f', COUNT(l.[{col}]) AS {name}' for col,name in (
            ('sm1281_modulo_actualspeed_raw','modulo_speed_raw'),
            ('sm1281_cfg_speedsource','cfg_speedsource'),
            ('estado_operativo_detalle','estado_plc'),
            ('vfd_regimen_hz','regimen_vfd_hz'),
            ('vfd_cambio_hz_por_seg','derivada_vfd_hz'),
            ('s1_sm1281_mon_dkw_bits','s1_mon_dkw'),
            ('s2_sm1281_mon_dkw_bits','s2_mon_dkw'),
            ('s3_sm1281_mon_dkw_bits','s3_mon_dkw'),
            ('s1_sm1281_tiene_alarma','s1_flag_alarma'),
            ('s2_sm1281_tiene_alarma','s2_flag_alarma'),
            ('s3_sm1281_tiene_alarma','s3_flag_alarma'),
            ('s1_sm1281_sensor_conectado','s1_sensor_conectado'),
            ('s2_sm1281_sensor_conectado','s2_sensor_conectado'),
            ('s3_sm1281_sensor_conectado','s3_sensor_conectado'),
            ('db13_s1_vrms_mm_s','db13_s1_vrms'),
            ('db13_s2_vrms_mm_s','db13_s2_vrms'),
            ('db13_s3_vrms_mm_s','db13_s3_vrms'),
        )]) + ' '
        f'FROM {TABLE} AS l WHERE l.captura_unix_ms >= ?;'
    )
    with sql_connection() as con:
        return _row(con.cursor().execute(query, after))


def status_summary(hours: int = 24) -> dict:
    """Agregado sobre SQL; sin leer todas las filas ni alterar el historico."""
    if not 1 <= hours <= 168:
        raise ValueError('hours debe ser 1..168')
    after = now_ms() - hours * 3600 * 1000
    query = (
        'SELECT COUNT_BIG(*) AS total, '
        'SUM(CASE WHEN l.rpm_vfd > 20 OR l.vfd_frecuencia_salida_hz > 0.5 THEN 1 ELSE 0 END) AS vfd_con_giro, '
        'SUM(CASE WHEN (l.rpm_vfd = 0 OR l.rpm_vfd IS NULL) '
        'AND (l.vfd_frecuencia_salida_hz = 0 OR l.vfd_frecuencia_salida_hz IS NULL) '
        'AND l.vfd_voltaje_bus_dc_v >= 100 THEN 1 ELSE 0 END) AS parado_bus_energizado, '
        'SUM(CASE WHEN l.motor_activo = 1 AND l.rpm_vfd = 0 '
        'AND l.vfd_frecuencia_salida_hz = 0 THEN 1 ELSE 0 END) AS activos_etiquetados_sin_giro, '
        'SUM(CASE WHEN l.vfd_fault <> 0 THEN 1 ELSE 0 END) AS fallos_vfd_reportados, '
        "SUM(CASE WHEN l.modo_captura = 'POST_PARO' THEN 1 ELSE 0 END) AS capturas_post_paro, "
        'SUM(CASE WHEN l.s1_sm1281_tiene_alarma = 1 THEN 1 ELSE 0 END) AS s1_alarma_sm1281, '
        'SUM(CASE WHEN l.s2_sm1281_tiene_alarma = 1 THEN 1 ELSE 0 END) AS s2_alarma_sm1281, '
        'SUM(CASE WHEN l.s3_sm1281_tiene_alarma = 1 THEN 1 ELSE 0 END) AS s3_alarma_sm1281, '
        'SUM(CASE WHEN l.s1_sm1281_tiene_aviso = 1 THEN 1 ELSE 0 END) AS s1_aviso_sm1281, '
        'SUM(CASE WHEN l.s2_sm1281_tiene_aviso = 1 THEN 1 ELSE 0 END) AS s2_aviso_sm1281, '
        'SUM(CASE WHEN l.s3_sm1281_tiene_aviso = 1 THEN 1 ELSE 0 END) AS s3_aviso_sm1281, '
        "SUM(CASE WHEN l.estado_operativo_detalle = 'GIRO_ESTABLE_VFD' THEN 1 ELSE 0 END) AS estado_giro_estable_plc, "
        "SUM(CASE WHEN l.estado_operativo_detalle = 'CAMBIO_VELOCIDAD' THEN 1 ELSE 0 END) AS estado_cambio_velocidad_plc, "
        'COUNT(DISTINCT CASE WHEN l.vfd_frecuencia_salida_hz > 0.5 '
        'THEN CAST(ROUND(l.vfd_frecuencia_salida_hz / 2.0, 0) AS INT) END) AS bandas_hz_observadas '
        f'FROM {TABLE} AS l WHERE l.captura_unix_ms >= ?;'
    )
    with sql_connection() as con:
        return _row(con.cursor().execute(query, after)) or {}


def diagnostics_rows(hours: int = 24, limit: int = 200) -> list[dict]:
    """Consulta solo diagnosticos y los 3 espejos; no reentrena ni escribe."""
    if not (1 <= hours <= 168 and 1 <= limit <= 1000):
        raise ValueError('hours o limit fuera de rango')
    after = now_ms() - hours * 3600 * 1000
    query = (f'SELECT TOP (?) {SELECT_DIAGNOSTIC_COLUMNS} FROM {TABLE} AS l '
             'WHERE l.captura_unix_ms >= ? ORDER BY l.id DESC;')
    with sql_connection() as con:
        return list(reversed(_rows(con.cursor().execute(query, limit, after))))


def diagnostics_summary(hours: int = 24) -> dict:
    """Agrega alertas y cobertura desde SQL sin desplazar datos existentes."""
    if not 1 <= hours <= 168:
        raise ValueError('hours debe estar entre 1 y 168')
    after = now_ms() - hours * 3600 * 1000
    parts = [
        'COUNT_BIG(*) AS total',
        'MAX(l.captura_unix_ms) AS ultima_captura_unix_ms',
    ]
    for i in (1, 2, 3):
        parts.extend([
            f'COUNT(l.s{i}_sm1281_mon_dkw_bits) AS s{i}_mon_dkw_registrados',
            f'COUNT(l.db13_s{i}_vrms_mm_s) AS db13_s{i}_vrms_registrados',
            f'SUM(CASE WHEN l.s{i}_sm1281_tiene_alarma = 1 THEN 1 ELSE 0 END) AS s{i}_muestras_alarma',
            f'SUM(CASE WHEN l.s{i}_sm1281_tiene_aviso = 1 THEN 1 ELSE 0 END) AS s{i}_muestras_aviso',
            f'SUM(CASE WHEN l.s{i}_sm1281_sensor_conectado = 0 THEN 1 ELSE 0 END) AS s{i}_muestras_desconectado',
            f'SUM(CASE WHEN l.s{i}_sm1281_sensor_corto = 1 THEN 1 ELSE 0 END) AS s{i}_muestras_corto',
            f'SUM(CASE WHEN l.s{i}_sm1281_sensor_cable_roto = 1 THEN 1 ELSE 0 END) AS s{i}_muestras_cable_roto',
            f'SUM(CASE WHEN (l.s{i}_sm1281_mon_bpfo_bits & 1) = 1 THEN 1 ELSE 0 END) AS s{i}_bpfo_no_valido',
        ])
    query = 'SELECT ' + ', '.join(parts) + f' FROM {TABLE} AS l WHERE l.captura_unix_ms >= ?;'
    with sql_connection() as con:
        return _row(con.cursor().execute(query, after)) or {}

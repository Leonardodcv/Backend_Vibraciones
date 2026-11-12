"""Contrato de campos real de dbo.LecturasVibraciones (SQL 11-nov-2026).

Solo definiciones estaticas: no enviar nombres de columna proporcionados por HTTP a SQL.
"""
from __future__ import annotations

META = (
    'id', 'fecha_registro_utc', 'plc_ip', 'captura_unix_ms',
    'modo_captura', 'motor_activo',
)
SM1281 = ('rpm_sm1281', 'qc_rpm_sm1281', 'modo_sm1281')


def sensor_fields(i: int) -> tuple[str, ...]:
    if i not in (1, 2, 3):
        raise ValueError('Solo existen los canales 1, 2 y 3')
    p = f's{i}_'
    return (
        p + 'vrms_mm_s', p + 'arms_m_s2', p + 'dkw', p + 'peak_m_s2',
        p + 'qc_vrms', p + 'qc_arms', p + 'qc_dkw', p + 'factor_cresta',
    )


SENSOR_FIELDS = sensor_fields(1) + sensor_fields(2) + sensor_fields(3)
LEGACY_MOTOR = (
    'estado_vfd', 'orden_marcha_vfd', 'temperatura_motor_c',
    'corriente_motor_a', 'temperatura_devanado_c',
    'corriente_fase1_a', 'corriente_fase2_a',
)
VFD_FIELDS = (
    'rpm_vfd', 'corriente_vfd_a', 'vfd_ready', 'vfd_fault',
    'vfd_frecuencia_salida_hz', 'vfd_torque', 'vfd_potencia_actual',
    'vfd_energia_total_kwh', 'vfd_voltaje_bus_dc_v', 'vfd_voltaje_salida_v',
    'vfd_habilitado', 'vfd_ultima_falla', 'vfd_advertencia',
    'vfd_ultima_advertencia',
)
MEDIDOR_FIELDS = (
    'medidor_voltaje_l1_n', 'medidor_voltaje_l2_n', 'medidor_voltaje_l1_l2',
    'medidor_corriente_l1_a', 'medidor_corriente_l2_a',
    'medidor_potencia_activa_l1', 'medidor_potencia_activa_l2',
    'medidor_potencia_aparente_l1', 'medidor_potencia_aparente_l2',
    'medidor_frecuencia_hz',
    'medidor_energia_activa_l1', 'medidor_energia_activa_l2',
    'medidor_energia_aparente_l1', 'medidor_energia_aparente_l2',
    'medidor_energia_reactiva_l1', 'medidor_energia_reactiva_l2',
    'medidor_thd_voltaje_l1_raw', 'medidor_thd_voltaje_l2_raw',
    'medidor_thd_corriente_l1_raw', 'medidor_thd_corriente_l2_raw',
)
ALL_COLUMNS = META + SM1281 + SENSOR_FIELDS + LEGACY_MOTOR + VFD_FIELDS + MEDIDOR_FIELDS
assert len(ALL_COLUMNS) == 74 and len(set(ALL_COLUMNS)) == len(ALL_COLUMNS)

# Variables candidatas; solo se incluyen en ML tras verificar completitud/variabilidad.
VFD_CONTEXT_CANDIDATES = (
    'vfd_frecuencia_salida_hz', 'corriente_vfd_a', 'vfd_voltaje_bus_dc_v',
)

# Variables del medidor se exponen en la API, pero no se usan en ML mientras
# no se confirmen unidades, escalamiento y coherencia del equipo Jaritza.
COLUMNS_BY_GROUP = {
    'metadatos': META,
    'sm1281': SM1281,
    'sensor_1': sensor_fields(1),
    'sensor_2': sensor_fields(2),
    'sensor_3': sensor_fields(3),
    'motor_historico': LEGACY_MOTOR,
    'vfd': VFD_FIELDS,
    'medidor_electrico': MEDIDOR_FIELDS,
}

# Confirmado por capturas TIA 11-nov-2026. No incluye direcciones antiguas no
# verificadas para otros campos de DB23/DB187.
NEW_SENSOR_OFFSETS = {
    1: {'vrms_mm_s': 'DB23,REAL440', 'arms_m_s2': 'DB23,REAL444',
        'dkw': 'DB23,REAL448', 'peak_m_s2': 'DB23,REAL452',
        'qc_vrms': 'DB23,BYTE456', 'qc_arms': 'DB23,BYTE457', 'qc_dkw': 'DB23,BYTE458'},
    2: {'vrms_mm_s': 'DB23,REAL488', 'arms_m_s2': 'DB23,REAL492',
        'dkw': 'DB23,REAL496', 'peak_m_s2': 'DB23,REAL500',
        'qc_vrms': 'DB23,BYTE504', 'qc_arms': 'DB23,BYTE505', 'qc_dkw': 'DB23,BYTE506'},
    3: {'vrms_mm_s': 'DB23,REAL536', 'arms_m_s2': 'DB23,REAL540',
        'dkw': 'DB23,REAL544', 'peak_m_s2': 'DB23,REAL548',
        'qc_vrms': 'DB23,BYTE552', 'qc_arms': 'DB23,BYTE553', 'qc_dkw': 'DB23,BYTE554'},
}


# v1.3: columnas del script Node-RED/SQL SM1281 v1.3.2, en su orden exacto.
# Generadas del 01_SQL_MIGRACION_ADITIVA.sql validado, no de datos HTTP.
NEW_COLUMNS = (
    'sm1281_drive1_velocity_raw',
    'sm1281_drive1_speed_ch1_raw',
    'sm1281_drive1_speed_ch2_raw',
    'sm1281_drive1_speed_ch3_raw',
    'sm1281_drive1_speed_ch4_raw',
    'sm1281_drive1_error',
    'sm1281_drive1_error_id',
    'sm1281_modulo_actualspeed_raw',
    'sm1281_modulo_qc_speed',
    'sm1281_modulo_opmode',
    'sm1281_modulo_state_opmode_change',
    'sm1281_modulo_state_raw_rec',
    'sm1281_modulo_state_raw_send',
    'sm1281_modulo_systemstate_bits',
    'sm1281_cfg_speedsource',
    'sm1281_cfg_pulsos_por_vuelta',
    's1_sm1281_mon_vrms_bits',
    's1_sm1281_mon_arms_bits',
    's1_sm1281_mon_dkw_bits',
    's1_sm1281_mon_espectro_a_bits',
    's1_sm1281_mon_espectro_v_bits',
    's1_sm1281_mon_envolvente_bits',
    's1_sm1281_mon_bpfo_bits',
    's1_sm1281_mon_bpfi_bits',
    's1_sm1281_mon_ftf_bits',
    's1_sm1281_mon_bsf_bits',
    's1_sm1281_sensorstate_bits',
    's1_sm1281_faulttype_bits',
    's1_sm1281_sensoroffset_raw',
    's1_cfg_sensibilidad_mvg',
    's1_cfg_speedratio',
    's1_cfg_alarma_arms_m_s2',
    's1_cfg_aviso_arms_m_s2',
    's1_cfg_alarma_vrms_mm_s',
    's1_cfg_aviso_vrms_mm_s',
    's1_cfg_alarma_dkw',
    's1_cfg_aviso_dkw',
    's2_sm1281_mon_vrms_bits',
    's2_sm1281_mon_arms_bits',
    's2_sm1281_mon_dkw_bits',
    's2_sm1281_mon_espectro_a_bits',
    's2_sm1281_mon_espectro_v_bits',
    's2_sm1281_mon_envolvente_bits',
    's2_sm1281_mon_bpfo_bits',
    's2_sm1281_mon_bpfi_bits',
    's2_sm1281_mon_ftf_bits',
    's2_sm1281_mon_bsf_bits',
    's2_sm1281_sensorstate_bits',
    's2_sm1281_faulttype_bits',
    's2_sm1281_sensoroffset_raw',
    's2_cfg_sensibilidad_mvg',
    's2_cfg_speedratio',
    's2_cfg_alarma_arms_m_s2',
    's2_cfg_aviso_arms_m_s2',
    's2_cfg_alarma_vrms_mm_s',
    's2_cfg_aviso_vrms_mm_s',
    's2_cfg_alarma_dkw',
    's2_cfg_aviso_dkw',
    's3_sm1281_mon_vrms_bits',
    's3_sm1281_mon_arms_bits',
    's3_sm1281_mon_dkw_bits',
    's3_sm1281_mon_espectro_a_bits',
    's3_sm1281_mon_espectro_v_bits',
    's3_sm1281_mon_envolvente_bits',
    's3_sm1281_mon_bpfo_bits',
    's3_sm1281_mon_bpfi_bits',
    's3_sm1281_mon_ftf_bits',
    's3_sm1281_mon_bsf_bits',
    's3_sm1281_sensorstate_bits',
    's3_sm1281_faulttype_bits',
    's3_sm1281_sensoroffset_raw',
    's3_cfg_sensibilidad_mvg',
    's3_cfg_speedratio',
    's3_cfg_alarma_arms_m_s2',
    's3_cfg_aviso_arms_m_s2',
    's3_cfg_alarma_vrms_mm_s',
    's3_cfg_aviso_vrms_mm_s',
    's3_cfg_alarma_dkw',
    's3_cfg_aviso_dkw',
    's1_sm1281_tiene_aviso',
    's1_sm1281_tiene_alarma',
    's1_sm1281_sensor_conectado',
    's1_sm1281_sensor_corto',
    's1_sm1281_sensor_cable_roto',
    's2_sm1281_tiene_aviso',
    's2_sm1281_tiene_alarma',
    's2_sm1281_sensor_conectado',
    's2_sm1281_sensor_corto',
    's2_sm1281_sensor_cable_roto',
    's3_sm1281_tiene_aviso',
    's3_sm1281_tiene_alarma',
    's3_sm1281_sensor_conectado',
    's3_sm1281_sensor_corto',
    's3_sm1281_sensor_cable_roto',
    'estado_operativo_detalle',
    'vfd_regimen_hz',
    'vfd_cambio_hz_por_seg',
    'vfd_bus_dc_presente',
    'db13_s1_vrms_mm_s',
    'db13_s1_arms_m_s2',
    'db13_s1_dkw',
    'db13_s1_peak_m_s2',
    'db13_s1_qc_vrms',
    'db13_s1_qc_arms',
    'db13_s1_qc_dkw',
    'db13_s2_vrms_mm_s',
    'db13_s2_arms_m_s2',
    'db13_s2_dkw',
    'db13_s2_peak_m_s2',
    'db13_s2_qc_vrms',
    'db13_s2_qc_arms',
    'db13_s2_qc_dkw',
    'db13_s3_vrms_mm_s',
    'db13_s3_arms_m_s2',
    'db13_s3_dkw',
    'db13_s3_peak_m_s2',
    'db13_s3_qc_vrms',
    'db13_s3_qc_arms',
    'db13_s3_qc_dkw',
)
NEW_COLUMN_TYPES = {
    'sm1281_drive1_velocity_raw': 'FLOAT',
    'sm1281_drive1_speed_ch1_raw': 'FLOAT',
    'sm1281_drive1_speed_ch2_raw': 'FLOAT',
    'sm1281_drive1_speed_ch3_raw': 'FLOAT',
    'sm1281_drive1_speed_ch4_raw': 'FLOAT',
    'sm1281_drive1_error': 'BIT',
    'sm1281_drive1_error_id': 'SMALLINT',
    'sm1281_modulo_actualspeed_raw': 'FLOAT',
    'sm1281_modulo_qc_speed': 'TINYINT',
    'sm1281_modulo_opmode': 'TINYINT',
    'sm1281_modulo_state_opmode_change': 'TINYINT',
    'sm1281_modulo_state_raw_rec': 'TINYINT',
    'sm1281_modulo_state_raw_send': 'TINYINT',
    'sm1281_modulo_systemstate_bits': 'BIGINT',
    'sm1281_cfg_speedsource': 'TINYINT',
    'sm1281_cfg_pulsos_por_vuelta': 'INT',
    's1_sm1281_mon_vrms_bits': 'TINYINT',
    's1_sm1281_mon_arms_bits': 'TINYINT',
    's1_sm1281_mon_dkw_bits': 'TINYINT',
    's1_sm1281_mon_espectro_a_bits': 'TINYINT',
    's1_sm1281_mon_espectro_v_bits': 'TINYINT',
    's1_sm1281_mon_envolvente_bits': 'TINYINT',
    's1_sm1281_mon_bpfo_bits': 'TINYINT',
    's1_sm1281_mon_bpfi_bits': 'TINYINT',
    's1_sm1281_mon_ftf_bits': 'TINYINT',
    's1_sm1281_mon_bsf_bits': 'TINYINT',
    's1_sm1281_sensorstate_bits': 'TINYINT',
    's1_sm1281_faulttype_bits': 'TINYINT',
    's1_sm1281_sensoroffset_raw': 'FLOAT',
    's1_cfg_sensibilidad_mvg': 'FLOAT',
    's1_cfg_speedratio': 'FLOAT',
    's1_cfg_alarma_arms_m_s2': 'FLOAT',
    's1_cfg_aviso_arms_m_s2': 'FLOAT',
    's1_cfg_alarma_vrms_mm_s': 'FLOAT',
    's1_cfg_aviso_vrms_mm_s': 'FLOAT',
    's1_cfg_alarma_dkw': 'FLOAT',
    's1_cfg_aviso_dkw': 'FLOAT',
    's2_sm1281_mon_vrms_bits': 'TINYINT',
    's2_sm1281_mon_arms_bits': 'TINYINT',
    's2_sm1281_mon_dkw_bits': 'TINYINT',
    's2_sm1281_mon_espectro_a_bits': 'TINYINT',
    's2_sm1281_mon_espectro_v_bits': 'TINYINT',
    's2_sm1281_mon_envolvente_bits': 'TINYINT',
    's2_sm1281_mon_bpfo_bits': 'TINYINT',
    's2_sm1281_mon_bpfi_bits': 'TINYINT',
    's2_sm1281_mon_ftf_bits': 'TINYINT',
    's2_sm1281_mon_bsf_bits': 'TINYINT',
    's2_sm1281_sensorstate_bits': 'TINYINT',
    's2_sm1281_faulttype_bits': 'TINYINT',
    's2_sm1281_sensoroffset_raw': 'FLOAT',
    's2_cfg_sensibilidad_mvg': 'FLOAT',
    's2_cfg_speedratio': 'FLOAT',
    's2_cfg_alarma_arms_m_s2': 'FLOAT',
    's2_cfg_aviso_arms_m_s2': 'FLOAT',
    's2_cfg_alarma_vrms_mm_s': 'FLOAT',
    's2_cfg_aviso_vrms_mm_s': 'FLOAT',
    's2_cfg_alarma_dkw': 'FLOAT',
    's2_cfg_aviso_dkw': 'FLOAT',
    's3_sm1281_mon_vrms_bits': 'TINYINT',
    's3_sm1281_mon_arms_bits': 'TINYINT',
    's3_sm1281_mon_dkw_bits': 'TINYINT',
    's3_sm1281_mon_espectro_a_bits': 'TINYINT',
    's3_sm1281_mon_espectro_v_bits': 'TINYINT',
    's3_sm1281_mon_envolvente_bits': 'TINYINT',
    's3_sm1281_mon_bpfo_bits': 'TINYINT',
    's3_sm1281_mon_bpfi_bits': 'TINYINT',
    's3_sm1281_mon_ftf_bits': 'TINYINT',
    's3_sm1281_mon_bsf_bits': 'TINYINT',
    's3_sm1281_sensorstate_bits': 'TINYINT',
    's3_sm1281_faulttype_bits': 'TINYINT',
    's3_sm1281_sensoroffset_raw': 'FLOAT',
    's3_cfg_sensibilidad_mvg': 'FLOAT',
    's3_cfg_speedratio': 'FLOAT',
    's3_cfg_alarma_arms_m_s2': 'FLOAT',
    's3_cfg_aviso_arms_m_s2': 'FLOAT',
    's3_cfg_alarma_vrms_mm_s': 'FLOAT',
    's3_cfg_aviso_vrms_mm_s': 'FLOAT',
    's3_cfg_alarma_dkw': 'FLOAT',
    's3_cfg_aviso_dkw': 'FLOAT',
    's1_sm1281_tiene_aviso': 'BIT',
    's1_sm1281_tiene_alarma': 'BIT',
    's1_sm1281_sensor_conectado': 'BIT',
    's1_sm1281_sensor_corto': 'BIT',
    's1_sm1281_sensor_cable_roto': 'BIT',
    's2_sm1281_tiene_aviso': 'BIT',
    's2_sm1281_tiene_alarma': 'BIT',
    's2_sm1281_sensor_conectado': 'BIT',
    's2_sm1281_sensor_corto': 'BIT',
    's2_sm1281_sensor_cable_roto': 'BIT',
    's3_sm1281_tiene_aviso': 'BIT',
    's3_sm1281_tiene_alarma': 'BIT',
    's3_sm1281_sensor_conectado': 'BIT',
    's3_sm1281_sensor_corto': 'BIT',
    's3_sm1281_sensor_cable_roto': 'BIT',
    'estado_operativo_detalle': 'VARCHAR(40)',
    'vfd_regimen_hz': 'FLOAT',
    'vfd_cambio_hz_por_seg': 'FLOAT',
    'vfd_bus_dc_presente': 'BIT',
    'db13_s1_vrms_mm_s': 'FLOAT',
    'db13_s1_arms_m_s2': 'FLOAT',
    'db13_s1_dkw': 'FLOAT',
    'db13_s1_peak_m_s2': 'FLOAT',
    'db13_s1_qc_vrms': 'TINYINT',
    'db13_s1_qc_arms': 'TINYINT',
    'db13_s1_qc_dkw': 'TINYINT',
    'db13_s2_vrms_mm_s': 'FLOAT',
    'db13_s2_arms_m_s2': 'FLOAT',
    'db13_s2_dkw': 'FLOAT',
    'db13_s2_peak_m_s2': 'FLOAT',
    'db13_s2_qc_vrms': 'TINYINT',
    'db13_s2_qc_arms': 'TINYINT',
    'db13_s2_qc_dkw': 'TINYINT',
    'db13_s3_vrms_mm_s': 'FLOAT',
    'db13_s3_arms_m_s2': 'FLOAT',
    'db13_s3_dkw': 'FLOAT',
    'db13_s3_peak_m_s2': 'FLOAT',
    'db13_s3_qc_vrms': 'TINYINT',
    'db13_s3_qc_arms': 'TINYINT',
    'db13_s3_qc_dkw': 'TINYINT',
}
NEW_GROUPS = {
    'velocidad_y_modulo_sm1281': ('sm1281_drive1_velocity_raw', 'sm1281_drive1_speed_ch1_raw', 'sm1281_drive1_speed_ch2_raw', 'sm1281_drive1_speed_ch3_raw', 'sm1281_drive1_speed_ch4_raw', 'sm1281_drive1_error', 'sm1281_drive1_error_id', 'sm1281_modulo_actualspeed_raw', 'sm1281_modulo_qc_speed', 'sm1281_modulo_opmode', 'sm1281_modulo_state_opmode_change', 'sm1281_modulo_state_raw_rec', 'sm1281_modulo_state_raw_send', 'sm1281_modulo_systemstate_bits', 'sm1281_cfg_speedsource', 'sm1281_cfg_pulsos_por_vuelta'),
    'diagnostico_sm1281_sensor_1': ('s1_sm1281_mon_vrms_bits', 's1_sm1281_mon_arms_bits', 's1_sm1281_mon_dkw_bits', 's1_sm1281_mon_espectro_a_bits', 's1_sm1281_mon_espectro_v_bits', 's1_sm1281_mon_envolvente_bits', 's1_sm1281_mon_bpfo_bits', 's1_sm1281_mon_bpfi_bits', 's1_sm1281_mon_ftf_bits', 's1_sm1281_mon_bsf_bits', 's1_sm1281_sensorstate_bits', 's1_sm1281_faulttype_bits', 's1_sm1281_sensoroffset_raw', 's1_sm1281_tiene_aviso', 's1_sm1281_tiene_alarma', 's1_sm1281_sensor_conectado', 's1_sm1281_sensor_corto', 's1_sm1281_sensor_cable_roto'),
    'diagnostico_sm1281_sensor_2': ('s2_sm1281_mon_vrms_bits', 's2_sm1281_mon_arms_bits', 's2_sm1281_mon_dkw_bits', 's2_sm1281_mon_espectro_a_bits', 's2_sm1281_mon_espectro_v_bits', 's2_sm1281_mon_envolvente_bits', 's2_sm1281_mon_bpfo_bits', 's2_sm1281_mon_bpfi_bits', 's2_sm1281_mon_ftf_bits', 's2_sm1281_mon_bsf_bits', 's2_sm1281_sensorstate_bits', 's2_sm1281_faulttype_bits', 's2_sm1281_sensoroffset_raw', 's2_sm1281_tiene_aviso', 's2_sm1281_tiene_alarma', 's2_sm1281_sensor_conectado', 's2_sm1281_sensor_corto', 's2_sm1281_sensor_cable_roto'),
    'diagnostico_sm1281_sensor_3': ('s3_sm1281_mon_vrms_bits', 's3_sm1281_mon_arms_bits', 's3_sm1281_mon_dkw_bits', 's3_sm1281_mon_espectro_a_bits', 's3_sm1281_mon_espectro_v_bits', 's3_sm1281_mon_envolvente_bits', 's3_sm1281_mon_bpfo_bits', 's3_sm1281_mon_bpfi_bits', 's3_sm1281_mon_ftf_bits', 's3_sm1281_mon_bsf_bits', 's3_sm1281_sensorstate_bits', 's3_sm1281_faulttype_bits', 's3_sm1281_sensoroffset_raw', 's3_sm1281_tiene_aviso', 's3_sm1281_tiene_alarma', 's3_sm1281_sensor_conectado', 's3_sm1281_sensor_corto', 's3_sm1281_sensor_cable_roto'),
    'configuracion_sensor_1': ('s1_cfg_sensibilidad_mvg', 's1_cfg_speedratio', 's1_cfg_alarma_arms_m_s2', 's1_cfg_aviso_arms_m_s2', 's1_cfg_alarma_vrms_mm_s', 's1_cfg_aviso_vrms_mm_s', 's1_cfg_alarma_dkw', 's1_cfg_aviso_dkw'),
    'configuracion_sensor_2': ('s2_cfg_sensibilidad_mvg', 's2_cfg_speedratio', 's2_cfg_alarma_arms_m_s2', 's2_cfg_aviso_arms_m_s2', 's2_cfg_alarma_vrms_mm_s', 's2_cfg_aviso_vrms_mm_s', 's2_cfg_alarma_dkw', 's2_cfg_aviso_dkw'),
    'configuracion_sensor_3': ('s3_cfg_sensibilidad_mvg', 's3_cfg_speedratio', 's3_cfg_alarma_arms_m_s2', 's3_cfg_aviso_arms_m_s2', 's3_cfg_alarma_vrms_mm_s', 's3_cfg_aviso_vrms_mm_s', 's3_cfg_alarma_dkw', 's3_cfg_aviso_dkw'),
    'estado_operativo_plc': ('estado_operativo_detalle', 'vfd_regimen_hz', 'vfd_cambio_hz_por_seg', 'vfd_bus_dc_presente'),
    'espejo_db13_sensor_1': ('db13_s1_vrms_mm_s', 'db13_s1_arms_m_s2', 'db13_s1_dkw', 'db13_s1_peak_m_s2', 'db13_s1_qc_vrms', 'db13_s1_qc_arms', 'db13_s1_qc_dkw'),
    'espejo_db13_sensor_2': ('db13_s2_vrms_mm_s', 'db13_s2_arms_m_s2', 'db13_s2_dkw', 'db13_s2_peak_m_s2', 'db13_s2_qc_vrms', 'db13_s2_qc_arms', 'db13_s2_qc_dkw'),
    'espejo_db13_sensor_3': ('db13_s3_vrms_mm_s', 'db13_s3_arms_m_s2', 'db13_s3_dkw', 'db13_s3_peak_m_s2', 'db13_s3_qc_vrms', 'db13_s3_qc_arms', 'db13_s3_qc_dkw'),
}

OLD_COLUMNS = ALL_COLUMNS
ALL_COLUMNS = OLD_COLUMNS + NEW_COLUMNS
COLUMNS_BY_GROUP = {**COLUMNS_BY_GROUP, **NEW_GROUPS}
assert len(ALL_COLUMNS) == 193 and len(set(ALL_COLUMNS)) == 193
assert sum(map(len, COLUMNS_BY_GROUP.values())) == 193

# Entrenamiento/inferencia requiere un subconjunto estatico para evitar
# cargar 193 columnas x 200,000 filas en memoria. Las API devuelven todas.
MODEL_BASE = ('id','fecha_registro_utc','captura_unix_ms','modo_captura',
              'motor_activo','rpm_sm1281','qc_rpm_sm1281','rpm_vfd',
              'vfd_frecuencia_salida_hz','vfd_voltaje_bus_dc_v','vfd_fault',
              'orden_marcha_vfd','estado_operativo_detalle')
MODEL_SENSOR_FIELDS = tuple(
    f's{i}_{name}' for i in (1,2,3)
    for name in ('vrms_mm_s','arms_m_s2','peak_m_s2','dkw',
                 'qc_vrms','qc_arms','qc_dkw')
)
MODEL_DIAG_FIELDS = tuple(
    f's{i}_sm1281_{name}' for i in (1,2,3)
    for name in ('mon_vrms_bits','mon_arms_bits','mon_dkw_bits',
                 'mon_espectro_a_bits','mon_espectro_v_bits',
                 'mon_envolvente_bits','mon_bpfo_bits','mon_bpfi_bits',
                 'mon_ftf_bits','mon_bsf_bits',
                 'sensorstate_bits','faulttype_bits',
                 'tiene_aviso','tiene_alarma','sensor_conectado',
                 'sensor_corto','sensor_cable_roto')
)
MODEL_DB13_FIELDS = tuple(
    f'db13_s{i}_{name}' for i in (1,2,3)
    for name in ('vrms_mm_s','arms_m_s2','dkw','peak_m_s2',
                 'qc_vrms','qc_arms','qc_dkw')
)
MODEL_COLUMNS = tuple(dict.fromkeys(
    MODEL_BASE + MODEL_SENSOR_FIELDS + MODEL_DIAG_FIELDS + MODEL_DB13_FIELDS
))
assert set(MODEL_COLUMNS).issubset(ALL_COLUMNS)

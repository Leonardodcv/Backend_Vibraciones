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

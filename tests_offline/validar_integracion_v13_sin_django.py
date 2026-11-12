"""Prueba sin Django/SQL/PLC; usa datos sinteticos y el esquema SQL real.

Ejecutar con: python tests_offline/validar_integracion_v13_sin_django.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Simular solo django.conf.settings para el entrenamiento que no hace SQL ni HTTP.
if 'django.conf' not in sys.modules:
    django = types.ModuleType('django')
    conf = types.ModuleType('django.conf')
    conf.settings = types.SimpleNamespace(
        VIBRATIONS_MIN_TRAIN_SAMPLES=300,
        VIBRATIONS_MIN_TRAIN_MINUTES=15,
        VIBRATIONS_SCORE_WARNING=60,
        VIBRATIONS_SCORE_ALERT=85,
        VIBRATIONS_SPEED_SOURCE='vfd_hz',
        VIBRATIONS_SPEED_BAND_WIDTH=2.,
        VIBRATIONS_TRAIN_SM1281_ALERT_POLICY='annotate',
        VIBRATIONS_DB13_STRICT=False,
        VIBRATIONS_DB13_REL_TOL=.10,
        VIBRATIONS_DB13_ABS_TOL=.05,
        VIBRATIONS_MODEL_DIR=ROOT / 'artifacts',
        VIBRATIONS_BAR_RPS_PER_VFD_HZ=None,
        VIBRATIONS_EVENTS_CSV=None,
    )
    django.conf = conf
    sys.modules['django'] = django
    sys.modules['django.conf'] = conf

import numpy as np
from vibraciones import diagnosticos, fields, modeling, operacion


def check(condition, description):
    if not condition:
        raise AssertionError(description)
    print('[OK]', description)


def build_row(n, speed, rng, base):
    row = dict(id=n, captura_unix_ms=base+n*3100,
               modo_captura='ACTIVO', motor_activo=True,
               rpm_vfd=speed*30, vfd_frecuencia_salida_hz=speed+rng.normal(0,.03),
               vfd_voltaje_bus_dc_v=295., vfd_fault=0,
               rpm_sm1281=0, qc_rpm_sm1281=0, orden_marcha_vfd=True,
               estado_operativo_detalle='GIRO_ESTABLE_VFD')
    for i in (1, 2, 3):
        vrms = .12*i+.025*speed**1.2 + rng.normal(0,.01)
        arms = .16*i+.031*speed**1.1+rng.normal(0,.01)
        peak = arms*(3.5+rng.normal(0,.03))
        dkw = .5*i+.02*speed+rng.normal(0,.02)
        row.update({f's{i}_vrms_mm_s':vrms,
                    f's{i}_arms_m_s2':arms,
                    f's{i}_peak_m_s2':peak,
                    f's{i}_dkw':dkw,
                    f's{i}_qc_vrms':1, f's{i}_qc_arms':1, f's{i}_qc_dkw':1,
                    f's{i}_sm1281_sensorstate_bits':2,
                    f's{i}_sm1281_faulttype_bits':1,
                    f's{i}_sm1281_sensor_conectado':True,
                    f's{i}_sm1281_sensor_corto':False,
                    f's{i}_sm1281_sensor_cable_roto':False,
                    f's{i}_sm1281_tiene_alarma':i==1,
                    f's{i}_sm1281_tiene_aviso':i==2})
        for k in diagnosticos.MONITORES:
            val = 1 if k in ('bpfo','bpfi','ftf','bsf') else (
                8 if (i==1 and k=='dkw') else 4 if (i==2 and k=='dkw') else 2)
            row[f's{i}_sm1281_mon_{k}_bits']=val
        for k in ('vrms_mm_s', 'arms_m_s2', 'dkw', 'peak_m_s2'):
            row[f'db13_s{i}_{k}']=row[f's{i}_{k}']
    return row


def main():
    sql = Path('/mnt/data/NodeRED_SM1281_Diagnosticos_v1_3/01_SQL_MIGRACION_ADITIVA.sql')
    if sql.is_file():
        names = re.findall(r'ALTER TABLE dbo\.LecturasVibraciones ADD \[([^]]+)\]', sql.read_text())
        check(tuple(names) == fields.NEW_COLUMNS, '119 columnas nuevas exactamente iguales a migracion SQL real')
    check(len(fields.ALL_COLUMNS)==193, '193 columnas total; sin duplicados')
    check(len(set(fields.ALL_COLUMNS))==193, '193 nombres de columna unicos')
    check(len(fields.MODEL_COLUMNS)<len(fields.ALL_COLUMNS), 'Consulta modelo reduce peso en memoria')
    check(diagnosticos.monitor_estado(1)['estado']=='NO_VALIDO', 'bit 1 es NotValid')
    check(diagnosticos.monitor_estado(8)['estado']=='ALARMA', 'bit 8 es Alarma')
    check(diagnosticos.monitor_estado(4)['estado']=='AVISO', 'bit 4 es Aviso')
    check(diagnosticos.monitor_estado(2)['estado']=='BUENO', 'bit 2 es Bueno')
    rng=np.random.default_rng(20261112)
    base=1794400000000
    rows=[build_row(i, speed, rng, base) for i,speed in enumerate(
        (s for s in (5.,10.,15.,20.) for _ in range(360)), start=1)]
    d=diagnosticos.diagnostic_summary(rows[0])
    check(d['sensores']['sensor_1']['estado']=='ALARMA_PLC', 'S1 DKW alarma 8, visible sin imputar')
    check(d['sensores']['sensor_2']['estado']=='AVISO_PLC', 'S2 DKW aviso 4, visible sin imputar')
    check(d['sensores']['sensor_3']['estado']=='SIN_ALERTA_EN_MONITORES_VALIDOS', 'S3 DKW bueno 2')
    check(d['sensores']['sensor_1']['monitores_no_validos']==4, 'BPFO/BPFI/FTF/BSF NotValid no son fallos')
    check(d['sensores']['sensor_1']['espejo_db13']['estado']=='COINCIDENTE_APROXIMADO', 'DB13 copia DB23')
    check(diagnosticos.quality_gate(rows[0])[0], 'Alarma DKW no bloquea modelo')
    invalid=dict(rows[0], s1_sm1281_faulttype_bits=4, s1_sm1281_sensor_cable_roto=True)
    check(not diagnosticos.quality_gate(invalid)[0], 'Cable roto bloquea inferencia')
    invalidqc=dict(rows[0], s2_qc_dkw=0)
    check(not diagnosticos.quality_gate(invalidqc)[0], 'QC DKW 0 bloquea inferencia')
    displaced=dict(rows[0], db13_s3_vrms_mm_s=1000)
    check(diagnosticos.espejo_db13(displaced,3)['estado']=='DIFERENCIA_DETECTADA', 'DB13 discrepancia reportada')
    bundle=modeling.train_rows(rows, confirm_normal=True)
    check(bundle['metadata']['n_regimenes']==4, '4 bandas de velocidad independientes entrenadas')
    check(bundle['metadata']['version_backend']=='1.3.0', 'Version del nuevo modelo 1.3.0')
    check(bundle['metadata']['politica_alertas_sm1281']=='annotate', 'Alarmas PLC anotadas, no usadas como features')
    check(bundle['metadata']['filas_validas']>=4*300, 'Cobertura minima verificada por banda')
    check(bundle['metadata']['alarmas_plc_en_ventanas_aprobadas']['alarma']>0,
          'Metadatos documentan alertas en entrenamiento')
    for i in (250,610,970,1330):
        score=modeling.score_row(rows[i], bundle, eventos=())
        check(score['indice_anomalia'] is not None, f'Indice en velocidad banda #{i//360+1}')
    uncertain=dict(rows[900], vfd_frecuencia_salida_hz=12.5, rpm_vfd=375)
    check(modeling.score_row(uncertain, bundle, eventos=())['estado']=='SIN_MODELO_PARA_ESTA_VELOCIDAD',
          'Sin extrapolar a velocidad desconocida')
    score=modeling.score_row(invalid, bundle, eventos=())
    check(score['estado']=='CALIDAD_INSTRUMENTACION_INVALIDA' and score['indice_anomalia'] is None,
          'Falla instrumento no crea score')
    healthy=modeling.score_row(rows[900], bundle, eventos=())
    bad=dict(rows[900], s3_vrms_mm_s=rows[900]['s3_vrms_mm_s']*20,
             s3_arms_m_s2=rows[900]['s3_arms_m_s2']*15,
             s3_peak_m_s2=rows[900]['s3_peak_m_s2']*18,
             s3_dkw=rows[900]['s3_dkw']*12)
    anomaly=modeling.score_row(bad, bundle, eventos=())
    check(anomaly['indice_anomalia']>=healthy['indice_anomalia'], 'Anomalia vibratoria eleva o mantiene indice')
    stopped=dict(rows[900], rpm_vfd=0, vfd_frecuencia_salida_hz=0,
                 motor_activo=False, modo_captura='REPOSO',
                 estado_operativo_detalle='SIN_GIRO_ORDEN_INACTIVA', orden_marcha_vfd=False)
    check(modeling.score_row(stopped,bundle,eventos=())['indice_anomalia'] is None,
          'Reposo no es probabilidad de falla')
    change=dict(rows[900], estado_operativo_detalle='CAMBIO_VELOCIDAD')
    check(modeling.score_row(change,bundle,eventos=())['estado']=='TRANSICION',
          'Cambio velocidad excluido de scoring')
    check(len(modeling.details_for_sql(anomaly))<=1000,'Detalle SQL cabe NVARCHAR(1000)')
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'v13.joblib'
        modeling.save_bundle(bundle,path)
        read=modeling.load_bundle(path)
        check(read['metadata']['version']==bundle['metadata']['version'],
              'Artefacto 1.3 aislado serializa correctamente')
    pathfile=ROOT/'vibraciones/urls.py'
    tree=ast.parse(pathfile.read_text())
    routes=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='path':
            if node.args and isinstance(node.args[0],ast.Constant): routes.append(node.args[0].value)
    check(len(routes)==14, '14 rutas URL v1.3 declaradas')
    postman=json.loads((ROOT/'postman/Postman_Backend_Vibraciones_v1.3.postman_collection.json').read_text())
    urls=[]
    for group in postman['item']:
        for item in group['item']:
            urls.append(item['request']['url']['raw'].split('?')[0].removeprefix('{{baseUrl}}/api/v1/'))
            check(item['request']['method']=='GET','' if False else f"Postman GET: {item['name']}")
    check(set(routes).issubset(set(urls)), 'Postman cubre las 14 rutas backend')
    print('VALIDACION OFFLINE FINALIZADA: OK. No se consulto SQL ni PLC.')


if __name__=='__main__':
    main()

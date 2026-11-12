"""Pruebas ejecutables sin Django/pyodbc: python tests_offline/validar_modelo_sin_django.py.
Solo suple `django.conf.settings`; nunca se conecta al PLC ni a SQL.
"""
from __future__ import annotations

import csv
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def settings_for(**changes):
    return types.SimpleNamespace(
        VIBRATIONS_MIN_TRAIN_SAMPLES=300, VIBRATIONS_MIN_TRAIN_MINUTES=15,
        VIBRATIONS_SPEED_BAND_WIDTH=2.0, VIBRATIONS_SPEED_SOURCE='vfd_hz',
        VIBRATIONS_BAR_RPS_PER_VFD_HZ=None,
        VIBRATIONS_SCORE_ALERT=85, VIBRATIONS_SCORE_WARNING=60,
        VIBRATIONS_MODEL_DIR=ROOT / 'artifacts',
        VIBRATIONS_EVENTS_CSV=None,
        **changes,
    )

django = types.ModuleType('django')
conf = types.ModuleType('django.conf')
conf.settings = settings_for()
django.conf = conf
sys.modules['django'] = django
sys.modules['django.conf'] = conf

from vibraciones import modeling, operacion  # noqa: E402

rng = np.random.default_rng(20261112)
start = int(datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp() * 1000)


def fake_row(i: int, hz: float, *, rest: bool = False) -> dict:
    rpm = 0 if rest else hz * 30 + rng.normal(0, 1.7)
    row = {
        'id': i+1, 'captura_unix_ms': start + i*3000,
        'modo_captura': 'REPOSO' if rest else 'ACTIVO',
        'motor_activo': not rest,
        'rpm_vfd': rpm, 'rpm_sm1281': 0, 'qc_rpm_sm1281': 0,
        'vfd_frecuencia_salida_hz': 0 if rest else hz + rng.normal(0, 0.03),
        'vfd_voltaje_bus_dc_v': 310 + rng.normal(0, 3),
        'vfd_fault': 0, 'orden_marcha_vfd': False if rest else True,
    }
    for j in (1, 2, 3):
        # La amplitud normal CRECE con velocidad de forma pronunciada.
        vrms = (0.008 + abs(rng.normal(0, .002))) if rest else (
            .12 * j + .022*hz**1.3 + rng.normal(0, .03))
        arms = .001 if rest else .15*j + .02*hz**1.22 + rng.normal(0, .025)
        row.update({
            f's{j}_vrms_mm_s': max(0., vrms),
            f's{j}_arms_m_s2': max(.0001, arms),
            f's{j}_peak_m_s2': max(.0001, arms)*(3.5+rng.normal(0,.09)),
            f's{j}_dkw': .1*j+.02*hz+rng.normal(0,.025),
        })
    return row


def validate():
    rows=[]
    for hz in (5., 10., 15., 20.):
        for i in range(500):
            rows.append(fake_row(len(rows), hz))
    for i, r in enumerate(rows):
        r['id']=i+1
        r['captura_unix_ms']=start+i*3000
    with tempfile.TemporaryDirectory() as d:
        file = Path(d) / 'eventos.csv'
        cols=['inicio_utc','fin_utc','estado_real','barra_rps','normal_confirmado','descripcion']
        with file.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
            for k, hz in enumerate((5., 10., 15., 20.)):
                begin = datetime.fromtimestamp((start+k*500*3000)/1000, timezone.utc)
                end = datetime.fromtimestamp((start+(k+1)*500*3000)/1000, timezone.utc)
                w.writerow({'inicio_utc':begin.isoformat(), 'fin_utc':end.isoformat(),
                            'estado_real':'OPERACION_NORMAL_CONFIRMADA',
                            'barra_rps':hz, 'normal_confirmado':'si',
                            'descripcion':'Prueba 100% sintetica'})
        events=operacion.leer_eventos(file)
        trained=modeling.train_rows(rows,eventos=events)
        assert trained['metadata']['multivelocidad_validada'] is True
        assert trained['metadata']['n_regimenes']==4
        assert trained['metadata']['filas_validas']>1800
        assert len(trained['features'])==21
        examples={}
        for hz in (5.,10.,15.,20.):
            row=fake_row(0,hz)
            predicted=modeling.score_row(row,trained,eventos=())
            assert predicted['indice_anomalia'] is not None, (hz,predicted)
            assert predicted['estado_operativo']=='EN_MARCHA_ESTABLE'
            bad=dict(row,s3_vrms_mm_s=row['s3_vrms_mm_s']*9,
                     s3_arms_m_s2=row['s3_arms_m_s2']*6,
                     s3_peak_m_s2=row['s3_peak_m_s2']*6, s3_dkw=row['s3_dkw']*8)
            outlier=modeling.score_row(bad,trained,eventos=())
            assert outlier['indice_anomalia'] >= predicted['indice_anomalia'], (hz,predicted,outlier)
            examples[hz]=(predicted['indice_anomalia'],outlier['indice_anomalia'])
        unseen=modeling.score_row(fake_row(0,12.5),trained,eventos=())
        assert unseen['estado']=='SIN_MODELO_PARA_ESTA_VELOCIDAD' and unseen['indice_anomalia'] is None
        rest=modeling.score_row(fake_row(0,0,rest=True),trained,eventos=())
        assert rest['estado']=='ENERGIZADO_EN_REPOSO' and rest['indice_anomalia'] is None
        assert operacion.estado_operativo({**fake_row(0,0,rest=True), 'modo_captura':'ACTIVO'})['estado']=='ENERGIZADO_EN_REPOSO'
        # Solo el operador puede etiquetar la falla del relevador.
        relay=operacion.Evento(start,start+10000,'FALLA_ELECTRICA_CONFIRMADA',None,False,'Relevador')
        state=modeling.score_row(fake_row(0,0,rest=True),trained,eventos=(relay,))
        assert state['estado']=='FALLA_ELECTRICA_CONFIRMADA'
        # El modelo v1.3 se guarda en su propio artefacto, separado de las versiones anteriores.
        path=Path(d)/'modelo-v12.joblib'
        modeling.save_bundle(trained,path)
        loaded=modeling.load_bundle(path)
        assert loaded['metadata']['version']==trained['metadata']['version']
        # Reposo normal etiquetado se entrena solo con ventana confirmada.
        rest_rows=[]
        for i in range(550):
            r=fake_row(i,0,rest=True)
            r['captura_unix_ms']=start+(len(rows)+i)*3000
            r['id']=len(rows)+i+1
            rest_rows.append(r)
        event_rest=operacion.Evento(start+len(rows)*3000,
                                   start+(len(rows)+550)*3000,
                                   'REPOSO_CONFIRMADO',0.0,True,'Normal aprobado')
        rest_model = modeling.train_rows(rows+rest_rows, eventos=events+(event_rest,))
        assert rest_model['metadata']['referencia_reposo_entrenada']
        normal_rest=modeling.score_row(rest_rows[-1],rest_model,eventos=events+(event_rest,))
        assert normal_rest['estado']=='REPOSO_DENTRO_DE_REFERENCIA'
        bad_rest=dict(rest_rows[-1],s1_vrms_mm_s=0.4)
        unusual_rest=modeling.score_row(bad_rest,rest_model,eventos=events+(event_rest,))
        assert unusual_rest['estado']=='VIBRACION_INESPERADA_EN_REPOSO'
        print('PASS: 4 regimenes de velocidad, 3 sensores, 21 features, estados de reposo y relevador, fuera de rango, artefacto')
        print('Scores de ejemplo (normal, atipico):',examples)

if __name__=='__main__':
    validate()

"""Entrenamiento de ejemplo sin SQL/PLC, no modifica archivos de modelos reales."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django  # noqa: E402

django.setup()
from vibraciones import modeling  # noqa: E402

rg = np.random.default_rng(20261111)
base = int(datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp() * 1000)
rows = []
for i in range(1500):
    r = {
        'id': i + 1, 'captura_unix_ms': base + i * 1000,
        'modo_captura': 'ACTIVO', 'motor_activo': 1,
        'rpm_sm1281': 0, 'rpm_vfd': 1500 + rg.normal(0, 12),
    }
    for j in (1, 2, 3):
        a = max(.1, 1 + .2 * j + rg.normal(0, .1))
        r[f's{j}_vrms_mm_s'] = max(.1, 1 + .4 * j + rg.normal(0, .12))
        r[f's{j}_arms_m_s2'] = a
        r[f's{j}_peak_m_s2'] = a * (3.1 + rg.normal(0, .1))
        r[f's{j}_dkw'] = 1 + .2 * j + rg.normal(0, .08)
    rows.append(r)
bundle = modeling.train_rows(rows)
outlier = dict(rows[-1], s3_vrms_mm_s=16, s3_arms_m_s2=12,
               s3_peak_m_s2=50, s3_dkw=8)
print('Version:', bundle['metadata']['version'])
print('Normal:', modeling.score_row(rows[-1], bundle))
print('Anomalia del sensor 3:', modeling.score_row(outlier, bundle))
print('Demo sintetica en memoria; no se escribio SQL ni un archivo de modelo.')

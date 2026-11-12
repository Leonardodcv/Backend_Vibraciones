"""Validacion 100% sintetica por regimenes. No usa SQL ni escribe artefactos reales."""
from pathlib import Path
import runpy
if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'tests_offline' / 'validar_modelo_sin_django.py'), run_name='__main__')

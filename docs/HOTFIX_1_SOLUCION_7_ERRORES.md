# Solucion para 7 errores de tests en el backend Django v1.3

## Resumen del log reportado

- `manage.py check`: correcto, no valida una conexion SQL real.
- `manage.py test vibraciones.tests -v 2`: 39 pruebas, 2 FAIL y 5 ERROR.
- 5 ERROR: `SQL_PORT=''` -> `int('')` -> `ValueError` en `vibraciones/db.py`.
- FAIL 1: test `len(set(ALL_COLUMNS)) == 74` desactualizado. Son 193 nombres de columnas unicos.
- FAIL 2: la prueba copiaba una orden de marcha `True` de una lectura sintetica a un supuesto
  reposo, por lo que el clasificador devolvia `ORDEN_MARCHA_SIN_GIRO`, correctamente.
  La prueba ahora diferencia ambos estados y los comprueba por separado.

## Instalacion del hotfix minimo (recomendada)

1. Detener el servidor Django para sustituir archivos.
2. Respaldar tu carpeta actual y especialmente `.env` y `artifacts/`.
3. Descomprimir `Backend_Vibraciones_v1.3_HOTFIX_1_ARCHIVOS.zip` dentro de
   `C:\python\Backend_Vibraciones` (sobrescribir solamente los archivos del hotfix).
4. Abrir `.env` y configurar `SQL_PORT=1433`; conservar SQL_USERNAME, SQL_PASSWORD,
   SQL_HOST=10.10.17.13, SQL_DATABASE=MantenimientoPredictivo que ya te funcionaban.
5. Activar `.venv` y ejecutar:

```powershell
python manage.py check
python manage.py test vibraciones.tests -v 2
python manage.py check_vibration_schema
python manage.py runserver 0.0.0.0:8006
```

## Alternativa: ZIP completo

Descomprime `Backend_Vibraciones_Django_v1.3_HOTFIX_1_COMPLETO.zip` en
carpeta nueva, copia tu `.env` y tus modelos validos `artifacts/`, y activa
tu entorno virtual de siempre. No sustituye tu SQL ni Node-RED.

## Alcance y seguridad

- La tabla `dbo.LecturasVibraciones` sigue siendo de 193 columnas.
- No ejecutar ALTER TABLE ni reconstruir SQL Server.
- No hay cambio en los indices IsolationForest; no requiere reentrenamiento.
- No se altera el estado inferido del equipo ni los resultados historicos.
- Las pruebas unitarias con mocks NO demuestran conectividad SQL real.
- `check_vibration_schema` SI requiere conectividad y permisos a SQL Server.
- Si sigue fallando el esquema, enviar el nuevo error completo SIN publicar credenciales.

# Cambios del backend Django v1.0 a v1.1.0

## Compatibilidad

- Las rutas de la API de la v1.0 se conservan; ahora muestran 3 canales y 74 columnas.
- Se agregan `GET /api/v1/vibraciones/variables/` y `GET /api/v1/vibraciones/calidad/`.
- `serie-temporal/` incluye promedios de sensor 3, VFD y algunas variables del medidor, sin modificar los nombres anteriores.
- `proyeccion/` requiere 3 sensores y proyecta vRMS para cada uno (sin RUL).
- Las columnas antiguas `rpm_sm1281`, `estado_vfd` y temperaturas siguen disponibles. **No se completan** retroactivamente con valores inventados.
- Si `rpm_sm1281` es cero, la referencia de RPM para ML utiliza `rpm_vfd` si es valida. Se informa `fuente_rpm`.
- El indice de anomalia v1.1 exige los 3 sensores; filas historicas sin sensor 3 devuelven `SIN_DATOS`, y el procesamiento por lotes las omite.
- Estado `REPOSO`/`TRANSICION`: no se clasifica una fase de parada como funcionamiento estable.
- Los datos nuevos del VFD se consultan siempre. El modelo puede seleccionar automaticamente frecuencia de salida, corriente y tension del bus DC **solo cuando la referencia tiene completitud total y suficiente variabilidad**. La lista real queda en la metadata del modelo.
- Las mediciones electricas Jaritza se consultan para diagnosticos, pero **no entran en el indice de anomalia** hasta verificar escalas/unidades.
- Los codigos QC se exponen sin asumir que el valor 1 significa "bueno" hasta validar la documentacion del SM1281.
- Se conserva `fecha_registro_utc`; se agregan `fecha_registro_mexico`/`fecha_captura_mexico` en JSON.
- El algoritmo de anomalia es **no supervisado**, no una probabilidad de falla ni una prediccion de tiempo para averia.

## Artefactos y resultados

| v1.0 | v1.1 |
|---|---|
| `artifacts/modelo_vibraciones_v1.joblib` | `artifacts/modelo_vibraciones_v1_1.joblib` |
| `IsolationForest` | `IsolationForest3S` |
| 2 sensores obligatorios | 3 sensores obligatorios |
| 13 features | 22 features base + VFD opcional |

Los dos modelos son **incompatibles** y no deben intercambiarse. El nuevo se debe entrenar con datos normales de los 3 sensores (despues de la incorporacion de sensor 3). Resultados antiguos en `dbo.ResultadosAnomaliaVibraciones` se preservan por version.

## Sobre la conexion

El backend sigue usando **pyodbc** y la misma conexion: `SQL_HOST=10.10.17.13`, `SQL_PORT=1433`, `SQL_DATABASE=MantenimientoPredictivo`, autenticacion SQL. Nunca se copia ni se incluye la contrasena de Node-RED en el repositorio. La cuenta del backend requiere SELECT en `LecturasVibraciones` y SELECT+INSERT en `ResultadosAnomaliaVibraciones`.

## Migracion segura

1. Respaldar proyecto v1.0 y base de datos. No borrar v1.0 ni el historial.
2. Descomprimir v1.1 en una carpeta distinta. Crear `.venv`; copiar `.env.example` a `.env` y pegar credenciales locales.
3. Detener el `runserver` v1.0 si se usara el mismo puerto 8006.
4. `python manage.py check` y `python manage.py test vibraciones.tests -v 2`.
5. `python manage.py check_vibration_schema` para validar las 74 columnas sin cambiar SQL.
6. `python manage.py train_vibration_model --start <ISO_UTC> --end <ISO_UTC> --confirm-normal` con un periodo que haya sido revisado en planta.
7. `python manage.py score_vibrations --limit 200 --dry-run`, despues ejecutar sin `--dry-run`.
8. Iniciar el backend v1.1 en 8006 y verificar `ultima/`, `serie-temporal/`, `calidad/`.
9. Planificar un solo proceso de scoring por minuto. No poner el entrenamiento en endpoints GET.

Si aun no hay muestras normales suficientes del tercer sensor, `modelo/estado/` devuelve `NO_ENTRENADO`, pero `ultima/`, `historico/`, `calidad/` y `serie-temporal/` pueden seguir consultandose.

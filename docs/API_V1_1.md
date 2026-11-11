# API v1.1 - vibraciones

Base: `http://127.0.0.1:8006/api/v1/`

La ruta `health/` no requiere API key. Las demas requieren el encabezado `X-API-Key` (la clave debe permanecer en un servidor confiable, no embebida en React).

| Ruta GET | Respuesta |
|---|---|
| `health/` | Estado Django / SQL y version |
| `modelo/estado/` | Version, features elegidas, rango RPM, cobertura normal |
| `vibraciones/ultima/` | 74 columnas, fechas UTC y Mexico, inferencia 3 sensores o `NO_ENTRENADO` |
| `vibraciones/historico/?hours=6&limit=2000` | Lecturas y scores de version activa (si existen) |
| `vibraciones/serie-temporal/?hours=24&interval_minutes=5` | Medias de 3 sensores, RPM, VFD y algunas magnitudes electricas |
| `vibraciones/anomalias/?hours=24&min_score=60&limit=200` | Anomalias persistidas para version actual |
| `vibraciones/proyeccion/?window_minutes=60&horizon_minutes=30` | Theil-Sen para 3 sensores, no calcula tiempo a falla |
| `vibraciones/variables/` | Mapa de los 74 campos y offsets de sensores confirmados en TIA |
| `vibraciones/calidad/?hours=24` | Porcentaje no nulo de sensores, VFD y medidor |

Se conservan los nombres y formato de los endpoints anteriores. Las columnas historicas aun pueden ser `null` por los cambios anteriores del flujo; la API no las repara ni las fabrica.

## Estados del indice

- `NO_ENTRENADO`: no hay modelo v1.1 local.
- `NORMAL`: indice debajo de 60 (umbral configurable y no validado como alarma industrial).
- `OBSERVACION`: indice de 60 hasta menos de 85.
- `ANOMALIA`: indice a partir de 85.
- `SIN_DATOS`: faltan sensores o contexto requerido; no se inventa un indice.
- `REPOSO`: equipo detenido; no se evalua.
- `TRANSICION`: periodo posterior a la parada; no se evalua.
- `FUERA_RANGO_RPM`: regimen no representado en la referencia sana; no se evalua.

## Ejemplo ilustrativo de `ultima/`

```json
{
  "lectura": {
    "id": 172319,
    "fecha_registro_utc": "2026-11-11T17:09:08.684000Z",
    "fecha_registro_mexico": "2026-11-11T11:09:08.684000-06:00",
    "rpm_sm1281": null,
    "rpm_vfd": 603,
    "s1_vrms_mm_s": 0.60,
    "s2_vrms_mm_s": 0.62,
    "s3_vrms_mm_s": 0.70,
    "medidor_frecuencia_hz": 50.0
  },
  "prediccion": {
    "estado": "NO_ENTRENADO",
    "indice_anomalia": null
  }
}
```

Los valores de ejemplo solo muestran el formato y no son un reporte en vivo.

## Nota de seguridad

La v1.1 permite solo consultas a la tabla de lecturas y guardado de puntuaciones en la tabla ya existente de resultados. No hay endpoints para controlar el PLC. Las predicciones no sustituyen protecciones industriales ni intervalos de mantenimiento definidos por seguridad.

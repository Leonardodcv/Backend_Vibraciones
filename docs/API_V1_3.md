# API Django Vibraciones v1.3.0: SM1281 + DB13

Base URL en el mismo equipo Django: `http://127.0.0.1:8006`.
Desde otra computadora usar la **IP de Django**, NO confundir con SQL Server.

Todos los endpoints usan `GET`, **sin Body**, y devuelven JSON. Excepto salud,
encabezados: `X-API-Key: TU_API_KEY` y `Accept: application/json`.

| Método | Ruta | Parámetros | Respuesta |
|---|---|---|---|
| GET | `/api/v1/health/` | ninguno | Django, SQL y versión 1.3.0 |
| GET | `/api/v1/modelo/estado/` | ninguno | Modelo y velocidades aprobadas |
| GET | `/api/v1/vibraciones/ultima/` | ninguno | 193 columnas, estado, predicción, diagnóstico |
| GET | `/api/v1/vibraciones/historico/` | `hours=24&limit=200` | Lecturas completas con 193 columnas |
| GET | `/api/v1/vibraciones/serie-temporal/` | `hours=24&interval_minutes=5` | Vibration RMS y conteos de alerta por ventana |
| GET | `/api/v1/vibraciones/anomalias/` | `hours=24&min_score=60&limit=200` | Índices v1.3 guardados |
| GET | `/api/v1/vibraciones/proyeccion/` | `window_minutes=60&horizon_minutes=30` | Proyección de vRMS si hay marcha estable |
| GET | `/api/v1/vibraciones/variables/` | ninguno | Inventario y grupos de 193 columnas |
| GET | `/api/v1/vibraciones/calidad/` | `hours=24` | Porcentaje de campos disponibles |
| GET | `/api/v1/vibraciones/estado/` | `samples=30` | Estado operativo, modelo y diagnósticos |
| GET | `/api/v1/vibraciones/regimenes/` | `hours=24` | Bandas, cobertura, estado y alarmas |
| GET | `/api/v1/vibraciones/diagnosticos/ultima/` | ninguno | Monitores bitmask, banderas y espejos DB13 |
| GET | `/api/v1/vibraciones/diagnosticos/historico/` | `hours=24&limit=200&raw=0` | Historial de diagnósticos; con `raw=1`, añade campos originales |
| GET | `/api/v1/vibraciones/diagnosticos/resumen/` | `hours=24` | Conteos de avisos y alarmas PLC y NotValid |

## Ejemplos Postman

`GET http://127.0.0.1:8006/api/v1/vibraciones/diagnosticos/ultima/`

```
X-API-Key: TU_API_KEY
Accept: application/json
```

`GET http://127.0.0.1:8006/api/v1/vibraciones/diagnosticos/historico/?hours=24&limit=50&raw=1`

## Interpretación importante

- `mon_dkw_bits=8` = alarma PLC; `4` = aviso; `2` = bueno; `1` = NotValid.
- `tiene_alarma = 0` representa ausencia de alarma **entre monitores válidos**;
  puede existir diagnóstico parcial porque los monitores de rodamiento están NotValid.
- `DB13` es espejo de las vibraciones `DB23`, no un cuarto sensor.
- Una alarma PLC no es igual a una falla mecánica confirmada.
- Una medición cruda `0` no se convierte a `NULL`.
- `fecha_registro_utc` se conserva en UTC; se añaden campos de presentación México.
- Los índices de anomalía de la versión v1.3 corresponden a `IsolationForest3S_Regimenes_SM1281`;
  no se comparan directamente con índices anteriores.

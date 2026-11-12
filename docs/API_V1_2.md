# API REST v1.2 - Postman

**Base URL:** `http://127.0.0.1:8006` desde el equipo de Django, o `http://IP_DEL_EQUIPO_DJANGO:8006` desde otra computadora. SQL Server `10.10.17.13` puede no ser el mismo host del backend.

**Metodos:** TODOS `GET`. **Body:** `none` para todos. **Encabezado:** `Accept: application/json`. Todos salvo `health/` requieren `X-API-Key: TU_CLAVE`. No enviar contrasenas SQL por HTTP.

| Metodo | Ruta (sufijo de baseURL) | Parametros |
|---|---|---|
| GET | `/api/v1/health/` | sin parametros (publico) |
| GET | `/api/v1/modelo/estado/` | modelo v1.2, bandas aprendidas, si hay reposo de referencia |
| GET | `/api/v1/vibraciones/ultima/` | ultima lectura (74 columnas) + prediccion + estado operativo |
| GET | `/api/v1/vibraciones/historico/?hours=24&limit=2000` | hours 1..168; limit 1..5000; incluye estado operativo por lectura |
| GET | `/api/v1/vibraciones/serie-temporal/?hours=24&interval_minutes=5` | hours 1..168; intervalo 1,5,15,30,60 |
| GET | `/api/v1/vibraciones/anomalias/?hours=24&min_score=60&limit=200` | min_score 0..100; limite 1..1000 |
| GET | `/api/v1/vibraciones/proyeccion/?window_minutes=60&horizon_minutes=30` | solo periodo reciente en marcha, no mezcla paros/cambios de velocidad |
| GET | `/api/v1/vibraciones/variables/` | grupos de 74 campos, fuente de velocidad del modelo |
| GET | `/api/v1/vibraciones/calidad/?hours=24` | cobertura fisica/NULL por campo |
| **GET** | **`/api/v1/vibraciones/estado/?samples=30`** | estado operativo con contexto de lecturas cercanas, 2..120 |
| **GET** | **`/api/v1/vibraciones/regimenes/?hours=24`** | bandas entrenadas y resumen de estados SQL |

## Ejemplo de prediccion a 20 Hz (proxy VFD)

```json
{
  "estado_operativo": "EN_MARCHA_ESTABLE",
  "estado": "NORMAL",
  "indice_anomalia": 27.4,
  "velocidad_referencia": 20.1,
  "fuente_velocidad": "VFD_HZ_PROXY",
  "unidad_velocidad": "Hz electricos VFD (proxy)",
  "regimen_centro": 20.1
}
```

Los numeros en el ejemplo son ilustrativos, no un resultado obtenido del PLC. Si no hay banda entrenada para la velocidad observada, el endpoint devuelve `SIN_MODELO_PARA_ESTA_VELOCIDAD` con `indice_anomalia: null` y **NO** `0` ni `100`.

El resultado `ENERGIZADO_EN_REPOSO` cuando el bus DC tiene voltaje no acredita alimentacion de la maquina completa. `ORDEN_MARCHA_SIN_GIRO` distingue una orden activa con eje del VFD sin movimiento. El relevador fallado se etiqueta por operador: `FALLA_ELECTRICA_CONFIRMADA`.

## Ejemplo PowerShell

```powershell
$headers = @{ 'X-API-Key' = 'TU_API_KEY'; 'Accept' = 'application/json' }
Invoke-RestMethod -Uri 'http://127.0.0.1:8006/api/v1/vibraciones/estado/?samples=30' -Headers $headers
Invoke-RestMethod -Uri 'http://127.0.0.1:8006/api/v1/vibraciones/regimenes/?hours=24' -Headers $headers
```

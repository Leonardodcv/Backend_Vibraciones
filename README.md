# Backend Vibraciones v1.3.0 — SQL Server + SM1281 v1.3.2

Proyecto **Django REST** de mantenimiento predictivo para los 3 sensores del
SIPLUS SM1281. Compatible con Node-RED
`01_NodeRED_DB13_DB23_DB187_v1_3_2_CORREGIDO.json` y la migración aditiva
SQL ya aplicada (**193 columnas**).

**No altera la tabla de telemetría** `dbo.LecturasVibraciones`, no reescribe
los datos `NULL` antiguos y no controla ni modifica el PLC.

## 1. Conexiones del proyecto (mismas que antes)

| Equipo | Valor |
|---|---|
| PLC S7-1200 | `192.168.0.5` (DB13, DB23, DB187) |
| IOT2050 Node-RED | `10.10.17.120:1880` |
| SQL Server | `10.10.17.13:1433` |
| Base | `MantenimientoPredictivo` |
| Tabla lecturas | `dbo.LecturasVibraciones` |
| Tabla resultados ML | `dbo.ResultadosAnomaliaVibraciones` |
| Puerto Django | `8006` |

Las contraseñas **no están incluidas**. Copiar el archivo `.env.example` y
colocar `SQL_USERNAME`, `SQL_PASSWORD`, `DJANGO_SECRET_KEY` y `VIBRATIONS_API_KEY`.
Usa las credenciales ya utilizadas con tu v1.2; no pegues secretos aquí.

## 2. Instalar en Windows PowerShell

Descomprime el ZIP **en carpeta diferente** de v1.2, abre PowerShell ahí:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python manage.py check
python manage.py test vibraciones.tests -v 2
python manage.py check_vibration_schema
```

Necesitas instalar **ODBC Driver 18 for SQL Server** en Windows. Django v1.3
usa pyodbc directamente, sin migraciones ORM. **No ejecutes `manage.py migrate`**
para este proyecto; la tabla ya existe y la comprobación solo realiza SELECT.

En SQL Server Management Studio, si es necesario, ejecuta
`sql/04_VERIFICAR_SM1281_V13_SOLO_LECTURA.sql` y confirma **193 columnas**.
No debes volver a ejecutar un `ALTER TABLE` si la migración v1.3 ya se aplicó.

Para iniciar el backend: detén cualquier servidor v1.1/v1.2 que ocupe 8006 y usa:

```powershell
python manage.py runserver 0.0.0.0:8006
```

Desde la misma PC: `http://127.0.0.1:8006/api/v1/health/`.
Desde otro equipo, usa la IP del host de Django (que puede ser distinta de SQL).

## 3. Qué se añadió desde v1.2

- Las **193 columnas**, agrupadas en `/api/v1/vibraciones/variables/`.
- Diagnósticos RAW del SM1281 y banderas corregidas por Node-RED v1.3.2.
- `sm1281_modulo_actualspeed_raw`, `sm1281_drive1_velocity_raw`, `SpeedSource`,
  `PulsosPorVuelta` y configuración de cada sensor. NO se infiere la escala RPM.
- Diagnóstico de advertencia/alarma del PLC separado de la predicción ML.
- Comprobación opcional de coincidencia de las 21 columnas espejo DB13 con DB23.
- Calidad de lectura: si un canal está **confirmadamente inválido** (QC 0,
  desconexión, corto o cable roto), no generar un índice engañoso.
- Estados de giro estable, estabilización, cambios de velocidad y reposo
  con las etiquetas de Node-RED y reglas inferidas del VFD.
- Nuevos endpoints `diagnosticos/ultima/`, `diagnosticos/historico/`,
  `diagnosticos/resumen/` (14 rutas total).
- Ventanas de entrenamiento por velocidad siguen requiriendo periodo normal
  **confirmado**. Conserva 21 features numéricas; monitores PLC son contexto y
  filtros, no etiquetas de falla ni una probabilidad de falla.

## 4. Entrenamiento v1.3

El artefacto `.joblib` de v1.3 se guarda separado:
`artifacts/modelo_vibraciones_v1_3_sm1281_regimenes.joblib`.

El nombre de resultados SQL es
`IsolationForest3S_Regimenes_SM1281`, evitando sobrescribir las versiones
anteriores. Hasta entrenar, `/modelo/estado/` devolverá `NO_ENTRENADO`.
El resto de las consultas (`ultima`, `diagnosticos`, `calidad`) siguen funcionando.

```powershell
python manage.py train_vibration_model --eventos "data/eventos_operativos.csv" --check-only
python manage.py train_vibration_model --eventos "data/eventos_operativos.csv"
python manage.py score_vibrations --limit 200 --dry-run
python manage.py score_vibrations --limit 200
```

`data/eventos_operativos.csv` está vacío intencionalmente: **debes cargar
ventanas normales aprobadas**. Alternativa con una ventana sana confirmada:

```powershell
python manage.py train_vibration_model `
  --start "2026-11-12T14:00:00Z" `
  --end "2026-11-12T14:30:00Z" --confirm-normal --check-only
```

> El rango anterior es SOLO ejemplo de formato: no está verificado como normal.

**IMPORTANTE:** El módulo SM1281 puede reportar `S1_MON_DKW=8` y
`S2_MON_DKW=4` durante operación. Por defecto `annotate` permite
entrenar con intervalos sanos verificados y documenta estas alarmas; para
excluirlos usa `exclude_alarm` o `exclude_warning_alarm` en `.env`.

NO extrapoles el modelo de 20 Hz VFD a una barra de velocidad desconocida.
Revisa `docs/SM1281_INTEGRACION_Y_REENTRENAMIENTO.md` y
`docs/ENTRENAMIENTO_MULTIVELOCIDAD.md`.

## 5. API y Postman

Ver `docs/API_V1_3.md` para las 14 rutas y Postman importable en `postman/`.
Todos los endpoints son GET, sin body; excepto `health/`, requieren
`X-API-Key` y `Accept: application/json`.

Prueba especialmente:

```text
http://127.0.0.1:8006/api/v1/vibraciones/variables/
http://127.0.0.1:8006/api/v1/vibraciones/ultima/
http://127.0.0.1:8006/api/v1/vibraciones/diagnosticos/ultima/
http://127.0.0.1:8006/api/v1/vibraciones/diagnosticos/resumen/?hours=24
```

## 6. Seguridad y alcance

- Reutilizar login SQL de **permisos mínimos** (SELECT lecturas,
  SELECT+INSERT resultados, lectura de metadatos). No configurar un login SA.
- La configuración SQL `.env.example` replica la conexión actual de pruebas,
  pero en producción exige TLS, `SQL_ENCRYPT=yes` y validación de certificado.
- `runserver` no es un servidor de producción; utilizar WSGI/ASGI adecuado.
- La señal `0` y un `NULL` significan cosas distintas. No se imputa medición
  histórica, no se inventa velocidad de barra ni se cambia UTC almacenado.
- `DB13` es espejo de los 3 sensores, no 3 sensores adicionales.
- Una **alarma del PLC no prueba una falla física**; los avisos y alarmas deben
  verificarse con automatización y mantenimiento.
- No se calcula vida útil restante ni probabilidad de falla.

## 7. Pruebas

- `python manage.py check`
- `python manage.py test vibraciones.tests -v 2`
- `python manage.py check_vibration_schema`
- `python tests_offline/validar_integracion_v13_sin_django.py`

El script offline usa modelos sintéticos y verificación del esquema, **no**
representa una validación directa del PLC/SQL. En este entorno de generación
no hay servidor SQL disponible ni Django/pyodbc instalados; las pruebas de
integración completas deben ejecutarse en tu equipo.

# Backend Django v1.1.0 - Demo de vibraciones S7-1200

**Proyecto funcional preparado para instalar en Windows; no conectado al SQL Server real desde el entorno de generacion.** La validacion local del algoritmo y de la estructura de archivos se realizo con datos sintéticos y el esquema de tu exportacion de 74 columnas. La prueba completa Django + SQL Server debe realizarse en tu maquina.

## Arquitectura

```text
PLC Siemens S7-1200 (192.168.0.5, DB23 y DB187)
  -> Node-RED en IOT2050 (10.10.17.120)
  -> SQL Server (10.10.17.13:1433)
     base existente MantenimientoPredictivo
     - dbo.LecturasVibraciones        (SELECT, 74 columnas)
     - dbo.ResultadosAnomaliaVibraciones (SELECT + INSERT del modelo)
  -> Django REST API, puerto 8006 -> dashboard React
```

La API usa **pyodbc**, igual que el backend v1.0. Usa la conexion al **MISMO SQL Server, MISMA base y MISMAS tablas**; no se crean nuevas bases, tablas, ni se modifican los registros del tanque. No es necesaria ninguna migracion de Django.

**Novedades:** 3 canales SM1281, VFD actualizado, 20 variables del medidor Jaritza, un indice IsolationForest de 3 sensores, consultas de calidad de datos, series 6h/24h y fechas locales de Mexico junto al UTC original. Las 74 columnas se incluyen en `ultima/` y `historico/`.

## Requisitos

- Windows 10/11 o Windows Server.
- Python 3.12 recomendado, con pip.
- Microsoft ODBC Driver 18 for SQL Server instalado en **el equipo donde corre Django**, no solo en SQL Server.
- Red autorizada entre Django y `10.10.17.13:1433`.
- Credenciales SQL existentes con los permisos mínimos indicados mas abajo.
- La tabla `dbo.LecturasVibraciones` debe contar con los campos agregados previamente en la actualizacion del 11 de noviembre de 2026.

## 1. Instalacion desde PowerShell

Extrae el ZIP en una carpeta nueva (no sobreescribas el backend v1.0). Abre PowerShell en la carpeta del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Si PowerShell no permite activar el entorno:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Verifica que el controlador ODBC esté instalado:

```powershell
python -c "import pyodbc; print(pyodbc.drivers())"
Test-NetConnection 10.10.17.13 -Port 1433
```

Edita `.env` para definir `SQL_USERNAME`, `SQL_PASSWORD`, `DJANGO_SECRET_KEY` y `VIBRATIONS_API_KEY`. **No copies contraseñas de Node-RED al código, ni compartas tu `.env`.** Puedes utilizar la misma cuenta SQL que ya autorizaron para el proyecto, aunque se recomienda crear una cuenta con permisos mínimos (no usar `sa` permanentemente).

El archivo trae la direccion y la base correctas:

```dotenv
SQL_HOST=10.10.17.13
SQL_PORT=1433
SQL_DATABASE=MantenimientoPredictivo
SQL_AUTH=sql
SQL_DRIVER=ODBC Driver 18 for SQL Server
SQL_USERNAME=TU_USUARIO_SQL
SQL_PASSWORD=TU_CONTRASENA_SQL
```

Para igualar el nodo MSSQL operativo de Node-RED, `.env.example` inicia con `SQL_ENCRYPT=no` y `SQL_TRUST_SERVER_CERTIFICATE=yes`. **Esto es solo un ajuste de compatibilidad para una demo en red aislada; no verifica la identidad del servidor y no ofrece cifrado de transporte.** En un despliegue serio, configura TLS con certificado confiable y cambia a `SQL_ENCRYPT=yes`, `SQL_TRUST_SERVER_CERTIFICATE=no`.

Genera los dos secretos aleatorios con este comando (ejecuta dos veces):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Si Django funciona desde otra maquina, ajusta `DJANGO_ALLOWED_HOSTS` con **la IP del equipo Django** y `CORS_ALLOWED_ORIGINS` con el origen HTTP del React. No uses `*` para permitir todos los orígenes.

## 2. Validacion del esquema, sin modificar SQL

```powershell
python manage.py check
python manage.py test vibraciones.tests -v 2
python manage.py check_vibration_schema
```

Para probar el algoritmo sin tocar el PLC ni SQL puedes ejecutar `python scripts/demo_sintetica.py`.

Tambien se incluye `sql/00_VERIFICAR_ESQUEMA_Y_DATOS.sql` para ejecutar en SSMS. Es **solo lectura**, no necesitas hacer `ALTER TABLE` otra vez. Si faltan columnas, primero verifica que se aplicara el script del 11 de noviembre y que se seleccionara la base correcta.

El backend espera 74 columnas. Importante: después de corregir el flujo de Node-RED, las filas que se registraron con `NULL` continuaran con `NULL` porque no se deben inventar mediciones historicas.

Para el login de Django, la cuenta necesita `SELECT` sobre `dbo.LecturasVibraciones` y `SELECT, INSERT` sobre `dbo.ResultadosAnomaliaVibraciones`. No requiere permisos de escritura a `LecturasVibraciones`, ni acceso al PLC. Ejemplo comentado en `sql/02_PERMISOS_EJEMPLO.sql`.

## 3. Comprobar los datos antes de entrenar

Primero inicia la API de prueba:

```powershell
python manage.py runserver 0.0.0.0:8006
```

En otra consola PowerShell:

```powershell
$headers = @{ 'X-API-Key' = 'TU_CLAVE_REAL' }
Invoke-RestMethod 'http://127.0.0.1:8006/api/v1/health/'
Invoke-RestMethod 'http://127.0.0.1:8006/api/v1/vibraciones/ultima/' -Headers $headers
Invoke-RestMethod 'http://127.0.0.1:8006/api/v1/vibraciones/calidad/?hours=24' -Headers $headers
Invoke-RestMethod 'http://127.0.0.1:8006/api/v1/vibraciones/variables/' -Headers $headers
```

`ultima/` funciona sin modelo entrenado y devuelve `prediccion: {"estado":"NO_ENTRENADO", "indice_anomalia":null}` hasta el primer entrenamiento. Comprueba que `s1_vrms_mm_s`, `s2_vrms_mm_s`, `s3_vrms_mm_s`, `rpm_vfd` y `vfd_frecuencia_salida_hz` tengan valores. El endpoint `calidad/` informa presencia de columnas, **no validez física**.

**Fecha UTC y Mexico:** SQL almacena `fecha_registro_utc` como UTC mediante `SYSUTCDATETIME()`. La API mantiene esa fecha y agrega `fecha_registro_mexico` / `fecha_captura_mexico` convertidas a `America/Mexico_City`; no cambies el reloj del IOT2050 ni restes 6 horas en la tabla.

## 4. Entrenar el algoritmo de tres sensores

Solo se debe entrenar sobre un intervalo que hayas revisado como **maquina sana**, con tres sensores completos y RPM en marcha. Requisitos: >=300 lecturas validas y >=15 minutos de cobertura. En la exportacion que proporcionaste anteriormente, 259 filas tenian el canal 3, por lo que aun no bastaban para entrenar la v1.1. Esos 259 registros cubrian aproximadamente cuatro minutos; el resto de las filas pertenecia a una etapa de dos sensores.

Ejemplo (cambia las fechas por un periodo verificado real; las fechas son UTC):

```powershell
python manage.py train_vibration_model `
  --start "2026-11-11T17:00:00Z" `
  --end "2026-11-11T17:30:00Z" `
  --confirm-normal
```

Este comando **no decide por si mismo** si el periodo es sano: tu confirmacion es obligatoria. Si falla por pocas filas o poca duracion, no bajes los limites sin una justificacion tecnica. Asegurate de que Node-RED ya haya insertado datos completos del canal 3 durante el intervalo.

El modelo se guardara en `artifacts/modelo_vibraciones_v1_1.joblib` (archivo nuevo y diferente del modelo v1.0). **No copies el .joblib viejo**: usa un esquema de 2 sensores incompatible con esta version. No cargues .joblib de fuentes desconocidas.

El modelo aprende 22 caracteristicas base (RPM, 3 sensores, relaciones entre canales, factores de cresta). Opcionalmente incorpora frecuencia de salida, corriente y voltaje del bus del VFD si el periodo de referencia tiene valores completos y variabilidad suficiente. Las variables del medidor Jaritza **se consultan y visualizan, pero no alimentan el índice** hasta confirmar el escalamiento.

## 5. Calcular indices y guardarlos en la misma base

```powershell
python manage.py score_vibrations --limit 200 --dry-run
python manage.py score_vibrations --limit 200
```

Se insertan resultados solamente en `MantenimientoPredictivo.dbo.ResultadosAnomaliaVibraciones`, con nombre de modelo `IsolationForest3S` y version propia. Las puntuaciones antiguas `IsolationForest` no se sobreescriben.

Si necesitas calcular de forma recurrente, configura **un solo proceso** mediante el Programador de tareas de Windows usando `scripts/calcular_anomalias.ps1` una vez por minuto. No hay tareas de fondo automáticas por iniciar `runserver`.

## 6. Endpoints

Todos usan `GET`, y todos salvo `health/` requieren `X-API-Key`.

| Endpoint | Datos |
|---|---|
| `/api/v1/health/` | Conectividad con SQL |
| `/api/v1/modelo/estado/` | Estado y caracteristicas del modelo |
| `/api/v1/vibraciones/ultima/` | 74 campos y puntuacion actual |
| `/api/v1/vibraciones/historico/?hours=6&limit=2000` | Historial completo 6h/24h por filas |
| `/api/v1/vibraciones/serie-temporal/?hours=24&interval_minutes=5` | Promedios por minuto de 3 sensores, RPM, VFD, medidor |
| `/api/v1/vibraciones/anomalias/?hours=24&min_score=60` | Anomalias calculadas para version activa |
| `/api/v1/vibraciones/proyeccion/?window_minutes=60&horizon_minutes=30` | Proyeccion experimental vRMS de 3 canales |
| `/api/v1/vibraciones/variables/` | Inventario de las 74 columnas por grupo |
| `/api/v1/vibraciones/calidad/?hours=24` | Cobertura de variables y antiguedad de ultima captura |

Mas detalle en `docs/API_V1_1.md`.

**Seguridad de React:** una API key agregada directamente al JavaScript del navegador queda expuesta a los usuarios. Para un dashboard multiusuario se necesita autenticar usuarios y tener un proxy/backend intermedio que guarde el secreto. `runserver` sirve para desarrollo; en produccion usar un servidor WSGI y HTTPS.

## 7. Limitaciones y siguiente iteracion

- `IsolationForest3S` calcula **anomalia relativa**, no probabilidad de falla ni vida util restante (RUL).
- Se necesita referencia normal revisada y, idealmente, fallas etiquetadas para futuras predicciones de averia.
- No hay forma de calcular FFT, kurtosis de onda cruda ni fase entre canales con solo vRMS/aRMS/DKW/Peak de PLC.
- Si se pierde un sensor, se informa `SIN_DATOS`, **no** se pone un indice cero ni se fabrica el dato.
- Los codigos de calidad `QC` se exponen, pero se deben validar contra el manual antes de usarlos para rechazar lecturas.
- Los campos `medidor_thd_*_raw` no se reescalan automáticamente; revisar TIA/medidor.
- Tras un reinicio o una caída de SQL, Node-RED requiere monitoreo y una cola persistente para garantizar que las lecturas no se pierdan.
- El backend no escribe ni modifica entradas/salidas del PLC, ni controla el motor.

## Referencias internas

- `docs/CAMBIOS_V1_0_A_V1_1.md`: migracion y compatibilidad.
- `docs/DISENO_MODELO_V1_1.md`: selección de features y calibración.
- `docs/API_V1_1.md`: contratos REST.
- `sql/00_VERIFICAR_ESQUEMA_Y_DATOS.sql`: auditoria sin escrituras.
- `scripts/demo_sintetica.py`: ejemplo sin tocar SQL ni PLC.

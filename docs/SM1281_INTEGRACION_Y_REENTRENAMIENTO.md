# SM1281 / DB13 / entrenamiento por velocidad — Backend v1.3

## 1. Datos y fuentes

La tabla SQL `dbo.LecturasVibraciones` tiene 193 columnas, 119 nuevas desde Node-RED
v1.3 y banderas reparadas en v1.3.2. El backend solo lee la tabla de telemetría:
no envía comandos al PLC y nunca rellena `NULL` históricos.

- `DB23`: mediciones originales, monitores SM1281, diagnósticos,
  configuración, estados, velocidad RAW no escalada.
- `DB13`: 21 valores espejo de canales 1-3 (mismas lecturas replicadas).
- `DB187`: variador VFD y medidor eléctrico.
- `estado_operativo_detalle`: etiqueta deducida en Node-RED (giro estable,
  cambio de velocidad, estabilización, reposo, etc.). No equivale a una falla.
- `rpm_vfd` y `vfd_frecuencia_salida_hz`: velocidad del variador, **no**
  necesariamente la velocidad física de la barra generadora de vibraciones.
- `sm1281_modulo_actualspeed_raw`: por ahora no es velocidad validada
  de barra; los datos recientes tienen cero.

## 2. Diagnósticos e interpretación

Para cada sensor se inspeccionan diez monitores del SM1281 y su bitmask:
1 = NotValid, 2 = Good, 4 = Warning, 8 = Alarm.

En una lectura real recibimos `S1_MON_DKW = 8`, `S2_MON_DKW = 4` y
`S3_MON_DKW = 2`; los cuatro monitores de frecuencias de rodamientos
BPFO/BPFI/FTF/BSF tienen valor 1 (no disponibles). Por eso un resumen de
avisos/alarma **no** significa que todas las señales se supervisen.

Las banderas SQL corregidas (`s*_sm1281_tiene_aviso`, `tiene_alarma`)
son resúmenes; se conserva la decodificación de las diez columnas RAW.
El backend detecta discrepancias en flags históricos derivados por flujos viejos.

**Gating de calidad:** si un sensor aparece explícitamente desconectado,
cortocircuitado, con cable roto o QC de vibración = 0, la inferencia retorna
`CALIDAD_INSTRUMENTACION_INVALIDA` (índice `null`). Una alarma de DKW **no**
bloquea por sí sola el índice de anomalía.

**DB13:** se compara de manera aproximada con DB23. Si una lectura difiere,
se emite alerta `DIFERENCIA_DETECTADA`, pero no se imputa ni se sustituye.
El valor puede reflejar diferentes instantes de actualización.

## 3. Entrenamiento y versiones

La versión v1.3 conserva el algoritmo por bandas (21 características
numéricas de tres sensores) de v1.2. Los estados PLC/flags no se incluyen
como `features` numéricas, porque podrían provocar fuga de etiquetas y
su escala/códigos no equivalen a valores físicos. Actúan como **metadatos,
validación y filtros** para el entrenamiento y la inferencia.

El modelo se almacena en:
`artifacts/modelo_vibraciones_v1_3_sm1281_regimenes.joblib`.

No se cargarán automáticamente los modelos .joblib anteriores. Mantener
separado el proyecto v1.2 y sus artefactos si deseas comparar resultados.

Entrenar con un periodo normal **confirmado por un operador**, usando el
procedimiento multivelocidad de `docs/ENTRENAMIENTO_MULTIVELOCIDAD.md`:

```powershell
python manage.py check_vibration_schema
python manage.py train_vibration_model `
  --eventos "data/eventos_operativos.csv" --check-only
python manage.py train_vibration_model `
  --eventos "data/eventos_operativos.csv"
python manage.py score_vibrations --limit 200 --dry-run
python manage.py score_vibrations --limit 200
```

Alternativamente se admite `--start`, `--end` y `--confirm-normal`
para una única ventana sana ya conocida.

La calibración genera modelos separados por velocidad; NO extrapola de 20 Hz
a 5, 10 o 15 Hz hasta tener ejemplos normales de esas velocidades.

## 4. Política de alertas en el entrenamiento

`.env` ofrece `VIBRATIONS_TRAIN_SM1281_ALERT_POLICY`:

- `annotate` (predeterminado): conserva periodos confirmados sanos aunque el
  PLC tenga alarma DKW, ya que los umbrales deben revisarse en planta.
  La metadata registra cuántas alertas había.
- `exclude_alarm`: excluye filas con algún monitor SM1281 en alarma.
- `exclude_warning_alarm`: excluye filas con alarma o advertencia SM1281.

**Recomendación:** antes de usar políticas restrictivas, analizar los umbrales
PLC porque los registros actuales muestran alarma DKW del sensor 1 y aviso del 2.
Una exclusión total podría impedir el entrenamiento por falta de datos.

`VIBRATIONS_DB13_STRICT=0` evita descartar lecturas por un mero desfase entre
DB13 y DB23. Solo activar `=1` tras estudiar lecturas simultáneas y ajustar
las tolerancias relativas/absolutas.

## 5. Eventos reales

El paro controlado de rotación (2026-11-11 aproximadamente 17:00 México)
y la avería de relevador deben etiquetarse en el CSV de eventos con sus
horas comprobadas. No constituyen automáticamente registros normales de
funcionamiento en marcha. El reposo requiere un intervalo normal aprobado.

No se estima tiempo hasta falla ni probabilidad de avería: hacen falta
historiales completos y etiquetas de fallos para ello.

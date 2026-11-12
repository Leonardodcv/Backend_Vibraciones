# Entrenamiento multivelocidad y estados operativos - v1.2

## Principio central

`rpm_vfd` (eje del motor/variador), `vfd_frecuencia_salida_hz` (frecuencia electrica VFD) y `barra_rps` (vueltas/s mecanicas de la barra) **no son equivalentes** por defecto. En el extracto actual, la barra se reporto a 20 vueltas/s, mientras el VFD entregaba ~20.1 Hz y ~603 RPM. Eso no demuestra relacion 1:1.

**Predeterminado:** usar `vfd_hz` para agrupar en regimenes electricos con datos existentes. Es un proxy, NO un tacometro de la barra. Para analizar la barra fisica con precision, conectar un sensor o hacer calibracion verificable en varias velocidades, no una sola.

El modelo entrena un **RobustScaler + IsolationForest por velocidad estable**, con **80% entrenamiento / 20% calibracion cronologica DENTRO DE CADA regimen**, y 21 atributos de vibracion (3 canales de vRMS, aRMS, Peak, DKW, factores de cresta y diferencias entre sensores). La frecuencia sirve para elegir el regimen, no como senal de falla. Cada regimen tiene sus propios percentiles de calibracion. **No extrapola a velocidades no vistas**. No se usan los valores Jaritza para ML (unidades pendientes de validar).

## Estados

| Estado | Significado / accion ML |
|---|---|
| `EN_MARCHA_ESTABLE` | VFD gira con datos estables; comparar solo con banda aprendida |
| `TRANSICION` | Arranque, desaceleracion o cambio rapido de velocidad; no puntuar |
| `ENERGIZADO_EN_REPOSO` | VFD sin giro y bus DC con tension; NO equivale a motor rotando; excluir del entrenamiento de marcha |
| `ORDEN_MARCHA_SIN_GIRO` | Comando de marcha 1, pero RPM/frecuencia 0; investigacion operativa, no aprendizaje normal |
| `SIN_GIRO_ENERGIA_NO_CONFIRMADA` | Sin giro y bus DC bajo o no disponible; NO declarar todo equipo desenergizado |
| `FALLA_VFD_REPORTADA` | `vfd_fault` distinto de cero; no puntuar con modelo de marcha sana |
| `FALLA_ELECTRICA_CONFIRMADA` | **Solo etiqueta del operador**, por ejemplo relevador; no inferida del VFD |
| `PRUEBA_CONTROLADA` / `MANTENIMIENTO` | Evento declarado por operador; excluir del modelo sano |
| `SIN_TELEMETRIA_VELOCIDAD` | Faltan lecturas de velocidad |
| `SIN_MODELO_PARA_ESTA_VELOCIDAD` | No hay suficientes muestras sanas verificadas para esa velocidad |
| `SIN_DATOS` | Faltan valores de los 3 sensores |

## Recolectar datos sanos a nuevas velocidades

1. **Asegurar condiciones de operacion y permisos** conforme a procedimientos de planta. Solo el personal responsable cambia la velocidad; la API no controla el PLC.
2. Seleccionar velocidades permitidas (por ejemplo 5, 10, 15 y 20 vueltas/s **solo si son seguras para esa maquina**). Anotar el valor de barra medido por tacometro/encoder y simultaneamente los Hz del VFD. Mantener carga/montaje constantes.
3. En cada velocidad, esperar que termine la aceleracion y la vibracion se estabilice. Despues registrar al menos **300 lecturas validas, en 15 minutos distintos, con una ventana superior a 15 minutos**; recomendable 20–30 min estables por regimen. No usar datos del arranque/transicion ni de falla de relevador.
4. Registrar inicio y fin **exactos y con zona** en `data/eventos_operativos.csv`. Solo marcar `normal_confirmado=si` despues de validar que motor/barra operaban sanos. Usar `REPOSO_CONFIRMADO` para ventanas de reposo sano y `FALLA_ELECTRICA_CONFIRMADA` para el relevador. No extender intervalos sin observar realmente el estado.
5. Reentrenar los regimenes y comprobar `modelo/estado/` y `vibraciones/regimenes/`. Las velocidades nuevas sin referencia continuaran sin puntuacion.

### Formato CSV de etiquetas

```csv
inicio_utc,fin_utc,estado_real,barra_rps,normal_confirmado,descripcion
2026-11-12T13:20:00Z,2026-11-12T13:45:00Z,OPERACION_NORMAL_CONFIRMADA,20,no,EJEMPLO aun no verificado por operador
```

`inicio_utc` y `fin_utc` son ISO8601 con `Z` o un offset explicito. `barra_rps` se registra como observacion del operador, y NO se asume igual a los Hz del VFD. Los intervalos no pueden superponerse. La fila anterior es **solo un ejemplo** con `normal_confirmado=no`: no genera entrenamiento hasta que el operador la valide y la velocidad fisica sea comprobada.

### Comandos Windows PowerShell

Para entrenar UNA ventana sana verificada, con el proxy VFD, sin etiquetas manuales:

```powershell
python manage.py train_vibration_model `
    --start "2026-11-12T13:20:00Z" `
    --end "2026-11-12T13:45:00Z" `
    --confirm-normal --check-only
```

**IMPORTANTE:** el rango es ejemplo: ajustarlo a un periodo REAL y sano (no usarlo automaticamente). Para varias velocidades usar el CSV:

```powershell
python manage.py train_vibration_model --eventos "data/eventos_operativos.csv" --check-only
python manage.py train_vibration_model --eventos "data/eventos_operativos.csv"
python manage.py score_vibrations --limit 200 --dry-run
python manage.py score_vibrations --limit 200
python manage.py runserver 0.0.0.0:8006
```

**El CSV de eventos es local al backend.** Si se marca un periodo como falla del relevador sin estar confirmado, se alteraria la interpretacion de los resultados; no modifiques automaticamente SQL para cambiar el historico. El backend v1.2 lee las mismas 74 columnas SQL, añade etiquetas solo en las respuestas y no cambia la base.

### Para usar la velocidad real de barra (`barra_rps`)

- Opcion A: `VIBRATIONS_SPEED_SOURCE=barra_rps` y guardar periodos con `barra_rps` aprobado en el CSV. Poner `VIBRATIONS_EVENTS_CSV` en el `.env` apuntando al MISMO CSV usado en entrenamiento. Cuando llega una lectura fuera de un intervalo con velocidad anotada, la API devuelve `SIN_VELOCIDAD_BARRA`, no inventa la velocidad. Por tanto esta opcion es inicialmente para **analisis historico y periodos controlados**.
- Opcion B: integrar un sensor de velocidad de barra (encoder/tacometro) en el PLC/Node-RED, almacenarlo y exponerlo al backend. Esta es la mejor solucion para inferencia continua y distintas velocidades. Requiere adaptar el flujo SQL y la consulta de lecturas; **no viene incluida esa nueva variable en las 74 columnas actuales**.
- Opcion C: `VIBRATIONS_SPEED_SOURCE=barra_rps_calibrada` y establecer `VIBRATIONS_BAR_RPS_PER_VFD_HZ` **solo despues de medir** la relacion en distintas condiciones. No se configura por defecto; una relacion basada en un solo punto no es suficiente para asegurar exactitud.

Para no perder continuidad en la fase actual, se recomienda entrenar el modelo v1.2 usando `vfd_hz` como proxy y recopilar por separado `barra_rps` medido. Asi se prepara ya el modelo condicional sin llamar "velocidad real de barra" a los Hz electricos del VFD.

## Reposo

El reposo confirmado puede contar con una referencia separada de vibracion residual si tiene >=300 muestras y >=15 minutos distintos. Se valida con el operador mediante `REPOSO_CONFIRMADO,0,si`. No se utiliza IsolationForest de marcha para clasificar el reposo. Si la suma vRMS supera el umbral de referencia, la API devuelve `VIBRACION_INESPERADA_EN_REPOSO` **sin asociarla automaticamente a falla mecanica**. La tabla `ResultadosAnomaliaVibraciones` no guarda indice de marcha para estos estados (indice `null`).

## Comparar v1.1 con v1.2

Modelos almacenados en archivos distintos: `artifacts/modelo_vibraciones_v1_1.joblib` (solo para referencia) y `artifacts/modelo_vibraciones_v1_2_regimenes.joblib` (nuevo). Los registros historicos no se cambian y las nuevas puntuaciones se guardan en `dbo.ResultadosAnomaliaVibraciones` con el nombre **IsolationForest3S_Regimenes** y otra version. El dashboard debe consultar la version activa. El indice es **relativo a velocidad**, nunca probabilidad de falla/RUL.

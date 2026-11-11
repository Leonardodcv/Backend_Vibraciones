# Diseno del algoritmo - Backend Django 1.1.0

## Objetivo

Construir un **indice de anomalia relativo a una referencia verificada como sana**. No es un modelo supervisado de fallas, no predice probabilidad de averia y no estima RUL. No sustituye alarmas o protecciones del equipo.

## Fuente

`MantenimientoPredictivo.dbo.LecturasVibraciones` (SQL Server `10.10.17.13:1433`). `captura_unix_ms` se interpreta como milisegundos Unix UTC de Node-RED/IOT2050; `fecha_registro_utc` es hora UTC calculada por SQL Server y no se convierte para almacenar. La API agrega `fecha_registro_mexico`.

## Entradas obligatorias del algoritmo

- RPM: `rpm_sm1281` si es >0; en otro caso `rpm_vfd` si >0. En los registros adjuntos el SM1281 marcaba 0 y VFD alrededor de 603 RPM.
- Por canal 1, 2 y 3: `vrms_mm_s`, `arms_m_s2`, `peak_m_s2` y `dkw`, 12 senales.
- Derivadas: 3 factores de cresta (Peak/aRMS), 3 diferencias absolutas de vRMS por pares, 3 diferencias relativas. Son 22 caracteristicas base (1 RPM + 12 senales + 9 derivadas).
- Contexto VFD opcional: `vfd_frecuencia_salida_hz`, `corriente_vfd_a`, `vfd_voltaje_bus_dc_v`. Se agrega una caracteristica solo cuando **todas** las muestras validas de la referencia tienen valor positivo y la dispersion P95-P05 supera el 1% de la mediana (normalizada). Si se selecciono, un valor ausente en inferencia devuelve `SIN_DATOS`.

La tabla/REST tambien exponen los 20 campos Jaritza, pero no entran al entrenamiento hasta validar voltajes (algunos fueron 0.03/4.6), corrientes en 0 y THD bruto fuera de escala. Los codigos QC tambien se muestran sin inventar su significado.

## Entrenamiento

- Operador elige rango UTC conocido como funcionamiento sano y confirma `--confirm-normal`.
- Debe haber >=300 lecturas completas de tres sensores con >=15 minutos de cobertura y en modo `ACTIVO`.
- Se ordena por `captura_unix_ms`. Primer 80% entrena; ultimos 20% calibran, sin mezclar futuro en ajuste del bosque.
- Se escalan columnas mediante `RobustScaler`, se entrenan 200 arboles de `IsolationForest(random_state=42)`, contaminacion `auto`.
- Puntuacion bruta: `-score_samples`. Se transforma a 0..100 usando P50 y P99.5 de la ventana de calibracion. Es un indice empirico, **no calibrado como probabilidad**.
- Las RPM del periodo de entrenamiento definen P1..P99; inferencia fuera del rango (mas margen de 100 RPM o 10%) no se clasifica como normal.
- No se rellenan con cero mediciones faltantes. Las lecturas previas a sensor 3 no se usan para entrenar esta version.

## Inferencia y persistencia

- `ultima/` infiere en memoria al consultar GET; **no escribe en SQL**.
- `score_vibrations` obtiene las filas nuevas `ACTIVO` con canal 3 completo, calcula una unica puntuacion por `lectura_id`, `modelo=IsolationForest3S`, `version_modelo`, y la guarda de forma idempotente en `dbo.ResultadosAnomaliaVibraciones`.
- Los resultados del modelo v1.0 `IsolationForest` no se mezclan. Los modelos se guardan en archivos diferentes.
- Estados: `NO_ENTRENADO`, `SIN_DATOS`, `REPOSO`, `TRANSICION`, `FUERA_RANGO_RPM`, `NORMAL`, `OBSERVACION`, `ANOMALIA`.
- Umbrales del indice (60,85) son iniciales y deben validarse con la maquina. La respuesta incluye calidad QC y origen RPM para trazabilidad.

## Proyeccion experimental

El endpoint `proyeccion/` usa la mediana de vRMS por minuto y pendiente robusta Theil-Sen de 3 sensores. Exige >=12 minutos medidos distintos, cobertura >=20 minutos, huecos <=10 minutos y RPM con CV<=10%. Solo extrapola la tendencia de los proximos 5..60 minutos; `tiempo_hasta_falla` siempre es `null`.

## Limites

Sin senal cruda de alta frecuencia no se puede inferir FFT real, frecuencia de rodamiento, fase o kurtosis confiable. Para un pronostico de RUL deben existir fallas conocidas, fechas verificadas y suficientes ciclos de degradacion hasta la falla. No entrenar automaticamente sobre datos sin inspeccion humana.

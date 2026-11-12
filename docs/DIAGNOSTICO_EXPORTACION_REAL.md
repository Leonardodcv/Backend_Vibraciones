# Diagnostico de la exportacion SQL (11-12 noviembre de 2026)

Fuente: archivo TSV compartido en la conversacion; contiene **35,045 filas y 74 columnas**. No se adjunta la exportacion completa en este ZIP.

- Periodo UTC: `2026-11-11 16:57:31.140` a `2026-11-12 14:09:05.759`.
- `rpm_vfd > 0`: **13,965** lecturas; `rpm_vfd = 0`: **21,080**.
- `rpm_sm1281 = 0` y `qc_rpm_sm1281 = 0` en las **35,045** lecturas. No se debe usar como referencia fiable de velocidad mientras no se repare/verifique esa entrada.
- `motor_activo = 1` con `rpm_vfd = 0`: **11,832** lecturas. Coinciden con `orden_marcha_vfd = 1`; NO son marcha confirmada. La etiqueta adecuada es `ORDEN_MARCHA_SIN_GIRO`, no `EN_MARCHA_ESTABLE`.
- `rpm_vfd = 0`, `motor_activo = 0`: **9,248** lecturas, con tension apreciable en el bus DC del variador. Corresponden a reposo en el VFD; no confirman por si solas alimentacion completa del equipo.
- `vfd_fault = 0` en todo el extracto. No significa que el relevador externo no haya fallado: una falla en el relevador puede no quedar en el registro de fallas del VFD.
- `vfd_frecuencia_salida_hz` en funcionamiento estable se concentra cerca de **20.1 Hz** y `rpm_vfd` en **601-604 RPM**. No hay suficientes ventanas estables demostradas a 5, 10, 15 Hz para entrenar esos regimenes sin nuevas mediciones.
- La frecuencia electrica de salida del VFD **no demuestra** que la barra gire a la misma cantidad de vueltas/s. Se necesita velocidad de barra medida o calibracion fisica comprobada.

## Cambios de estado detectados (a partir de `rpm_vfd`)

| Fecha Mexico (aproximada) | Cambio de RPM de VFD | Nota |
|---|---|---|
| 11 nov 13:10:22 | en giro -> 0 | Uno de los paros observados; no se asigna causa automaticamente |
| 11 nov 16:28:49 | 0 -> en giro | Arranque; transicion de aceleracion |
| **11 nov 17:06:19** | **en giro -> 0** | Coherente con la parada de barra informada por el operador alrededor de 17:00 |
| 12 nov 07:05:43 | 0 -> en giro | Arranque al dia siguiente |

Se distinguen **etiquetas informadas por el operador** (`FALLA_ELECTRICA_CONFIRMADA`, `REPOSO_CONFIRMADO`, `OPERACION_NORMAL_CONFIRMADA`) de **estados inferidos** (`EN_MARCHA_ESTABLE`, `ORDEN_MARCHA_SIN_GIRO`, etc.). No se insertaron o modificaron filas SQL durante este analisis.

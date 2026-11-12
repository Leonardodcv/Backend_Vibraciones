USE [MantenimientoPredictivo];
GO
-- Solo SELECT; no realiza ALTER, INSERT, UPDATE o DELETE.
-- Fecha SQL es UTC. La ventana aqui es SOLO una muestra de posibles verificaciones.
SELECT
    COUNT_BIG(*) AS total,
    SUM(CASE WHEN rpm_vfd > 20 OR vfd_frecuencia_salida_hz > 0.5 THEN 1 ELSE 0 END) AS en_giro_vfd,
    SUM(CASE WHEN orden_marcha_vfd = 1 AND rpm_vfd = 0 AND vfd_frecuencia_salida_hz = 0 THEN 1 ELSE 0 END) AS orden_sin_giro,
    SUM(CASE WHEN orden_marcha_vfd = 0 AND rpm_vfd = 0 AND vfd_frecuencia_salida_hz = 0 AND vfd_voltaje_bus_dc_v >= 100 THEN 1 ELSE 0 END) AS en_reposo_bus_dc,
    SUM(CASE WHEN vfd_fault <> 0 THEN 1 ELSE 0 END) AS fallas_reportadas_vfd
FROM dbo.LecturasVibraciones;
GO
SELECT TOP(100)
    id,
    fecha_registro_utc,
    CAST(fecha_registro_utc AT TIME ZONE 'UTC' AT TIME ZONE 'Central Standard Time (Mexico)' AS datetime2(3)) AS fecha_registro_mexico,
    orden_marcha_vfd, motor_activo, modo_captura,
    rpm_vfd, rpm_sm1281, qc_rpm_sm1281,
    vfd_frecuencia_salida_hz, vfd_voltaje_bus_dc_v,
    s1_vrms_mm_s, s2_vrms_mm_s, s3_vrms_mm_s
FROM dbo.LecturasVibraciones
WHERE fecha_registro_utc >= '2026-11-11T22:50:00'
  AND fecha_registro_utc <  '2026-11-11T23:20:00'
ORDER BY fecha_registro_utc DESC;
GO
-- Distribucion de frecuencias de VFD durante giro, NO es frecuencia mecanica de la barra.
SELECT CAST(ROUND(vfd_frecuencia_salida_hz, 0) AS int) AS banda_hz_aprox,
       COUNT_BIG(*) AS muestras,
       MIN(fecha_registro_utc) AS primera_utc,
       MAX(fecha_registro_utc) AS ultima_utc,
       AVG(s1_vrms_mm_s) AS promedio_s1,
       AVG(s2_vrms_mm_s) AS promedio_s2,
       AVG(s3_vrms_mm_s) AS promedio_s3
FROM dbo.LecturasVibraciones
WHERE vfd_frecuencia_salida_hz > 0.5
GROUP BY CAST(ROUND(vfd_frecuencia_salida_hz, 0) AS int)
ORDER BY banda_hz_aprox;
GO

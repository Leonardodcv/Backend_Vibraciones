-- Backend v1.3 | SQL Server MantenimientoPredictivo | SOLO LECTURA
-- Requiere que el script Node-RED v1.3 (119 columnas) haya sido ejecutado.
USE [MantenimientoPredictivo];
GO
-- La tabla original tenia 74 columnas y Node-RED v1.3 agrego 119 = 193.
SELECT COUNT(*) AS columnas_totales
FROM sys.columns
WHERE object_id = OBJECT_ID(N'dbo.LecturasVibraciones');
GO
-- Ultimos datos medidos (NO debe confundir 0 con NULL).
SELECT TOP (15)
    id, fecha_registro_utc,
    CAST(fecha_registro_utc AT TIME ZONE 'UTC'
         AT TIME ZONE 'Central Standard Time (Mexico)' AS datetime2(3)) AS fecha_mexico,
    estado_operativo_detalle, rpm_vfd, vfd_frecuencia_salida_hz,
    sm1281_modulo_actualspeed_raw, sm1281_cfg_speedsource,
    s1_sm1281_mon_dkw_bits, s2_sm1281_mon_dkw_bits, s3_sm1281_mon_dkw_bits,
    s1_sm1281_tiene_alarma, s2_sm1281_tiene_aviso,
    s1_sm1281_sensor_conectado, s2_sm1281_sensor_conectado, s3_sm1281_sensor_conectado,
    s1_vrms_mm_s, db13_s1_vrms_mm_s,
    s2_vrms_mm_s, db13_s2_vrms_mm_s,
    s3_vrms_mm_s, db13_s3_vrms_mm_s
FROM dbo.LecturasVibraciones
ORDER BY id DESC;
GO
-- Cobertura de cambios nuevos, sin modificar historico ni ocultar NULL.
SELECT COUNT_BIG(*) AS total_24h,
       COUNT(sm1281_modulo_actualspeed_raw) AS modulo_actualspeed_con_dato,
       COUNT(s1_sm1281_mon_dkw_bits) AS s1_dkw_estado_con_dato,
       COUNT(s2_sm1281_mon_dkw_bits) AS s2_dkw_estado_con_dato,
       COUNT(s3_sm1281_mon_dkw_bits) AS s3_dkw_estado_con_dato,
       COUNT(db13_s1_vrms_mm_s) AS espejo_db13_s1_con_dato,
       COUNT(db13_s2_vrms_mm_s) AS espejo_db13_s2_con_dato,
       COUNT(db13_s3_vrms_mm_s) AS espejo_db13_s3_con_dato,
       SUM(CASE WHEN s1_sm1281_tiene_alarma = 1 THEN 1 ELSE 0 END) AS s1_alertas,
       SUM(CASE WHEN s2_sm1281_tiene_aviso = 1 THEN 1 ELSE 0 END) AS s2_avisos
FROM dbo.LecturasVibraciones
WHERE captura_unix_ms >= DATEDIFF_BIG(MILLISECOND,
       CAST('1970-01-01T00:00:00' AS datetime2), SYSUTCDATETIME()) - 86400000;
GO
-- Comprobar resultados v1.3 sin alterar los de v1.1/v1.2.
SELECT TOP (30) modelo, version_modelo, COUNT_BIG(*) AS total,
       MIN(fecha_calculo_utc) AS desde_utc, MAX(fecha_calculo_utc) AS hasta_utc
FROM dbo.ResultadosAnomaliaVibraciones
GROUP BY modelo, version_modelo
ORDER BY hasta_utc DESC;
GO

-- SOLO LECTURA. Compatible con SQL Server: tabla existente del proyecto.
-- Ejecutar sobre 10.10.17.13:1433 despues de importar el flujo de 3 sensores.
USE [MantenimientoPredictivo];
GO

-- 1) Revisar existencia de ambas tablas, sin tocar el esquema.
SELECT DB_NAME() AS base_actual,
       OBJECT_ID(N'dbo.LecturasVibraciones', N'U') AS tabla_lecturas,
       OBJECT_ID(N'dbo.ResultadosAnomaliaVibraciones', N'U') AS tabla_resultados;
GO

-- 2) Campos criticos de la version 1.1 y columnas que faltarian.
WITH campos_esperados AS (
    SELECT nombre FROM (VALUES
      (N'captura_unix_ms'), (N'fecha_registro_utc'),
      (N'rpm_sm1281'), (N'rpm_vfd'), (N'modo_captura'),
      (N's1_vrms_mm_s'), (N's1_arms_m_s2'), (N's1_dkw'), (N's1_peak_m_s2'),
      (N's2_vrms_mm_s'), (N's2_arms_m_s2'), (N's2_dkw'), (N's2_peak_m_s2'),
      (N's3_vrms_mm_s'), (N's3_arms_m_s2'), (N's3_dkw'), (N's3_peak_m_s2'),
      (N's3_qc_vrms'), (N's3_qc_arms'), (N's3_qc_dkw'),
      (N's3_factor_cresta'), (N'vfd_frecuencia_salida_hz'),
      (N'corriente_vfd_a'), (N'vfd_voltaje_bus_dc_v'),
      (N'medidor_frecuencia_hz'), (N'medidor_thd_voltaje_l2_raw')
    ) AS x(nombre)
)
SELECT e.nombre AS columna_esperada,
       CASE WHEN c.column_id IS NULL THEN N'FALTA' ELSE N'OK' END AS estado
FROM campos_esperados AS e
LEFT JOIN sys.columns AS c
    ON c.object_id = OBJECT_ID(N'dbo.LecturasVibraciones', N'U')
   AND c.name = e.nombre
ORDER BY e.nombre;
GO

-- 3) Diez lecturas mas recientes: tres canales, RPM y contexto VFD.
SELECT TOP (10)
  id, fecha_registro_utc,
  CAST(fecha_registro_utc AT TIME ZONE 'UTC'
        AT TIME ZONE 'Central Standard Time (Mexico)' AS DATETIME2(3)) AS fecha_mexico,
  captura_unix_ms, modo_captura,
  rpm_sm1281, rpm_vfd,
  s1_vrms_mm_s, s2_vrms_mm_s, s3_vrms_mm_s,
  s1_factor_cresta, s2_factor_cresta, s3_factor_cresta,
  corriente_vfd_a, vfd_frecuencia_salida_hz,
  vfd_voltaje_bus_dc_v, medidor_frecuencia_hz
FROM dbo.LecturasVibraciones
ORDER BY id DESC;
GO

-- 4) Cobertura de los 3 sensores y contextos en ultimas 24 horas.
-- captura_unix_ms se obtiene del IOT2050, usando reloj UTC en ms Unix.
DECLARE @desde_ms BIGINT = DATEDIFF_BIG(
    MILLISECOND, CONVERT(DATETIME2(3),'1970-01-01T00:00:00'), SYSUTCDATETIME()) - 86400000;
SELECT COUNT_BIG(*) AS filas_24h,
       COUNT(s1_vrms_mm_s) AS sensor1_presentes,
       COUNT(s2_vrms_mm_s) AS sensor2_presentes,
       COUNT(s3_vrms_mm_s) AS sensor3_presentes,
       COUNT(rpm_vfd) AS rpm_vfd_presentes,
       COUNT(vfd_frecuencia_salida_hz) AS vfd_frecuencia_presentes,
       COUNT(medidor_frecuencia_hz) AS medidor_frecuencia_presentes
FROM dbo.LecturasVibraciones
WHERE captura_unix_ms >= @desde_ms;
GO

-- Este script no ejecuta CREATE / ALTER / UPDATE / DELETE / INSERT.

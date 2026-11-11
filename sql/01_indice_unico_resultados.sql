-- Mejora opcional recomendada para evitar resultados duplicados por lectura/modelo/version.
-- Ejecutar en SSMS dentro de MantenimientoPredictivo, DESPUES de revisar duplicados.
USE MantenimientoPredictivo;
GO
IF EXISTS (
    SELECT 1 FROM dbo.ResultadosAnomaliaVibraciones
    WHERE version_modelo IS NOT NULL
    GROUP BY lectura_id, modelo, version_modelo HAVING COUNT_BIG(*) > 1
)
    THROW 50010, 'Existen resultados duplicados. Revisar antes de agregar UNIQUE.', 1;
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id=OBJECT_ID('dbo.ResultadosAnomaliaVibraciones')
      AND name='UX_ResultadosAnomalia_Lectura_Modelo_Version'
)
CREATE UNIQUE INDEX UX_ResultadosAnomalia_Lectura_Modelo_Version
    ON dbo.ResultadosAnomaliaVibraciones(lectura_id, modelo, version_modelo)
    WHERE version_modelo IS NOT NULL;
GO

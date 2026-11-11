"""Verificar tablas y columnas reales SIN modificar SQL."""
from django.core.management.base import BaseCommand, CommandError

from vibraciones import db


class Command(BaseCommand):
    help = "Comprobar tablas dbo.LecturasVibraciones y dbo.ResultadosAnomaliaVibraciones."

    def handle(self, *args, **options):
        try:
            with db.sql_connection() as con:
                cur = con.cursor()
                found = set()
                q = "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME IN (?, ?)"
                for name, col in cur.execute(q, "LecturasVibraciones", "ResultadosAnomaliaVibraciones").fetchall():
                    found.add((str(name), str(col)))
                expected = {("LecturasVibraciones", n) for n in db.BASE_COLUMNS}
                expected.update({("ResultadosAnomaliaVibraciones", n) for n in
                                 ("lectura_id", "indice_anomalia", "modelo", "version_modelo", "detalle")})
                missing = sorted(expected - found)
                if missing:
                    raise CommandError("Faltan columnas:\n" + "\n".join(f"- {t}.{c}" for t, c in missing))
                cur.execute("SELECT COUNT_BIG(*) FROM dbo.LecturasVibraciones")
                count = cur.fetchone()[0]
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError("No se pudo consultar esquema SQL: " + type(exc).__name__) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Esquema compatible v1.1.0 | LecturasVibraciones: {count} filas | Tabla de resultados: OK"
        ))

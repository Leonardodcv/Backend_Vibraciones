"""Procesamiento por lotes. Ejecutar cada minuto usando Task Scheduler/cron."""
import logging

from django.core.management.base import BaseCommand, CommandError

from vibraciones import db, modeling

logger = logging.getLogger("vibraciones")


class Command(BaseCommand):
    help = "Calcular indices para lecturas nuevas y guardar en ResultadosAnomaliaVibraciones."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Max. lecturas recientes no calculadas (1..10000)")
        parser.add_argument("--since-id", type=int, default=0, help="Ignorar IDs menores o iguales")
        parser.add_argument("--dry-run", action="store_true", help="No escribir resultados a SQL")

    def handle(self, *args, **options):
        bundle = modeling.load_bundle()
        if bundle is None:
            raise CommandError("El modelo no esta entrenado: ejecutar train_vibration_model.")
        try:
            rows = db.unscored_rows(bundle["metadata"]["version"], limit=options["limit"],
                                    since_id=options["since_id"])
            saved = 0
            skipped = 0
            for row in rows:
                score = modeling.score_row(row, bundle)
                if score.get("indice_anomalia") is None:
                    skipped += 1
                    continue
                if not options["dry_run"]:
                    db.save_score(
                        lectura_id=int(row["id"]),
                        index=float(score["indice_anomalia"]),
                        version=score["version_modelo"],
                        details_json=modeling.details_for_sql(score),
                    )
                saved += 1
            self.stdout.write(self.style.SUCCESS(
                f"Revisadas: {len(rows)} | {'Clasificadas (simulacion)' if options['dry_run'] else 'Guardadas'}: "
                f"{saved} | Sin puntuacion: {skipped}"
            ))
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            logger.exception("Error al calcular indices")
            raise CommandError("Error de SQL o inferencia: " + type(exc).__name__) from exc

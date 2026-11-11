"""Entrenamiento intencional a partir de periodo de referencia conocido."""
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from vibraciones import db, modeling


def parse_date(text: str) -> int:
    try:
        if len(text) == 10:
            value = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if value.tzinfo is None:
                raise ValueError("falta UTC")
        return int(value.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, OverflowError) as exc:
        raise CommandError("Usar fecha YYYY-MM-DD (UTC) o ISO 8601 con zona; " + str(exc))


class Command(BaseCommand):
    help = "Entrenar IsolationForest v1.1 usando tres sensores y referencia normal confirmada."

    def add_arguments(self, parser):
        parser.add_argument("--start", required=True, help="Inicio UTC, YYYY-MM-DD o ISO 8601")
        parser.add_argument("--end", required=True, help="Fin EXCLUSIVO UTC")
        parser.add_argument("--limit", type=int, default=50000)
        parser.add_argument("--confirm-normal", action="store_true", help="Confirmar referencia verificada por operador")

    def handle(self, *args, **options):
        if not options["confirm_normal"]:
            raise CommandError("Se requiere --confirm-normal para evitar entrenar con fallas desconocidas.")
        start_ms, end_ms = parse_date(options["start"]), parse_date(options["end"])
        if start_ms >= end_ms:
            raise CommandError("--start debe ser anterior a --end")
        try:
            rows = db.training_rows(start_ms, end_ms, options["limit"])
            bundle = modeling.train_rows(rows)
            path = modeling.save_bundle(bundle)
        except (ValueError, modeling.InsufficientData) as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError("No se pudo acceder a SQL o generar el modelo: " + type(exc).__name__) from exc
        meta = bundle["metadata"]
        self.stdout.write(self.style.SUCCESS(
            f"Modelo guardado: {path}\nVersion: {meta['version']}\n"
            f"Lecturas validas: {meta['filas_validas']}\n"
            f"Referencia: {meta['duracion_minutos']} min\n"
            "Nota: el indice NO representa probabilidad de falla."
        ))

"""Procesar por lotes; estados sin modelo o transiciones NO se guardan como score cero."""
import logging
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from vibraciones import db, modeling, operacion

logger = logging.getLogger('vibraciones')


class Command(BaseCommand):
    help = 'Puntuar registros nuevos en REGIMENES entrenados, modelo v1.3.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=200)
        parser.add_argument('--since-id', type=int, default=0)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        bundle = modeling.load_bundle()
        if bundle is None:
            raise CommandError('Falta modelo v1.3: usar train_vibration_model')
        try:
            rows = db.unscored_rows(bundle['metadata']['version'],
                                    limit=options['limit'], since_id=options['since_id'])
            events = operacion.eventos_configurados()
            saved = 0
            causes = Counter()
            # Consulta devuelve DESC: el primer resultado a invertir tiene anterior
            # solamente si esta presente en el lote. No inventamos el anterior.
            chronological = sorted(rows, key=lambda r: operacion.stamp(r))
            previous = None
            for row in chronological:
                result = modeling.score_row(row, bundle, previous=previous, eventos=events)
                previous = row
                if result.get('indice_anomalia') is None:
                    causes[result.get('estado', 'SIN_CLASIFICAR')] += 1
                    continue
                if not options['dry_run']:
                    db.save_score(lectura_id=int(row['id']),
                                  index=float(result['indice_anomalia']),
                                  version=result['version_modelo'],
                                  details_json=modeling.details_for_sql(result))
                saved += 1
            self.stdout.write(self.style.SUCCESS(
                f'Revisadas: {len(rows)} | '
                f'{"Clasificadas (simulacion)" if options["dry_run"] else "Guardadas"}: {saved} | '
                f'Sin puntuacion: {sum(causes.values())} | Motivos: {dict(causes)}'
            ))
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            logger.exception('Error de scoring v1.3')
            raise CommandError('Fallo de SQL/inferencia: ' + type(exc).__name__) from exc

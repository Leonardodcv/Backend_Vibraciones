"""Entrenar por bandas con periodos aprobados. El CSV NO modifica la base SQL."""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from vibraciones import db, modeling, operacion
from ._dates import parse_date


class Command(BaseCommand):
    help = 'Entrenar v1.3 por regimen de velocidad (hasta 3 sensores, reposo opcional).'

    def add_arguments(self, parser):
        parser.add_argument('--start', help='Inicio UTC o ISO 8601 con offset')
        parser.add_argument('--end', help='Fin exclusivo UTC o ISO 8601 con offset')
        parser.add_argument('--eventos', help='CSV con intervalos, estados y confirmacion del operador')
        parser.add_argument('--limit', type=int, default=200000)
        parser.add_argument('--confirm-normal', action='store_true',
                            help='Para UNA ventana conocida sana, sin archivo de eventos')
        parser.add_argument('--check-only', action='store_true',
                            help='Entrenar/calibrar en memoria, SIN guardar artefacto')

    def handle(self, *args, **options):
        if bool(options['start']) != bool(options['end']):
            raise CommandError('Debes indicar --start Y --end juntos')
        if not options['eventos'] and not (options['start'] and options['confirm_normal']):
            raise CommandError('Indica --eventos CSV aprobado, o --start --end --confirm-normal')
        if options['eventos'] and options['confirm_normal']:
            raise CommandError('Con --eventos se usan aprobaciones por fila del CSV, no --confirm-normal')
        events = ()
        try:
            if options['eventos']:
                events = operacion.leer_eventos(Path(options['eventos']))
                verified = [e for e in events if e.normal_confirmado]
                if not verified:
                    raise CommandError('No hay intervalos normal_confirmado=si en CSV')
                start = min(e.inicio_ms for e in verified)
                end = max(e.fin_ms for e in verified)
                if options['start'] and options['end']:
                    start = max(start, parse_date(options['start']))
                    end = min(end, parse_date(options['end']))
            else:
                start, end = parse_date(options['start']), parse_date(options['end'])
            if start >= end:
                raise CommandError('Ventana de entrenamiento vacia o invertida')
            rows = db.training_rows(start, end, options['limit'])
            bundle = modeling.train_rows(rows, eventos=events,
                                         confirm_normal=bool(options['confirm_normal']))
            path = None if options['check_only'] else modeling.save_bundle(bundle)
        except CommandError:
            raise
        except (ValueError, modeling.InsufficientData) as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError('Error SQL/entrenamiento: ' + type(exc).__name__) from exc
        meta = bundle['metadata']
        action = 'Entrenamiento validado (SIN guardar)' if options['check_only'] else f'Modelo guardado: {path}'
        self.stdout.write(self.style.SUCCESS(
            f'{action}\nVersion: {meta["version"]}\n'
            f'Bandas entrenadas: {meta["n_regimenes"]} | Multivelocidad: {meta["multivelocidad_validada"]}\n'
            f'Filas validas: {meta["filas_validas"]} | Reposo: {meta["referencia_reposo_entrenada"]}\n'
            f'Bandas: {[b["centro"] for b in meta["regimenes"]]}\n'
            'No interpretar indice como probabilidad de falla.'
        ))

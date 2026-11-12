from datetime import datetime, timezone
from django.core.management.base import CommandError


def parse_date(text: str) -> int:
    try:
        if len(text) == 10:
            dt = datetime.strptime(text, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                raise ValueError('falta zona horaria Z o -06:00')
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, OverflowError, TypeError) as exc:
        raise CommandError('Fecha invalida: ' + str(exc)) from exc

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
import json

from landing.models import Visitor, Session, Interaction


class Command(BaseCommand):
    help = 'Dump basic info from Visitor, Session, and Interaction models for development debugging.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10, help='Max number of records per model to show (use 0 for none, -1 for all)')
        parser.add_argument('--json', action='store_true', help='Output results as JSON')
        parser.add_argument('--visitor', type=str, help='Show sessions for a specific visitor cookie UUID')

    def handle(self, *args, **options):
        limit = options['limit']
        as_json = options['json']
        visitor_filter = options.get('visitor')

        # Helper to apply limit
        def apply_limit(qs):
            if limit == -1:
                return qs
            if limit == 0:
                return qs.none()
            return qs[:limit]

        # Querysets / values
        visitors_qs = Visitor.objects.all().order_by('-created_at')
        sessions_qs = Session.objects.all().order_by('-started_at')
        interactions_qs = Interaction.objects.all().order_by('-timestamp')

        if visitor_filter:
            try:
                v = Visitor.objects.get(cookie_id=visitor_filter)
                sessions_qs = v.sessions.all().order_by('-started_at')
            except Visitor.DoesNotExist:
                self.stderr.write(f'Visitor with cookie_id={visitor_filter} not found.')
                return

        visitors = list(apply_limit(visitors_qs).values())
        sessions = list(apply_limit(sessions_qs).values())
        interactions = list(apply_limit(interactions_qs).values())

        summary = {
            'generated_at': timezone.now(),
            'counts': {
                'visitors': Visitor.objects.count(),
                'sessions': Session.objects.count(),
                'interactions': Interaction.objects.count(),
            },
            'samples': {
                'visitors': visitors,
                'sessions': sessions,
                'interactions': interactions,
            }
        }

        if as_json:
            # Use DjangoJSONEncoder to handle datetimes/UUIDs
            out = json.dumps(summary, cls=DjangoJSONEncoder, indent=2)
            self.stdout.write(out)
            return

        # Human readable output
        self.stdout.write('Database snapshot for debugging')
        self.stdout.write(f"Generated: {summary['generated_at']}")
        self.stdout.write('\nCounts:')
        for k, v in summary['counts'].items():
            self.stdout.write(f'  - {k}: {v}')

        def print_rows(title, rows, fields=None, sample_limit=limit):
            self.stdout.write(f"\n{title} (showing {len(rows)}):")
            if not rows:
                self.stdout.write('  (no rows)')
                return
            for r in rows:
                if fields:
                    parts = [f"{f}={r.get(f)}" for f in fields if f in r]
                else:
                    parts = [f"{k}={v}" for k, v in r.items()]
                self.stdout.write('  - ' + ', '.join(parts))

        print_rows('Visitors', visitors, fields=['id', 'cookie_id', 'created_at', 'last_seen'])
        print_rows('Sessions', sessions, fields=['id', 'visitor_id', 'session_id', 'started_at', 'ended_at', 'is_active'])
        print_rows('Interactions', interactions, fields=['id', 'session_id', 'event_type', 'element', 'timestamp', 'x', 'y'])

        self.stdout.write('\nDone.')

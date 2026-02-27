from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.db.models import Prefetch
from landing.models import LandingPage, LandingSection

import json
import textwrap

def _clean_and_truncate(text, max_chars=200):
    if text is None:
        return None
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."

class Command(BaseCommand):
    help = 'Dump info from LandingPage and LandingSection models for debugging.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10, help='Max number of pages to show (use 0 for none, -1 for all)')
        parser.add_argument('--json', action='store_true', help='Output results as JSON')
        parser.add_argument('--page', type=str, help='Filter by page id or name (partial match on name)')
        parser.add_argument('--show-html', action='store_true', help='Include full html/css fields (no truncation)')
        parser.add_argument('--truncate', type=int, default=200, help='Truncate length for html/css when --show-html not set')

    def handle(self, *args, **options):
        limit = options['limit']
        as_json = options['json']
        page_filter = options.get('page')
        show_html = options.get('show_html')
        truncate_len = options.get('truncate') or 200

        def apply_limit(qs):
            if limit == -1:
                return qs
            if limit == 0:
                return qs.none()
            return qs[:limit]

        # Prefetch sections to avoid N+1
        sections_prefetch = Prefetch('sections', queryset=LandingSection.objects.order_by('order'))
        pages_qs = LandingPage.objects.all().order_by('-created_at').prefetch_related(sections_prefetch)

        if page_filter:
            # allow searching by id (exact) or name (icontains)
            pages_qs = pages_qs.filter(models__icontains=page_filter) if False else pages_qs.filter(name__icontains=page_filter)

        pages = list(apply_limit(pages_qs))

        # Build summary
        summary = {
            'generated_at': timezone.now(),
            'counts': {
                'landing_pages': LandingPage.objects.count(),
                'landing_sections': LandingSection.objects.count(),
            },
            'pages': []
        }

        for p in pages:
            page_obj = {
                'id': p.id,
                'name': p.name,
                'created_at': p.created_at,
            }
            # global_css handling
            if show_html:
                page_obj['global_css'] = p.global_css
            else:
                page_obj['global_css'] = _clean_and_truncate(p.global_css, max_chars=truncate_len)

            # sections
            secs = []
            for s in p.sections.all():
                sec_item = {
                    'id': s.id,
                    'key': s.key,
                    'order': s.order,
                    'created_at': s.created_at,
                }
                if show_html:
                    sec_item['html'] = s.html
                    sec_item['css'] = s.css
                else:
                    sec_item['html'] = _clean_and_truncate(s.html, max_chars=truncate_len)
                    sec_item['css'] = _clean_and_truncate(s.css, max_chars=truncate_len)
                secs.append(sec_item)
            page_obj['sections'] = secs
            summary['pages'].append(page_obj)

        if as_json:
            out = json.dumps(summary, cls=DjangoJSONEncoder, indent=2)
            self.stdout.write(out)
            return

        # Human readable output
        self.stdout.write('Landing pages snapshot for debugging')
        self.stdout.write(f"Generated: {summary['generated_at']}")
        self.stdout.write('\nCounts:')
        for k, v in summary['counts'].items():
            self.stdout.write(f'  - {k}: {v}')

        for p in summary['pages']:
            self.stdout.write('\n' + ('=' * 60))
            self.stdout.write(f"Page id={p['id']} name=\"{p['name']}\" created_at={p['created_at']}")
            self.stdout.write('Global CSS (truncated):')
            self.stdout.write(textwrap.indent(str(p['global_css'] or '(none)'), '  '))
            self.stdout.write('\nSections:')
            if not p['sections']:
                self.stdout.write('  (no sections)')
            for s in p['sections']:
                self.stdout.write(f"  - id={s['id']} key={s['key']} order={s['order']} created_at={s['created_at']}")
                self.stdout.write('    html: ' + (_clean_and_truncate(s['html'], max_chars=truncate_len) if not show_html else '(full)'))
                self.stdout.write('    css:  ' + (_clean_and_truncate(s['css'], max_chars=truncate_len) if not show_html else '(full)'))

        self.stdout.write('\nDone.')
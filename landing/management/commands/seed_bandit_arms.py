"""
Management command: seed_bandit_arms

Populates the BanditArm table with starter arms whose page_config
matches the shape expected by the frontend's applyPageConfig() function.
Also initialises LinUCBParam rows for each arm (linear bandit).

Usage:
    python manage.py seed_bandit_arms          # insert only new arms
    python manage.py seed_bandit_arms --reset   # delete all arms first
"""

from django.core.management.base import BaseCommand

from landing.models import BanditArm, LinUCBParam
from landing.bandit_utils import make_initial_A, make_initial_b


# Each arm's page_config follows the applyPageConfig shape:
#   { compact: [...], hide: [...], promote: "section_id", variants: {id: cls} }

STARTER_ARMS = [
    {
        "arm_id": "no_change",
        "name": "Control — no layout changes",
        "page_config": {},
    },
    {
        "arm_id": "hero_compact",
        "name": "Hero section compacted",
        "page_config": {
            "compact": ["hero"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },
    {
        "arm_id": "pricing_compact",
        "name": "Pricing section compacted",
        "page_config": {
            "compact": ["pricing"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },
    {
        "arm_id": "pricing_highlight_plan_2",
        "name": "Pricing — highlight middle plan",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"pricing": "highlight-plan-2"},
        },
    },
    {
        "arm_id": "testimonials_single",
        "name": "Testimonials — single spotlight",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"testimonials": "testimonials-single"},
        },
    },
    {
        "arm_id": "services_compact",
        "name": "Services section compacted",
        "page_config": {
            "compact": ["services"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },
]


class Command(BaseCommand):
    help = "Seed the BanditArm table with starter arms for the contextual bandit."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete ALL existing CtxBanditArm rows before seeding.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            deleted, _ = BanditArm.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing BanditArm rows."))

        created_count = 0
        for arm_data in STARTER_ARMS:
            _obj, created = BanditArm.objects.get_or_create(
                arm_id=arm_data["arm_id"],
                defaults={
                    "name": arm_data["name"],
                    "page_config": arm_data["page_config"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created arm: {arm_data['arm_id']}"))
            else:
                self.stdout.write(f"  Already exists: {arm_data['arm_id']}")

        # Ensure every arm has a LinUCBParam row (linear bandit parameters)
        param_count = 0
        for arm in BanditArm.objects.all():
            _param, p_created = LinUCBParam.objects.get_or_create(
                arm=arm,
                defaults={
                    "A_matrix": make_initial_A(),
                    "b_vector": make_initial_b(),
                },
            )
            if p_created:
                param_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Initialised LinUCB params: {arm.arm_id}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {created_count} arm(s) created, {param_count} LinUCB param(s) initialised."
        ))

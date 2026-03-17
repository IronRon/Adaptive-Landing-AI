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


def _derive_affected_sections(page_config):
    """Derive the list of section IDs a page_config touches."""
    sections = set()
    for s in page_config.get("compact", []):
        sections.add(s)
    for s in page_config.get("hide", []):
        sections.add(s)
    if page_config.get("promote"):
        sections.add(page_config["promote"])
    for s in page_config.get("variants", {}):
        sections.add(s)
    return sorted(sections)


# Each arm's page_config follows the applyPageConfig shape:
#   { compact: [...], hide: [...], promote: "section_id", variants: {id: cls} }

STARTER_ARMS = [
    # ------------------------------------------------------------------
    # CONTROL — no changes at all (baseline)
    # ------------------------------------------------------------------
    {
        "arm_id": "no_change",
        "name": "Control — no layout changes",
        "page_config": {},
    },

    # ------------------------------------------------------------------
    # HERO variants
    # ------------------------------------------------------------------
    {
        "arm_id": "hero_compact",
        "name": "Hero — compact (smaller, hides subtitle & trust badges)",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"hero": "hero-compact"},
        },
    },
    {
        "arm_id": "hero_cta_emphasis",
        "name": "Hero — pulsing CTA button",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"hero": "hero-cta-emphasis"},
        },
    },

    # ------------------------------------------------------------------
    # SERVICES variants
    # ------------------------------------------------------------------
    {
        "arm_id": "services_compact",
        "name": "Services — compact (hides descriptions, shows top 3)",
        "page_config": {
            "compact": ["services"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },
    {
        "arm_id": "featured_service_1",
        "name": "Services — highlight service card 1",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"services": "featured-service-1"},
        },
    },
    {
        "arm_id": "featured_service_2",
        "name": "Services — highlight service card 2",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"services": "featured-service-2"},
        },
    },
    {
        "arm_id": "featured_service_3",
        "name": "Services — highlight service card 3",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"services": "featured-service-3"},
        },
    },

    # ------------------------------------------------------------------
    # PRICING variants
    # ------------------------------------------------------------------
    {
        "arm_id": "pricing_compact",
        "name": "Pricing — compact (fewer features shown)",
        "page_config": {
            "compact": ["pricing"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },
    {
        "arm_id": "highlight_plan_1",
        "name": "Pricing — highlight plan 1 (cheapest)",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"pricing": "highlight-plan-1"},
        },
    },
    {
        "arm_id": "highlight_plan_2",
        "name": "Pricing — highlight plan 2 (middle)",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"pricing": "highlight-plan-2"},
        },
    },
    {
        "arm_id": "highlight_plan_3",
        "name": "Pricing — highlight plan 3 (premium)",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"pricing": "highlight-plan-3"},
        },
    },

    # ------------------------------------------------------------------
    # TESTIMONIALS variants
    # ------------------------------------------------------------------
    {
        "arm_id": "testimonials_single",
        "name": "Testimonials — single card spotlight",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"testimonials": "testimonials-single"},
        },
    },
    {
        "arm_id": "testimonials_compact",
        "name": "Testimonials — compact (smaller quotes, no subheading)",
        "page_config": {
            "compact": ["testimonials"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },

    # ------------------------------------------------------------------
    # FAQ variants
    # ------------------------------------------------------------------
    {
        "arm_id": "faq_compact",
        "name": "FAQ — compact (smaller text)",
        "page_config": {
            "compact": ["faq"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },
    {
        "arm_id": "faq_top3",
        "name": "FAQ — show only top 3 with 'View All' button",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": None,
            "variants": {"faq": "faq-compact-top3"},
        },
    },

    # ------------------------------------------------------------------
    # ABOUT variants
    # ------------------------------------------------------------------
    {
        "arm_id": "about_compact",
        "name": "About — compact (hides stats & extra text)",
        "page_config": {
            "compact": ["about"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },

    # ------------------------------------------------------------------
    # LOCATIONS variants
    # ------------------------------------------------------------------
    {
        "arm_id": "locations_compact",
        "name": "Locations — compact (hides addresses & hours)",
        "page_config": {
            "compact": ["locations"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },
    {
        "arm_id": "hide_locations",
        "name": "Locations — hidden entirely",
        "page_config": {
            "compact": [],
            "hide": ["locations"],
            "promote": None,
            "variants": {},
        },
    },

    # ------------------------------------------------------------------
    # CONTACT variants
    # ------------------------------------------------------------------
    {
        "arm_id": "contact_compact",
        "name": "Contact — compact (hides contact details, form only)",
        "page_config": {
            "compact": ["contact"],
            "hide": [],
            "promote": None,
            "variants": {},
        },
    },

    # ------------------------------------------------------------------
    # PROMOTE variants — move a section right below the trust bar
    # ------------------------------------------------------------------
    {
        "arm_id": "promote_pricing",
        "name": "Promote pricing to top (below trust bar)",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": "pricing",
            "variants": {},
        },
    },
    {
        "arm_id": "promote_services",
        "name": "Promote services to top (below trust bar)",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": "services",
            "variants": {},
        },
    },
    {
        "arm_id": "promote_testimonials",
        "name": "Promote testimonials to top (below trust bar)",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": "testimonials",
            "variants": {},
        },
    },
    {
        "arm_id": "promote_contact",
        "name": "Promote contact to top (below trust bar)",
        "page_config": {
            "compact": [],
            "hide": [],
            "promote": "contact",
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
            affected = _derive_affected_sections(arm_data["page_config"])
            _obj, created = BanditArm.objects.get_or_create(
                arm_id=arm_data["arm_id"],
                defaults={
                    "name": arm_data["name"],
                    "page_config": arm_data["page_config"],
                    "affected_sections": affected,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created arm: {arm_data['arm_id']}"))
            else:
                # Backfill affected_sections for existing arms that lack it
                if not _obj.affected_sections:
                    _obj.affected_sections = affected
                    _obj.save(update_fields=["affected_sections"])
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

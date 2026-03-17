"""
Tests for the combinational contextual multi-armed (slate) bandit.

Coverage
--------
1. Conflict detection between arm pairs
2. merge_page_configs determinism and correctness
3. choose_slate: K arms, no duplicates, no conflicts, no_change excluded
4. First visit (visit_number == 1) creates no BanditDecision
5. Second visit (>= 2) produces a slate decision with merged config
6. Observation-gated reward: unobserved arms are NOT updated
7. Observation-gated reward: observed arms ARE updated
8. Idempotency: /end-session/ twice does not double-increment stats
"""

import json
import uuid

from django.test import TestCase, RequestFactory
from django.utils import timezone

from landing.models import (
    BanditArm,
    BanditDecision,
    Event,
    LinUCBParam,
    Session,
    Visitor,
)
from landing.bandit_utils import (
    EPSILON,
    FEATURE_DIM,
    _has_conflict,
    _conflicts_with_slate,
    build_context,
    choose_slate,
    make_initial_A,
    make_initial_b,
    merge_page_configs,
    update_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_arms():
    """Create a minimal set of arms for testing."""
    arms_data = [
        {
            "arm_id": "no_change",
            "page_config": {},
            "affected_sections": [],
        },
        {
            "arm_id": "hero_compact",
            "page_config": {"compact": [], "hide": [], "promote": None, "variants": {"hero": "hero-compact"}},
            "affected_sections": ["hero"],
        },
        {
            "arm_id": "pricing_compact",
            "page_config": {"compact": ["pricing"], "hide": [], "promote": None, "variants": {}},
            "affected_sections": ["pricing"],
        },
        {
            "arm_id": "highlight_plan_2",
            "page_config": {"compact": [], "hide": [], "promote": None, "variants": {"pricing": "highlight-plan-2"}},
            "affected_sections": ["pricing"],
        },
        {
            "arm_id": "testimonials_single",
            "page_config": {"compact": [], "hide": [], "promote": None, "variants": {"testimonials": "testimonials-single"}},
            "affected_sections": ["testimonials"],
        },
        {
            "arm_id": "promote_pricing",
            "page_config": {"compact": [], "hide": [], "promote": "pricing", "variants": {}},
            "affected_sections": ["pricing"],
        },
        {
            "arm_id": "hide_locations",
            "page_config": {"compact": [], "hide": ["locations"], "promote": None, "variants": {}},
            "affected_sections": ["locations"],
        },
        {
            "arm_id": "locations_compact",
            "page_config": {"compact": ["locations"], "hide": [], "promote": None, "variants": {}},
            "affected_sections": ["locations"],
        },
        {
            "arm_id": "promote_services",
            "page_config": {"compact": [], "hide": [], "promote": "services", "variants": {}},
            "affected_sections": ["services"],
        },
        {
            "arm_id": "services_compact",
            "page_config": {"compact": ["services"], "hide": [], "promote": None, "variants": {}},
            "affected_sections": ["services"],
        },
        {
            "arm_id": "faq_compact",
            "page_config": {"compact": ["faq"], "hide": [], "promote": None, "variants": {}},
            "affected_sections": ["faq"],
        },
    ]
    created = []
    for d in arms_data:
        arm = BanditArm.objects.create(
            arm_id=d["arm_id"],
            name=d["arm_id"],
            page_config=d["page_config"],
            affected_sections=d["affected_sections"],
        )
        LinUCBParam.objects.create(
            arm=arm,
            A_matrix=make_initial_A(),
            b_vector=make_initial_b(),
            n=5,  # past warmup so we get exploit behaviour
        )
        created.append(arm)
    return created


def _make_visitor_session(visit_number=2):
    """Create a Visitor + Session pair."""
    visitor = Visitor.objects.create()
    session = Session.objects.create(
        visitor=visitor,
        visit_number=visit_number,
    )
    return visitor, session


def _dummy_feature_vector():
    """Return a simple feature vector of length FEATURE_DIM."""
    return [0.0, 0.5, 0.3, 0.2, 0.1, 0.0, 0.2, 1.0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# Unit Tests for the core bandit logic: conflict detection, merging configs, and slate selection.
class ConflictDetectionTests(TestCase):
    """Test _has_conflict() between pairs of arms."""

    def setUp(self):
        _seed_arms()

    def test_same_arm_conflicts(self):
        arm = BanditArm.objects.get(arm_id="hero_compact")
        self.assertTrue(_has_conflict(arm, arm))

    def test_same_variants_key_conflicts(self):
        """Two arms setting variants.pricing should conflict."""
        b = BanditArm.objects.get(arm_id="highlight_plan_2")  # variants.pricing
        c = BanditArm.objects.create(
            arm_id="highlight_plan_3",
            page_config={"variants": {"pricing": "highlight-plan-3"}},
            affected_sections=["pricing"],
        )
        LinUCBParam.objects.create(arm=c, A_matrix=make_initial_A(), b_vector=make_initial_b())
        self.assertTrue(_has_conflict(b, c))

    def test_compact_no_variant_overlap_no_conflict(self):
        """pricing_compact (compact only) vs highlight_plan_2 (variant only) — no variant key overlap."""
        a = BanditArm.objects.get(arm_id="pricing_compact")
        b = BanditArm.objects.get(arm_id="highlight_plan_2")
        self.assertFalse(_has_conflict(a, b))

    def test_dual_promote_conflicts(self):
        a = BanditArm.objects.get(arm_id="promote_pricing")
        b = BanditArm.objects.get(arm_id="promote_services")
        self.assertTrue(_has_conflict(a, b))

    def test_hide_vs_compact_same_section_conflicts(self):
        """Hiding locations conflicts with compacting locations."""
        a = BanditArm.objects.get(arm_id="hide_locations")
        b = BanditArm.objects.get(arm_id="locations_compact")
        self.assertTrue(_has_conflict(a, b))

    def test_different_sections_no_conflict(self):
        a = BanditArm.objects.get(arm_id="hero_compact")
        b = BanditArm.objects.get(arm_id="testimonials_single")
        self.assertFalse(_has_conflict(a, b))

    def test_compact_plus_promote_different_section_no_conflict(self):
        a = BanditArm.objects.get(arm_id="pricing_compact")
        b = BanditArm.objects.get(arm_id="promote_services")
        self.assertFalse(_has_conflict(a, b))


class MergePageConfigTests(TestCase):
    """Test merge_page_configs() produces correct, deterministic output."""

    def setUp(self):
        _seed_arms()

    def test_merge_three_arms(self):
        arms = [
            BanditArm.objects.get(arm_id="hero_compact"),
            BanditArm.objects.get(arm_id="pricing_compact"),
            BanditArm.objects.get(arm_id="testimonials_single"),
        ]
        merged = merge_page_configs(arms)

        self.assertEqual(sorted(merged["compact"]), ["pricing"])
        self.assertEqual(merged["hide"], [])
        self.assertIn("hero", merged["variants"])
        self.assertIn("testimonials", merged["variants"])
        self.assertEqual(merged["variants"]["hero"], "hero-compact")
        self.assertEqual(merged["variants"]["testimonials"], "testimonials-single")

    def test_deterministic_ordering(self):
        """Calling merge twice on same arms gives identical JSON."""
        arms = [
            BanditArm.objects.get(arm_id="services_compact"),
            BanditArm.objects.get(arm_id="faq_compact"),
            BanditArm.objects.get(arm_id="promote_pricing"),
        ]
        m1 = merge_page_configs(arms)
        m2 = merge_page_configs(arms)
        self.assertEqual(json.dumps(m1, sort_keys=True), json.dumps(m2, sort_keys=True))


class ChooseSlateTests(TestCase):
    """Test choose_slate() returns valid, conflict-free slates."""

    def setUp(self):
        _seed_arms()

    def test_returns_up_to_k_arms(self):
        fv = _dummy_feature_vector()
        chosen, explored, scores = choose_slate(fv, k=3, epsilon=0.0)
        self.assertLessEqual(len(chosen), 3)
        self.assertGreater(len(chosen), 0)

    def test_no_duplicates(self):
        fv = _dummy_feature_vector()
        chosen, _, _ = choose_slate(fv, k=3, epsilon=0.0)
        ids = [a.arm_id for a in chosen]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_change_excluded(self):
        fv = _dummy_feature_vector()
        chosen, _, _ = choose_slate(fv, k=3, epsilon=0.0)
        ids = [a.arm_id for a in chosen]
        self.assertNotIn("no_change", ids)

    def test_no_conflict_in_slate(self):
        """Every pair in the slate must be conflict-free."""
        fv = _dummy_feature_vector()
        chosen, _, _ = choose_slate(fv, k=3, epsilon=0.0)
        for i in range(len(chosen)):
            for j in range(i + 1, len(chosen)):
                self.assertFalse(
                    _has_conflict(chosen[i], chosen[j]),
                    f"{chosen[i].arm_id} conflicts with {chosen[j].arm_id}",
                )

    def test_exploration_replaces_one_slot(self):
        """With epsilon=1.0 (forced explore), slate is still valid."""
        fv = _dummy_feature_vector()
        chosen, explored, _ = choose_slate(fv, k=3, epsilon=1.0)
        self.assertTrue(explored)
        self.assertLessEqual(len(chosen), 3)
        # Still no conflicts
        for i in range(len(chosen)):
            for j in range(i + 1, len(chosen)):
                self.assertFalse(_has_conflict(chosen[i], chosen[j]))

# Integration Tests for the full flow of accepting cookies, making decisions, and ending sessions with rewards.
class FirstVisitNoDecisionTests(TestCase):
    """First visit (visit_number == 1) must not create a BanditDecision."""

    def test_accept_cookies_first_visit(self):
        resp = self.client.post(
            "/accept-cookies/",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["visit_number"], 1)
        self.assertEqual(data["chosen_arms"], [])
        self.assertEqual(BanditDecision.objects.count(), 0)


class SecondVisitSlateTests(TestCase):
    """Returning visit (>= 2) should produce a slate decision."""

    def setUp(self):
        _seed_arms()
        # Create a visitor with a completed first session
        self.visitor = Visitor.objects.create()
        first = Session.objects.create(
            visitor=self.visitor,
            visit_number=1,
            is_active=False,
        )
        first.ended_at = first.started_at
        first.save()

    def test_accept_cookies_second_visit(self):
        self.client.cookies["visitor_id"] = str(self.visitor.cookie_id)
        resp = self.client.post(
            "/accept-cookies/",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertGreaterEqual(data["visit_number"], 2)
        self.assertIsInstance(data["chosen_arms"], list)
        self.assertGreater(len(data["chosen_arms"]), 0)
        self.assertLessEqual(len(data["chosen_arms"]), 3)
        self.assertIsInstance(data["page_config"], dict)

        # A BanditDecision row should exist
        self.assertEqual(BanditDecision.objects.count(), 1)
        decision = BanditDecision.objects.first()
        self.assertEqual(decision.chosen_arm_ids, data["chosen_arms"])


class ObservationGatedRewardTests(TestCase):
    """
    Test that end-session only updates arms whose affected sections
    were actually observed by the user.
    """

    def setUp(self):
        _seed_arms()
        self.visitor, self.session = _make_visitor_session(visit_number=2)
        fv = _dummy_feature_vector()

        # Manually create a decision with a known slate
        self.arm_hero = BanditArm.objects.get(arm_id="hero_compact")
        self.arm_testimonials = BanditArm.objects.get(arm_id="testimonials_single")
        self.arm_faq = BanditArm.objects.get(arm_id="faq_compact")

        self.decision = BanditDecision.objects.create(
            session=self.session,
            visitor=self.visitor,
            context_json={},
            context_vector=fv,
            chosen_arm_ids=["hero_compact", "testimonials_single", "faq_compact"],
            merged_page_config=merge_page_configs(
                [self.arm_hero, self.arm_testimonials, self.arm_faq]
            ),
            explore=False,
            epsilon=0.1,
        )

    def _get_n(self, arm_id):
        return LinUCBParam.objects.get(arm__arm_id=arm_id).n

    def test_unobserved_arm_not_updated(self):
        """User sees hero and faq but NOT testimonials → testimonials untouched."""
        now = timezone.now()
        Event.objects.bulk_create([
            Event(session=self.session, event_type="section_view", section="hero", timestamp=now),
            Event(session=self.session, event_type="section_dwell", section="faq", timestamp=now, duration_ms=3000),
        ])

        n_before_testimonials = self._get_n("testimonials_single")
        n_before_hero = self._get_n("hero_compact")
        n_before_faq = self._get_n("faq_compact")

        # Simulate the observation-gated reward logic
        observed = {"hero", "faq"}
        reward = 1.0
        updated = []
        for arm_id in self.decision.chosen_arm_ids:
            arm = BanditArm.objects.get(arm_id=arm_id)
            arm_sections = set(arm.affected_sections or [])
            if not arm_sections or (arm_sections & observed):
                update_stats(arm, self.decision.context_vector, reward)
                updated.append(arm_id)

        self.assertIn("hero_compact", updated)
        self.assertIn("faq_compact", updated)
        self.assertNotIn("testimonials_single", updated)

        self.assertEqual(self._get_n("hero_compact"), n_before_hero + 1)
        self.assertEqual(self._get_n("faq_compact"), n_before_faq + 1)
        self.assertEqual(self._get_n("testimonials_single"), n_before_testimonials)

    def test_observed_arm_is_updated(self):
        """User sees testimonials → arm IS updated."""
        now = timezone.now()
        Event.objects.create(
            session=self.session, event_type="section_view",
            section="testimonials", timestamp=now,
        )

        n_before = self._get_n("testimonials_single")
        update_stats(self.arm_testimonials, self.decision.context_vector, 1.0)
        self.assertEqual(self._get_n("testimonials_single"), n_before + 1)


class IdempotencyTests(TestCase):
    """Calling /end-session/ twice must not double-increment stats."""

    def setUp(self):
        _seed_arms()
        self.visitor = Visitor.objects.create()
        # First session (ended)
        s1 = Session.objects.create(visitor=self.visitor, visit_number=1, is_active=False)
        s1.ended_at = s1.started_at
        s1.save()
        # Second session
        self.session = Session.objects.create(
            visitor=self.visitor,
            visit_number=2,
        )
        fv = _dummy_feature_vector()
        arm_hero = BanditArm.objects.get(arm_id="hero_compact")
        self.decision = BanditDecision.objects.create(
            session=self.session,
            visitor=self.visitor,
            context_json={},
            context_vector=fv,
            chosen_arm_ids=["hero_compact"],
            merged_page_config=merge_page_configs([arm_hero]),
            explore=False,
            epsilon=0.1,
        )

    def test_double_end_session_no_double_update(self):
        now = timezone.now()
        Event.objects.create(
            session=self.session, event_type="section_view",
            section="hero", timestamp=now,
        )

        n_before = LinUCBParam.objects.get(arm__arm_id="hero_compact").n

        # End session payload
        payload = json.dumps({"session_id": str(self.session.session_id)})

        # Set cookies for auth
        self.client.cookies["visitor_id"] = str(self.visitor.cookie_id)
        self.client.cookies["sw_cookie_consent"] = "accepted"

        resp1 = self.client.post(
            "/end-session/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(resp1.status_code, 200)

        n_after_first = LinUCBParam.objects.get(arm__arm_id="hero_compact").n
        self.assertEqual(n_after_first, n_before + 1)

        # Second call — should be idempotent
        resp2 = self.client.post(
            "/end-session/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 200)

        n_after_second = LinUCBParam.objects.get(arm__arm_id="hero_compact").n
        self.assertEqual(
            n_after_second, n_after_first,
            "Stats double-incremented on second end-session call!",
        )

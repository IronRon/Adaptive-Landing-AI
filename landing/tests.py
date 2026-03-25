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
from datetime import timedelta

from django.test import TestCase, RequestFactory
from django.utils import timezone

from landing.models import (
    BanditArm,
    BanditDecision,
    Event,
    LinearArmParam,
    Session,
    Visitor,
)
from landing.bandit_utils import (
    EPSILON,
    FEATURE_DIM,
    MIN_PULLS_PER_ARM,
    _has_conflict,
    _predict,
    _conflicts_with_slate,
    build_context,
    choose_arm,
    choose_slate,
    make_initial_A,
    make_initial_b,
    merge_page_configs,
    update_stats,
)
from landing.utils import _saturate, _score_intent_group, compute_session_intent_scores


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
        LinearArmParam.objects.create(
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
        # Function under test: _has_conflict()
        arm = BanditArm.objects.get(arm_id="hero_compact")
        self.assertTrue(_has_conflict(arm, arm))

    def test_same_variants_key_conflicts(self):
        # Function under test: _has_conflict()
        """Two arms setting variants.pricing should conflict."""
        b = BanditArm.objects.get(arm_id="highlight_plan_2")  # variants.pricing
        c = BanditArm.objects.create(
            arm_id="highlight_plan_3",
            page_config={"variants": {"pricing": "highlight-plan-3"}},
            affected_sections=["pricing"],
        )
        LinearArmParam.objects.create(arm=c, A_matrix=make_initial_A(), b_vector=make_initial_b())
        self.assertTrue(_has_conflict(b, c))

    def test_compact_no_variant_overlap_no_conflict(self):
        # Function under test: _has_conflict()
        """pricing_compact (compact only) vs highlight_plan_2 (variant only) â€” no variant key overlap."""
        a = BanditArm.objects.get(arm_id="pricing_compact")
        b = BanditArm.objects.get(arm_id="highlight_plan_2")
        self.assertFalse(_has_conflict(a, b))

    def test_dual_promote_conflicts(self):
        # Function under test: _has_conflict()
        a = BanditArm.objects.get(arm_id="promote_pricing")
        b = BanditArm.objects.get(arm_id="promote_services")
        self.assertTrue(_has_conflict(a, b))

    def test_hide_vs_compact_same_section_conflicts(self):
        # Function under test: _has_conflict()
        """Hiding locations conflicts with compacting locations."""
        a = BanditArm.objects.get(arm_id="hide_locations")
        b = BanditArm.objects.get(arm_id="locations_compact")
        self.assertTrue(_has_conflict(a, b))

    def test_different_sections_no_conflict(self):
        # Function under test: _has_conflict()
        a = BanditArm.objects.get(arm_id="hero_compact")
        b = BanditArm.objects.get(arm_id="testimonials_single")
        self.assertFalse(_has_conflict(a, b))

    def test_compact_plus_promote_different_section_no_conflict(self):
        # Function under test: _has_conflict()
        a = BanditArm.objects.get(arm_id="pricing_compact")
        b = BanditArm.objects.get(arm_id="promote_services")
        self.assertFalse(_has_conflict(a, b))


class MergePageConfigTests(TestCase):
    """Test merge_page_configs() produces correct, deterministic output."""

    def setUp(self):
        _seed_arms()

    def test_merge_three_arms(self):
        # Function under test: merge_page_configs()
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
        # Function under test: merge_page_configs()
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
        # Function under test: choose_slate()
        fv = _dummy_feature_vector()
        chosen, explored, scores = choose_slate(fv, k=3, epsilon=0.0)
        self.assertLessEqual(len(chosen), 3)
        self.assertGreater(len(chosen), 0)

    def test_no_duplicates(self):
        # Function under test: choose_slate()
        fv = _dummy_feature_vector()
        chosen, _, _ = choose_slate(fv, k=3, epsilon=0.0)
        ids = [a.arm_id for a in chosen]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_change_excluded(self):
        # Function under test: choose_slate()
        fv = _dummy_feature_vector()
        chosen, _, _ = choose_slate(fv, k=3, epsilon=0.0)
        ids = [a.arm_id for a in chosen]
        self.assertNotIn("no_change", ids)

    def test_no_conflict_in_slate(self):
        # Function under test: choose_slate()
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
        # Function under test: choose_slate()
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
        # Function under test: accept_cookies() endpoint
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
        # Function under test: accept_cookies() endpoint
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
        return LinearArmParam.objects.get(arm__arm_id=arm_id).n

    def test_unobserved_arm_not_updated(self):
        # Function under test: update_stats() (observation-gated reward path)
        """User sees hero and faq but NOT testimonials â†’ testimonials untouched."""
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
        # Function under test: update_stats()
        """User sees testimonials â†’ arm IS updated."""
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
        # Function under test: end_session() endpoint
        now = timezone.now()
        Event.objects.create(
            session=self.session, event_type="section_view",
            section="hero", timestamp=now,
        )

        n_before = LinearArmParam.objects.get(arm__arm_id="hero_compact").n

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

        n_after_first = LinearArmParam.objects.get(arm__arm_id="hero_compact").n
        self.assertEqual(n_after_first, n_before + 1)

        # Second call â€” should be idempotent
        resp2 = self.client.post(
            "/end-session/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 200)

        n_after_second = LinearArmParam.objects.get(arm__arm_id="hero_compact").n
        self.assertEqual(
            n_after_second, n_after_first,
            "Stats double-incremented on second end-session call!",
        )


class BanditMatrixAndPredictionTests(TestCase):
    """Unit tests for matrix/vector initializers and linear prediction helper."""

    def test_make_initial_A_shape_and_diagonal(self):
        # Function under test: make_initial_A()
        A = make_initial_A()
        self.assertEqual(len(A), FEATURE_DIM)
        self.assertEqual(len(A[0]), FEATURE_DIM)
        for i in range(FEATURE_DIM):
            for j in range(FEATURE_DIM):
                expected = 1.0 if i == j else 0.0
                self.assertAlmostEqual(A[i][j], expected, places=7)

    def test_make_initial_b_is_zero_vector(self):
        # Function under test: make_initial_b()
        b = make_initial_b()
        self.assertEqual(len(b), FEATURE_DIM)
        self.assertEqual(sum(b), 0.0)

    def test_predict_identity_matches_dot_product(self):
        # Function under test: _predict()
        x = [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        b = [0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 1.0]
        score = _predict(make_initial_A(), b, x)
        expected = sum(i * j for i, j in zip(x, b))
        self.assertAlmostEqual(score, expected, places=7)


class BuildContextTests(TestCase):
    """Unit tests for build_context() extraction and feature-vector mapping."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_build_context_without_prior_session_defaults_to_zero_scores(self):
        # Function under test: build_context()
        visitor = Visitor.objects.create()
        request = self.factory.get("/", HTTP_USER_AGENT="Mozilla/5.0")

        context, fv = build_context(visitor, request)

        self.assertEqual(len(fv), FEATURE_DIM)
        self.assertEqual(context["is_mobile"], False)
        self.assertEqual(context["visit_count"], 0)
        self.assertEqual(context["price_score"], 0.0)
        self.assertEqual(context["service_score"], 0.0)
        self.assertEqual(context["trust_score"], 0.0)
        self.assertEqual(context["location_score"], 0.0)
        self.assertEqual(context["contact_score"], 0.0)

    def test_build_context_uses_latest_ended_session_and_mobile_flag(self):
        # Function under test: build_context()
        visitor = Visitor.objects.create()
        now = timezone.now()
        s1 = Session.objects.create(visitor=visitor, visit_number=1, is_active=False)
        s1.ended_at = now
        s1.price_intent_score = 0.11
        s1.service_intent_score = 0.22
        s1.trust_intent_score = 0.33
        s1.location_intent_score = 0.44
        s1.contact_intent_score = 0.55
        s1.save()

        # Latest ended session should be used for intent values.
        s2 = Session.objects.create(visitor=visitor, visit_number=2, is_active=False)
        s2.ended_at = now + timedelta(seconds=5)
        s2.price_intent_score = 0.66
        s2.service_intent_score = 0.77
        s2.trust_intent_score = 0.88
        s2.location_intent_score = 0.12
        s2.contact_intent_score = 0.34
        s2.save()

        request = self.factory.get("/", HTTP_USER_AGENT="Mozilla/5.0 (iPhone)")
        context, fv = build_context(visitor, request)

        self.assertEqual(context["is_mobile"], True)
        self.assertAlmostEqual(context["price_score"], 0.66)
        self.assertAlmostEqual(context["service_score"], 0.77)
        self.assertAlmostEqual(context["trust_score"], 0.88)
        self.assertAlmostEqual(context["location_score"], 0.12)
        self.assertAlmostEqual(context["contact_score"], 0.34)
        self.assertEqual(len(fv), FEATURE_DIM)


class ChooseArmTests(TestCase):
    """Unit tests for legacy single-arm epsilon-greedy selector."""

    def setUp(self):
        _seed_arms()

    def test_choose_arm_exploit_picks_highest_predicted(self):
        # Function under test: choose_arm()
        arm_best = BanditArm.objects.get(arm_id="hero_compact")
        param_best = LinearArmParam.objects.get(arm=arm_best)
        param_best.A_matrix = make_initial_A()
        param_best.b_vector = [2.0] + [0.0] * (FEATURE_DIM - 1)
        param_best.n = MIN_PULLS_PER_ARM
        param_best.save()

        # Keep all other arms at zero prediction and warmup-complete.
        LinearArmParam.objects.exclude(arm=arm_best).update(
            A_matrix=make_initial_A(),
            b_vector=make_initial_b(),
            n=MIN_PULLS_PER_ARM,
        )

        fv = [1.0] + [0.0] * (FEATURE_DIM - 1)
        chosen, explored, predicted = choose_arm(fv, epsilon=0.0)

        self.assertFalse(explored)
        self.assertEqual(chosen.arm_id, "hero_compact")
        self.assertIsNotNone(predicted)
        self.assertGreater(predicted, 0.0)

    def test_choose_arm_forced_explore_returns_none_score(self):
        # Function under test: choose_arm()
        fv = _dummy_feature_vector()
        chosen, explored, predicted = choose_arm(fv, epsilon=1.0)

        self.assertTrue(explored)
        self.assertIsNotNone(chosen)
        self.assertIsNone(predicted)

    def test_choose_arm_warmup_selects_under_pulled_arm(self):
        # Function under test: choose_arm()
        target = BanditArm.objects.get(arm_id="hero_compact")
        LinearArmParam.objects.filter(arm=target).update(n=0)
        LinearArmParam.objects.exclude(arm=target).update(n=MIN_PULLS_PER_ARM)

        chosen, explored, predicted = choose_arm(_dummy_feature_vector(), epsilon=0.0)
        self.assertTrue(explored)
        self.assertEqual(chosen.arm_id, "hero_compact")
        self.assertIsNone(predicted)


class ConflictWithSlateTests(TestCase):
    """Unit tests for _conflicts_with_slate() convenience wrapper."""

    def setUp(self):
        _seed_arms()

    def test_conflicts_with_slate_true_when_any_conflict_exists(self):
        # Function under test: _conflicts_with_slate()
        arm = BanditArm.objects.get(arm_id="locations_compact")
        slate = [BanditArm.objects.get(arm_id="hide_locations")]
        self.assertTrue(_conflicts_with_slate(arm, slate))

    def test_conflicts_with_slate_false_for_compatible_slate(self):
        # Function under test: _conflicts_with_slate()
        arm = BanditArm.objects.get(arm_id="testimonials_single")
        slate = [BanditArm.objects.get(arm_id="pricing_compact")]
        self.assertFalse(_conflicts_with_slate(arm, slate))


class UtilsScoringUnitTests(TestCase):
    """Unit tests for non-legacy scoring helpers in landing.utils."""

    def setUp(self):
        self.visitor = Visitor.objects.create()
        self.session = Session.objects.create(visitor=self.visitor, visit_number=1)

    def test_saturate_bounds_and_midpoint(self):
        # Function under test: _saturate()
        self.assertEqual(_saturate(0, 10), 0.0)
        self.assertEqual(_saturate(-5, 10), 0.0)
        self.assertAlmostEqual(_saturate(10, 10), 0.5)

    def test_score_intent_group_zero_when_no_matching_events(self):
        # Function under test: _score_intent_group()
        events = Event.objects.filter(session=self.session)
        score = _score_intent_group(events, ["pricing"])
        self.assertEqual(score, 0.0)

    def test_score_intent_group_combines_all_signals(self):
        # Function under test: _score_intent_group()
        now = timezone.now()
        Event.objects.create(
            session=self.session,
            event_type="click",
            section="pricing",
            is_cta=True,
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="hover",
            section="pricing",
            duration_ms=3000,
            is_cta=True,
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="section_dwell",
            section="pricing",
            duration_ms=15000,
            timestamp=now,
        )

        score = _score_intent_group(Event.objects.filter(session=self.session), ["pricing"])
        # click=1, hover=3000, dwell=15000, cta_click=1, cta_hover=3000
        expected = (
            _saturate(1, 3)
            + _saturate(3000, 5000)
            + _saturate(15000, 15000)
            + 1.0
            + _saturate(3000, 3000)
        ) / 5.0
        self.assertAlmostEqual(score, expected, places=6)


class ComputeSessionIntentScoresTests(TestCase):
    """Unit tests for compute_session_intent_scores()."""

    def setUp(self):
        self.visitor = Visitor.objects.create()
        self.session = Session.objects.create(visitor=self.visitor, visit_number=1)

    def test_compute_session_intent_scores_empty_session_defaults(self):
        # Function under test: compute_session_intent_scores()
        scores = compute_session_intent_scores(self.session)
        self.assertEqual(scores["primary_intent"], "unknown")
        self.assertEqual(scores["max_scroll_pct"], 0)
        self.assertEqual(scores["engaged_time_ms"], 0)
        self.assertFalse(scores["cta_clicked"])
        self.assertFalse(scores["pricing_cta_clicked"])

    def test_compute_session_intent_scores_pricing_path_and_quick_scan(self):
        # Function under test: compute_session_intent_scores()
        now = timezone.now()
        Event.objects.create(
            session=self.session,
            event_type="click",
            section="pricing",
            element="pricing-cta",
            is_cta=True,
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="hover",
            section="pricing",
            duration_ms=2000,
            is_cta=True,
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="section_dwell",
            section="pricing",
            duration_ms=2000,
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="scroll_depth",
            metadata={"depth": 85},
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="time_on_page",
            duration_ms=4500,
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="time_on_page",
            metadata={"seconds": 7},
            timestamp=now,
        )

        scores = compute_session_intent_scores(self.session)
        self.assertEqual(scores["primary_intent"], "price")
        self.assertEqual(scores["max_scroll_pct"], 85)
        self.assertEqual(scores["engaged_time_ms"], 7000)
        self.assertTrue(scores["cta_clicked"])
        self.assertTrue(scores["pricing_cta_clicked"])
        self.assertEqual(scores["quick_scan_score"], 1.0)
        self.assertGreater(scores["price_intent_score"], 0.1)


class TrackInteractionsEndpointTests(TestCase):
    """Integration tests for POST /track-interactions/."""

    def setUp(self):
        self.visitor = Visitor.objects.create()
        self.session = Session.objects.create(visitor=self.visitor, visit_number=1)

    def test_track_interactions_rejects_non_post(self):
        # Function under test: track_interactions() endpoint
        resp = self.client.get("/track-interactions/")
        self.assertEqual(resp.status_code, 405)

    def test_track_interactions_validates_json_and_session_id(self):
        # Function under test: track_interactions() endpoint
        bad_json = self.client.post("/track-interactions/", data="not-json", content_type="application/json")
        self.assertEqual(bad_json.status_code, 400)

        missing_session = self.client.post(
            "/track-interactions/",
            data=json.dumps({"events": []}),
            content_type="application/json",
        )
        self.assertEqual(missing_session.status_code, 400)

        unknown_session = self.client.post(
            "/track-interactions/",
            data=json.dumps({"session_id": str(uuid.uuid4()), "events": []}),
            content_type="application/json",
        )
        self.assertEqual(unknown_session.status_code, 404)

    def test_track_interactions_stores_events_and_metadata(self):
        # Function under test: track_interactions() endpoint
        payload = {
            "session_id": str(self.session.session_id),
            "events": [
                {
                    "type": "click",
                    "ts": "2026-03-20T10:00:00Z",
                    "url": "/",
                    "section": "hero",
                    "element": "hero-cta",
                    "is_cta": True,
                    "tag": "button",
                    "text": "Get Started",
                },
                {
                    "type": "section_dwell",
                    "ts": "bad-ts",
                    "section": "pricing",
                    "duration_ms": 2500,
                    "custom_flag": "x",
                },
            ],
        }

        resp = self.client.post(
            "/track-interactions/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["stored"], 2)

        self.assertEqual(Event.objects.filter(session=self.session).count(), 2)
        first = Event.objects.filter(session=self.session).order_by("id").first()
        second = Event.objects.filter(session=self.session).order_by("id")[1]
        self.assertEqual(first.event_type, "click")
        self.assertEqual(first.section, "hero")
        self.assertEqual(first.metadata.get("tag"), "button")
        self.assertEqual(first.metadata.get("text"), "Get Started")
        self.assertEqual(second.event_type, "section_dwell")
        self.assertEqual(second.duration_ms, 2500)
        self.assertEqual(second.metadata.get("custom_flag"), "x")


class DemoLandingEndpointTests(TestCase):
    """Integration test for GET /demo/ static landing page endpoint."""

    def test_demo_landing_page_renders_template(self):
        # Function under test: demo_landing_page() endpoint
        resp = self.client.get("/demo/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "landing/landing_page.html")


class EndSessionValidationTests(TestCase):
    """Integration tests for validation and score persistence in /end-session/."""

    def setUp(self):
        self.visitor = Visitor.objects.create()
        self.session = Session.objects.create(visitor=self.visitor, visit_number=1)

    def test_end_session_requires_consent_or_visitor_cookie(self):
        # Function under test: end_session() endpoint
        payload = json.dumps({"session_id": str(self.session.session_id)})
        resp = self.client.post("/end-session/", data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_end_session_persists_computed_scores(self):
        # Function under test: end_session() endpoint
        now = timezone.now()
        Event.objects.create(
            session=self.session,
            event_type="click",
            section="pricing",
            element="cta-primary",
            is_cta=True,
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="scroll_depth",
            metadata={"depth": 78},
            timestamp=now,
        )
        Event.objects.create(
            session=self.session,
            event_type="section_dwell",
            section="pricing",
            duration_ms=3000,
            timestamp=now,
        )

        self.client.cookies["visitor_id"] = str(self.visitor.cookie_id)
        self.client.cookies["sw_cookie_consent"] = "accepted"

        payload = json.dumps({"session_id": str(self.session.session_id)})
        resp = self.client.post("/end-session/", data=payload, content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        self.session.refresh_from_db()
        self.assertFalse(self.session.is_active)
        self.assertIsNotNone(self.session.ended_at)
        self.assertTrue(self.session.cta_clicked)
        self.assertTrue(self.session.pricing_cta_clicked)
        self.assertEqual(self.session.max_scroll_pct, 78)
        self.assertEqual(self.session.primary_intent, "price")


class AcceptCookiesValidationTests(TestCase):
    """Integration validation tests for /accept-cookies/."""

    def test_accept_cookies_rejects_non_post(self):
        # Function under test: accept_cookies() endpoint
        resp = self.client.get("/accept-cookies/")
        self.assertEqual(resp.status_code, 405)

    def test_accept_cookies_invalid_cookie_creates_new_visitor(self):
        # Function under test: accept_cookies() endpoint
        self.client.cookies["visitor_id"] = str(uuid.uuid4())
        resp = self.client.post("/accept-cookies/", content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_new"])
        self.assertEqual(data["visit_number"], 1)

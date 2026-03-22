# Testing Guide for landing/tests.py

This document explains what is tested in landing/tests.py, in beginner terms.

## High-level: How these tests work

These tests use Django TestCase.

What that means:
- Each test runs with a clean temporary test database.
- Test data is created inside each test or setUp method.
- Data from one test does not leak into another test.
- Django test client is used to simulate HTTP requests to endpoints like /accept-cookies/ and /end-session/.
- Assertions check expected behavior (status codes, returned JSON, saved database values).

In short, this file tests both:
- Unit behavior of core bandit/scoring functions.
- Integration behavior of full request flows and endpoint side effects.

## Unit tests

These focus on logic-level behavior for specific functions.

### 1) ConflictDetectionTests
Functions tested:
- _has_conflict

What is verified:
- Same arm conflicts with itself.
- Arms that set same variant key conflict.
- Dual promote actions conflict.
- Hide vs compact on same section conflict.
- Independent section edits do not conflict.

### 2) MergePageConfigTests
Function tested:
- merge_page_configs

What is verified:
- Combined config from multiple arms is correct.
- Merge output is deterministic (same inputs give same JSON output).

### 3) ChooseSlateTests
Function tested:
- choose_slate

What is verified:
- Returns at most k arms.
- No duplicate arms in the slate.
- no_change arm is excluded.
- Every pair in selected slate is conflict-free.
- Forced exploration still returns valid conflict-free slate.

### 4) BanditMatrixAndPredictionTests
Functions tested:
- make_initial_A
- make_initial_b
- _predict

What is verified:
- Initial A matrix has correct shape and identity diagonal.
- Initial b vector is all zeros.
- Prediction helper matches expected dot-product behavior when A is identity.

### 5) BuildContextTests
Function tested:
- build_context

What is verified:
- No prior ended session gives zero/default intent scores.
- Latest ended session values are used for intent features.
- Mobile flag is correctly derived from user agent.
- Feature vector has expected dimension.

### 6) ChooseArmTests
Function tested:
- choose_arm (legacy single-arm selector)

What is verified:
- Exploit mode picks highest predicted arm.
- Forced explore returns an explored choice with no predicted score.
- Warmup logic selects under-pulled arm.

### 7) ConflictWithSlateTests
Function tested:
- _conflicts_with_slate

What is verified:
- Returns true when candidate conflicts with any arm in slate.
- Returns false when candidate is compatible with slate.

### 8) UtilsScoringUnitTests
Functions tested:
- _saturate
- _score_intent_group

What is verified:
- Saturation behavior for zero, negative, midpoint values.
- Intent group score is zero with no matching events.
- Intent group score combines click/hover/dwell/cta signals correctly.

### 9) ComputeSessionIntentScoresTests
Function tested:
- compute_session_intent_scores

What is verified:
- Empty session returns safe defaults.
- Pricing interaction path sets primary intent to price.
- Scroll depth, engaged time, CTA flags, quick scan score, and intent score values are computed correctly.

## Integration tests

These focus on full user/API flows and database side effects.

### 1) FirstVisitNoDecisionTests
Flow tested:
- POST /accept-cookies/ on first visit

What is verified:
- Visit number is 1.
- No chosen arms are returned.
- No BanditDecision row is created.

### 2) SecondVisitSlateTests
Flow tested:
- Returning visitor POST /accept-cookies/

What is verified:
- Visit number is at least 2.
- Slate is returned (list of chosen arms).
- Merged page_config is returned.
- BanditDecision row is created and matches chosen arms.

### 3) ObservationGatedRewardTests
Flow tested:
- Reward updates only for observed sections in chosen slate

What is verified:
- Arms tied to observed sections are updated.
- Arms tied to unobserved sections are not updated.
- Update counts (n) change only for eligible arms.

### 4) IdempotencyTests
Flow tested:
- Calling POST /end-session/ twice

What is verified:
- First call updates stats once.
- Second call does not double-increment stats.
- Endpoint is idempotent for repeat submissions.

### 5) TrackInteractionsEndpointTests
Flow tested:
- POST /track-interactions/

What is verified:
- Rejects non-POST requests.
- Validates JSON and session_id.
- Stores events and extra metadata fields.
- Returns stored event count.

### 6) DemoLandingEndpointTests
Flow tested:
- GET /demo/

What is verified:
- Endpoint returns HTTP 200.
- Correct template is rendered.

### 7) EndSessionValidationTests
Flow tested:
- POST /end-session/

What is verified:
- Requires consent or valid visitor cookie (403 otherwise).
- Persists computed session fields after valid end-session request.
- Confirms session is closed and intent/engagement fields are saved.

### 8) AcceptCookiesValidationTests
Flow tested:
- POST /accept-cookies/

What is verified:
- Rejects non-POST requests.
- Invalid visitor cookie falls back to creating a new visitor flow.

## End-to-end behavior covered by this file

Taken together, these tests cover the main product path:
1. Visitor accepts cookies.
2. First visit has no bandit decision.
3. Returning visit can receive a slate decision.
4. Frontend interaction events are tracked.
5. Session is ended and intent scores are computed and saved.
6. Reward updates are applied safely and only to observed arms.
7. Duplicate end-session calls do not corrupt learning stats.
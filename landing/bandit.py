import math
from .models import BanditArm

class SectionBandit:
    """Simple population-level bandit using UCB1."""

    def __init__(self):
        self.arms = list(BanditArm.objects.all())

    def get_global_scores(self):
        """Return UCB1 score for each section."""
        # total pulls across all arms
        total_pulls = sum(a.pulls for a in self.arms)

        # To avoid returning infinite values (which JSON can't encode) and to
        # ensure untried arms get a positive exploration bonus, compute the
        # log term using (total_pulls + number_of_arms). This gives a finite
        # positive exploration score for arms with 0 pulls while preserving
        # the UCB-style tradeoff for arms with pulls > 0.
        #  n_arms is added to avoid infinite values when all arms have 0 pulls
        n_arms = max(1, len(self.arms))
        base_log = math.log(max(1, total_pulls + n_arms))

        scores = {}
        for arm in self.arms:
            denom = arm.pulls or 1
            mean = (arm.reward / arm.pulls) if arm.pulls > 0 else 0
            exploration = math.sqrt(2 * base_log / denom)
            scores[arm.section] = mean + exploration

        return scores

    def update(self, section_rewards):
        """section_rewards = dict like {'pricing': 0.5, 'cta': 0.2}"""
        for section, reward in section_rewards.items():
            arm = BanditArm.objects.get(section=section)
            arm.pulls += 1
            arm.reward += reward
            arm.save()

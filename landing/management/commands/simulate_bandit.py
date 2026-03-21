"""
Management command: simulate_bandit

Runs a synthetic, persona-driven simulator against the real contextual slate bandit
selection/update code without changing bandit core logic.

Example:
    python manage.py simulate_bandit --rounds 20000 --k 3 --epsilon 0.1 --seed 42
"""

from __future__ import annotations

import random
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from landing.bandit_utils import EPSILON as DEFAULT_EPSILON
from landing.bandit_utils import choose_slate, update_stats
from landing.models import BanditArm
from landing.simulator import (
    SimRound,
    build_synthetic_context,
    cumulative_average,
    moving_average,
    no_change_slate,
    random_non_conflicting_slate,
    reset_bandit_params,
    save_rounds_csv,
    simulate_reward,
    summarize,
    choose_persona,
)


class Command(BaseCommand):
    help = "Run synthetic persona-based simulation using real bandit selection/update functions."

    def add_arguments(self, parser):
        parser.add_argument("--rounds", type=int, default=20000, help="Number of simulation rounds.")
        parser.add_argument("--k", type=int, default=3, help="Slate size (number of arms per round).")
        parser.add_argument("--epsilon", type=float, default=DEFAULT_EPSILON, help="Epsilon passed to choose_slate.")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
        parser.add_argument(
            "--reset-params",
            action="store_true",
            help="Reset LinUCB and legacy bandit stats before simulation.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not update DB model params (evaluate only).",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="sim_outputs",
            help="Output directory (relative to project root unless absolute path).",
        )
        parser.add_argument(
            "--ma-window",
            type=int,
            default=200,
            help="Moving-average window for learning-curve plot.",
        )

    def handle(self, *args, **options):
        # --- 1) Read and validate CLI inputs ---------------------------------
        rounds = options["rounds"]
        k = options["k"]
        epsilon = float(options["epsilon"])
        seed = options["seed"]
        reset_params_flag = options["reset_params"]
        dry_run = options["dry_run"]
        ma_window = max(1, int(options["ma_window"]))

        if rounds <= 0:
            raise CommandError("--rounds must be > 0")
        if k <= 0:
            raise CommandError("--k must be > 0")
        if not (0.0 <= epsilon <= 1.0):
            raise CommandError("--epsilon must be in [0, 1]")

        # --- 2) Seed randomness for reproducible experiments -----------------
        rng = random.Random(seed)
        random.seed(seed)

        # --- 3) Prepare output folder for CSV + plots ------------------------
        # Resolve output path relative to Django BASE_DIR by default.
        output_dir = Path(options["output_dir"])
        if not output_dir.is_absolute():
            output_dir = Path(settings.BASE_DIR) / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # --- 4) Load real arms from DB and verify simulation prerequisites ---
        all_active_arms = list(BanditArm.objects.filter(is_active=True).order_by("arm_id"))
        if not all_active_arms:
            raise CommandError("No active BanditArm rows found. Seed arms first.")

        candidate_arms = [arm for arm in all_active_arms if arm.arm_id != "no_change"]
        if not candidate_arms:
            raise CommandError("No active non-control arms found (all are 'no_change').")

        # Optional: wipe learned parameters so this run starts from scratch.
        if reset_params_flag:
            self.stdout.write(self.style.WARNING("Resetting bandit params/stat tables..."))
            reset_bandit_params()

        self.stdout.write(
            f"Starting simulation: rounds={rounds}, k={k}, epsilon={epsilon:.3f}, "
            f"seed={seed}, reset_params={reset_params_flag}, dry_run={dry_run}"
        )

        rows: list[SimRound] = []
        bandit_rewards = []
        random_rewards = []
        no_change_rewards = []

        # --- 5) Main simulation loop ----------------------------------------
        # Each round uses one synthetic visitor context and evaluates 3 policies:
        #  - bandit (learns unless --dry-run)
        #  - random baseline (no learning)
        #  - no-change baseline (no learning)
        for round_idx in range(1, rounds + 1):
            # Generate one synthetic visitor (persona + feature vector).
            persona = choose_persona(rng)
            context, feature_vector = build_synthetic_context(persona, rng)

            # (A) Bandit policy: real selection function + real DB update path.
            chosen_bandit_arms, _explored, _scores = choose_slate(feature_vector, k=k, epsilon=epsilon)
            if not chosen_bandit_arms:
                # Safety fallback if no valid slate is produced.
                chosen_bandit_arms = random_non_conflicting_slate(all_active_arms, k=k, rng=rng)

            bandit_reward, bandit_p = simulate_reward(persona, chosen_bandit_arms, context, rng)
            if not dry_run:
                # Learning step: update the same model params used in production.
                for arm in chosen_bandit_arms:
                    if arm.arm_id != "no_change":
                        update_stats(arm, feature_vector, bandit_reward)

            rows.append(
                SimRound(
                    round_idx=round_idx,
                    policy="bandit",
                    persona=persona,
                    device=context["device"],
                    chosen_arm_ids=[arm.arm_id for arm in chosen_bandit_arms],
                    p_click=bandit_p,
                    reward=bandit_reward,
                )
            )
            bandit_rewards.append(bandit_reward)

            # (B) Random baseline: same context, no model updates.
            chosen_random_arms = random_non_conflicting_slate(all_active_arms, k=k, rng=rng)
            random_reward, random_p = simulate_reward(persona, chosen_random_arms, context, rng)
            rows.append(
                SimRound(
                    round_idx=round_idx,
                    policy="random",
                    persona=persona,
                    device=context["device"],
                    chosen_arm_ids=[arm.arm_id for arm in chosen_random_arms],
                    p_click=random_p,
                    reward=random_reward,
                )
            )
            random_rewards.append(random_reward)

            # (C) No-change baseline: control treatment only, no model updates.
            chosen_control_arms = no_change_slate(all_active_arms)
            no_change_reward, no_change_p = simulate_reward(persona, chosen_control_arms, context, rng)
            rows.append(
                SimRound(
                    round_idx=round_idx,
                    policy="no_change",
                    persona=persona,
                    device=context["device"],
                    chosen_arm_ids=[arm.arm_id for arm in chosen_control_arms],
                    p_click=no_change_p,
                    reward=no_change_reward,
                )
            )
            no_change_rewards.append(no_change_reward)

            if round_idx % 1000 == 0 or round_idx == rounds:
                self.stdout.write(f"  progress: {round_idx}/{rounds}")

        # --- 6) Persist round-level results ---------------------------------
        csv_path = output_dir / f"simulate_bandit_seed{seed}_r{rounds}.csv"
        save_rounds_csv(rows, csv_path)

        # --- 7) Build learning curves for each policy ------------------------
        bandit_curve = cumulative_average(bandit_rewards)
        random_curve = cumulative_average(random_rewards)
        no_change_curve = cumulative_average(no_change_rewards)

        bandit_ma = moving_average(bandit_rewards, window=ma_window)
        random_ma = moving_average(random_rewards, window=ma_window)
        no_change_ma = moving_average(no_change_rewards, window=ma_window)

        # Lazy import to keep command usable even if matplotlib is missing.
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as exc:
            raise CommandError(
                "matplotlib is required for plotting. Install it in your env, e.g. 'pip install matplotlib'."
            ) from exc

        # --- 8) Render cumulative-average comparison plot --------------------
        x = list(range(1, rounds + 1))

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(x, bandit_curve, label="bandit cumulative avg", linewidth=2)
        ax.plot(x, random_curve, label="random cumulative avg", linewidth=2)
        ax.plot(x, no_change_curve, label="no_change cumulative avg", linewidth=2)
        ax.set_xlabel("Round")
        ax.set_ylabel("Average Reward (CTR)")
        ax.set_title("Cumulative Average Reward")
        ax.legend()
        ax.grid(True, alpha=0.25)
        cumulative_plot = output_dir / f"simulate_bandit_cumavg_seed{seed}_r{rounds}.png"
        fig.tight_layout()
        fig.savefig(cumulative_plot, dpi=140)
        plt.close(fig)

        # --- 9) Render moving-average comparison plot ------------------------
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(x, bandit_ma, label=f"bandit moving avg ({ma_window})", linewidth=2)
        ax.plot(x, random_ma, label=f"random moving avg ({ma_window})", linewidth=2)
        ax.plot(x, no_change_ma, label=f"no_change moving avg ({ma_window})", linewidth=2)
        ax.set_xlabel("Round")
        ax.set_ylabel("Reward")
        ax.set_title("Learning Curve (Moving Average)")
        ax.legend()
        ax.grid(True, alpha=0.25)
        moving_plot = output_dir / f"simulate_bandit_movingavg_seed{seed}_r{rounds}.png"
        fig.tight_layout()
        fig.savefig(moving_plot, dpi=140)
        plt.close(fig)

        # --- 10) Aggregate summary metrics for quick inspection --------------
        summary = summarize(rows)

        self.stdout.write("\nSimulation complete.")
        self.stdout.write(f"CSV saved: {csv_path}")
        self.stdout.write(f"Plot saved: {cumulative_plot}")
        self.stdout.write(f"Plot saved: {moving_plot}")
        self.stdout.write("\nSummary stats:")

        for policy in ("bandit", "random", "no_change"):
            policy_stats = summary.get(policy)
            if not policy_stats:
                continue
            self.stdout.write(
                f"  {policy:<10} overall_ctr={policy_stats['overall_ctr']:.4f} "
                f"n={int(policy_stats['n'])}"
            )
            for key in sorted(policy_stats.keys()):
                if key.startswith("persona:"):
                    self.stdout.write(f"    {key}: {policy_stats[key]:.4f}")
            for key in sorted(policy_stats.keys()):
                if key.startswith("device:"):
                    self.stdout.write(f"    {key}: {policy_stats[key]:.4f}")

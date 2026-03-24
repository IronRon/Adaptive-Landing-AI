# Warmup Experiment Summary (V2)

This file summarizes the warmup experiment runs in this folder.

## Setup

All runs below used:
- rounds: 5000
- k: 3
- epsilon: 0.05
- reset_params: true
- policy comparison: bandit vs random vs no_change
- warmup values tested: 2, 5, 20
- seeds completed: 1, 7, 42

Summary files analyzed:
- w2_s1/simulate_bandit_summary_seed1_r5000.json
- w2_s7/simulate_bandit_summary_seed7_r5000.json
- w2_s42/simulate_bandit_summary_seed42_r5000.json
- w5_s1/simulate_bandit_summary_seed1_r5000.json
- w5_s7/simulate_bandit_summary_seed7_r5000.json
- w5_s42/simulate_bandit_summary_seed42_r5000.json
- w20_s1/simulate_bandit_summary_seed1_r5000.json
- w20_s7/simulate_bandit_summary_seed7_r5000.json
- w20_s42/simulate_bandit_summary_seed42_r5000.json

## Per-run results

| Warmup | Seed | Bandit CTR | Random CTR | No-change CTR | Bandit - Random | Bandit - No-change |
|---|---:|---:|---:|---:|---:|---:|
| 2  | 1  | 0.1006 | 0.0684 | 0.0348 | 0.0322 | 0.0658 |
| 2  | 7  | 0.0966 | 0.0748 | 0.0338 | 0.0218 | 0.0628 |
| 2  | 42 | 0.0958 | 0.0794 | 0.0326 | 0.0164 | 0.0632 |
| 5  | 1  | 0.1022 | 0.0684 | 0.0348 | 0.0338 | 0.0674 |
| 5  | 7  | 0.0884 | 0.0748 | 0.0338 | 0.0136 | 0.0546 |
| 5  | 42 | 0.0872 | 0.0794 | 0.0326 | 0.0078 | 0.0546 |
| 20 | 1  | 0.1010 | 0.0684 | 0.0348 | 0.0326 | 0.0662 |
| 20 | 7  | 0.0882 | 0.0748 | 0.0338 | 0.0134 | 0.0544 |
| 20 | 42 | 0.0944 | 0.0794 | 0.0326 | 0.0150 | 0.0618 |

## Averages by warmup (across seeds 1, 7, 42)

| Warmup | Runs | Mean Bandit CTR | Bandit CTR std dev | Mean (Bandit - Random) | Mean (Bandit - No-change) |
|---:|---:|---:|---:|---:|---:|
| 2  | 3 | 0.097667 | 0.002100 | 0.023467 | 0.063933 |
| 5  | 3 | 0.092600 | 0.006806 | 0.018400 | 0.058867 |
| 20 | 3 | 0.094533 | 0.005226 | 0.020333 | 0.060800 |

## Effect of warmup

Main findings:
- Warmup=2 has the best average bandit CTR in this set.
- Warmup=2 also has the largest average gain over random and no_change.
- Warmup=5 is the weakest on average.
- Warmup=20 recovers some performance vs warmup=5 but is still below warmup=2.

Differences in average bandit CTR:
- warmup 2 vs 5: +0.005067 for warmup 2
- warmup 2 vs 20: +0.003134 for warmup 2
- warmup 20 vs 5: +0.001933 for warmup 20

Seed behavior notes:
- Seed 1 slightly favors warmup=5.
- Seeds 7 and 42 favor warmup=2.
- This means warmup effect exists, but it is seed-sensitive.

## Practical conclusion

Based on the current 5000-round V2 warmup experiments:
- There is no evidence that larger warmup (5 or 20) improves average performance.
- Warmup=2 is currently the best default among tested values.

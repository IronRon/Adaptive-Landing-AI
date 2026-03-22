# V2 Simulator Results

Generated: 2026-03-22 00:31:13

## Experiment Scope
- Scenarios: conservative, base, optimistic
- Seeds: 1, 2, 3
- Epsilon values: 0.05, 0.10, 0.20
- Total runs: 27
- Rounds per run: 5000

## Scenario Summary (All Epsilons + Seeds)
| Scenario | Runs | Mean Bandit CTR | Std Bandit CTR | Mean Uplift vs Random (%) | Std Uplift vs Random (%) |
|---|---:|---:|---:|---:|---:|
| base | 9 | 0.0997 | 0.0033 | 38.7 | 7.5 |
| conservative | 9 | 0.0757 | 0.0025 | 30.2 | 9 |
| optimistic | 9 | 0.138 | 0.0053 | 48.5 | 2.8 |

## Scenario x Epsilon Summary (Averaged Over Seeds)
| Scenario | Epsilon | Runs | Mean Bandit CTR | Std Bandit CTR | Mean Uplift vs Random (%) | Std Uplift vs Random (%) |
|---|---:|---:|---:|---:|---:|---:|
| base | 0.05 | 3 | 0.1033 | 0.0021 | 43.6 | 4.7 |
| base | 0.1 | 3 | 0.0978 | 0.0024 | 36 | 6.2 |
| base | 0.2 | 3 | 0.098 | 0.0018 | 36.4 | 8.5 |
| conservative | 0.05 | 3 | 0.0763 | 0.0038 | 31 | 4.7 |
| conservative | 0.1 | 3 | 0.0751 | 0.0003 | 29.2 | 9 |
| conservative | 0.2 | 3 | 0.0757 | 0.0017 | 30.5 | 11.8 |
| optimistic | 0.05 | 3 | 0.1387 | 0.0052 | 49.2 | 1.9 |
| optimistic | 0.1 | 3 | 0.1396 | 0.0034 | 50.2 | 0.5 |
| optimistic | 0.2 | 3 | 0.1358 | 0.0061 | 46.1 | 3.1 |

## Best Performing Setting
- Scenario: optimistic
- Epsilon: 0.1
- Mean Bandit CTR: 0.1396
- Mean Uplift vs Random: 50.2%

## Full Run Table
| Scenario | Seed | Epsilon | Bandit CTR | Random CTR | No-change CTR | Uplift vs Random (%) | Uplift vs No-change (%) | Summary File |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| base | 1 | 0.05 | 0.1006 | 0.0684 | 0.0348 | 47.1 | 189.1 | test_output/V2/base/seed1_eps005/simulate_bandit_summary_seed1_r5000.json |
| base | 2 | 0.05 | 0.1036 | 0.0706 | 0.035 | 46.7 | 196 | test_output/V2/base/seed2_eps005/simulate_bandit_summary_seed2_r5000.json |
| base | 3 | 0.05 | 0.1058 | 0.0772 | 0.0346 | 37 | 205.8 | test_output/V2/base/seed3_eps005/simulate_bandit_summary_seed3_r5000.json |
| base | 1 | 0.1 | 0.0946 | 0.0684 | 0.0348 | 38.3 | 171.8 | test_output/V2/base/seed1_eps010/simulate_bandit_summary_seed1_r5000.json |
| base | 2 | 0.1 | 0.1004 | 0.0706 | 0.035 | 42.2 | 186.9 | test_output/V2/base/seed2_eps010/simulate_bandit_summary_seed2_r5000.json |
| base | 3 | 0.1 | 0.0984 | 0.0772 | 0.0346 | 27.5 | 184.4 | test_output/V2/base/seed3_eps010/simulate_bandit_summary_seed3_r5000.json |
| base | 1 | 0.2 | 0.0976 | 0.0684 | 0.0348 | 42.7 | 180.5 | test_output/V2/base/seed1_eps020/simulate_bandit_summary_seed1_r5000.json |
| base | 2 | 0.2 | 0.1004 | 0.0706 | 0.035 | 42.2 | 186.9 | test_output/V2/base/seed2_eps020/simulate_bandit_summary_seed2_r5000.json |
| base | 3 | 0.2 | 0.096 | 0.0772 | 0.0346 | 24.4 | 177.5 | test_output/V2/base/seed3_eps020/simulate_bandit_summary_seed3_r5000.json |
| conservative | 1 | 0.05 | 0.0748 | 0.0544 | 0.0322 | 37.5 | 132.3 | test_output/V2/conservative/seed1_eps005/simulate_bandit_summary_seed1_r5000.json |
| conservative | 2 | 0.05 | 0.0726 | 0.0566 | 0.0322 | 28.3 | 125.5 | test_output/V2/conservative/seed2_eps005/simulate_bandit_summary_seed2_r5000.json |
| conservative | 3 | 0.05 | 0.0816 | 0.0642 | 0.032 | 27.1 | 155 | test_output/V2/conservative/seed3_eps005/simulate_bandit_summary_seed3_r5000.json |
| conservative | 1 | 0.1 | 0.0754 | 0.0544 | 0.0322 | 38.6 | 134.2 | test_output/V2/conservative/seed1_eps010/simulate_bandit_summary_seed1_r5000.json |
| conservative | 2 | 0.1 | 0.0746 | 0.0566 | 0.0322 | 31.8 | 131.7 | test_output/V2/conservative/seed2_eps010/simulate_bandit_summary_seed2_r5000.json |
| conservative | 3 | 0.1 | 0.0752 | 0.0642 | 0.032 | 17.1 | 135 | test_output/V2/conservative/seed3_eps010/simulate_bandit_summary_seed3_r5000.json |
| conservative | 1 | 0.2 | 0.0778 | 0.0544 | 0.0322 | 43 | 141.6 | test_output/V2/conservative/seed1_eps020/simulate_bandit_summary_seed1_r5000.json |
| conservative | 2 | 0.2 | 0.0758 | 0.0566 | 0.0322 | 33.9 | 135.4 | test_output/V2/conservative/seed2_eps020/simulate_bandit_summary_seed2_r5000.json |
| conservative | 3 | 0.2 | 0.0736 | 0.0642 | 0.032 | 14.6 | 130 | test_output/V2/conservative/seed3_eps020/simulate_bandit_summary_seed3_r5000.json |
| optimistic | 1 | 0.05 | 0.1382 | 0.0928 | 0.0372 | 48.9 | 271.5 | test_output/V2/optimistic/seed1_eps005/simulate_bandit_summary_seed1_r5000.json |
| optimistic | 2 | 0.05 | 0.1326 | 0.0902 | 0.039 | 47 | 240 | test_output/V2/optimistic/seed2_eps005/simulate_bandit_summary_seed2_r5000.json |
| optimistic | 3 | 0.05 | 0.1452 | 0.0958 | 0.0378 | 51.6 | 284.1 | test_output/V2/optimistic/seed3_eps005/simulate_bandit_summary_seed3_r5000.json |
| optimistic | 1 | 0.1 | 0.14 | 0.0928 | 0.0372 | 50.9 | 276.3 | test_output/V2/optimistic/seed1_eps010/simulate_bandit_summary_seed1_r5000.json |
| optimistic | 2 | 0.1 | 0.1352 | 0.0902 | 0.039 | 49.9 | 246.7 | test_output/V2/optimistic/seed2_eps010/simulate_bandit_summary_seed2_r5000.json |
| optimistic | 3 | 0.1 | 0.1436 | 0.0958 | 0.0378 | 49.9 | 279.9 | test_output/V2/optimistic/seed3_eps010/simulate_bandit_summary_seed3_r5000.json |
| optimistic | 1 | 0.2 | 0.137 | 0.0928 | 0.0372 | 47.6 | 268.3 | test_output/V2/optimistic/seed1_eps020/simulate_bandit_summary_seed1_r5000.json |
| optimistic | 2 | 0.2 | 0.1278 | 0.0902 | 0.039 | 41.7 | 227.7 | test_output/V2/optimistic/seed2_eps020/simulate_bandit_summary_seed2_r5000.json |
| optimistic | 3 | 0.2 | 0.1426 | 0.0958 | 0.0378 | 48.9 | 277.2 | test_output/V2/optimistic/seed3_eps020/simulate_bandit_summary_seed3_r5000.json |

## Visual Gallery

All plots below are linked with repository-relative paths so they render on GitHub.

### conservative

#### Epsilon 0.05
Mean bandit CTR: 0.0763 | Std: 0.0038 | Mean uplift vs random: 31%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/conservative/seed1_eps005/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/conservative/seed2_eps005/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/conservative/seed3_eps005/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/conservative/seed1_eps005/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/conservative/seed2_eps005/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/conservative/seed3_eps005/simulate_bandit_movingavg_seed3_r5000.png) |

#### Epsilon 0.1
Mean bandit CTR: 0.0751 | Std: 0.0003 | Mean uplift vs random: 29.2%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/conservative/seed1_eps010/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/conservative/seed2_eps010/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/conservative/seed3_eps010/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/conservative/seed1_eps010/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/conservative/seed2_eps010/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/conservative/seed3_eps010/simulate_bandit_movingavg_seed3_r5000.png) |

#### Epsilon 0.2
Mean bandit CTR: 0.0757 | Std: 0.0017 | Mean uplift vs random: 30.5%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/conservative/seed1_eps020/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/conservative/seed2_eps020/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/conservative/seed3_eps020/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/conservative/seed1_eps020/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/conservative/seed2_eps020/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/conservative/seed3_eps020/simulate_bandit_movingavg_seed3_r5000.png) |

### base

#### Epsilon 0.05
Mean bandit CTR: 0.1033 | Std: 0.0021 | Mean uplift vs random: 43.6%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/base/seed1_eps005/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/base/seed2_eps005/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/base/seed3_eps005/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/base/seed1_eps005/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/base/seed2_eps005/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/base/seed3_eps005/simulate_bandit_movingavg_seed3_r5000.png) |

#### Epsilon 0.1
Mean bandit CTR: 0.0978 | Std: 0.0024 | Mean uplift vs random: 36%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/base/seed1_eps010/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/base/seed2_eps010/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/base/seed3_eps010/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/base/seed1_eps010/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/base/seed2_eps010/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/base/seed3_eps010/simulate_bandit_movingavg_seed3_r5000.png) |

#### Epsilon 0.2
Mean bandit CTR: 0.098 | Std: 0.0018 | Mean uplift vs random: 36.4%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/base/seed1_eps020/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/base/seed2_eps020/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/base/seed3_eps020/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/base/seed1_eps020/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/base/seed2_eps020/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/base/seed3_eps020/simulate_bandit_movingavg_seed3_r5000.png) |

### optimistic

#### Epsilon 0.05
Mean bandit CTR: 0.1387 | Std: 0.0052 | Mean uplift vs random: 49.2%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/optimistic/seed1_eps005/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/optimistic/seed2_eps005/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/optimistic/seed3_eps005/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/optimistic/seed1_eps005/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/optimistic/seed2_eps005/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/optimistic/seed3_eps005/simulate_bandit_movingavg_seed3_r5000.png) |

#### Epsilon 0.1
Mean bandit CTR: 0.1396 | Std: 0.0034 | Mean uplift vs random: 50.2%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/optimistic/seed1_eps010/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/optimistic/seed2_eps010/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/optimistic/seed3_eps010/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/optimistic/seed1_eps010/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/optimistic/seed2_eps010/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/optimistic/seed3_eps010/simulate_bandit_movingavg_seed3_r5000.png) |

#### Epsilon 0.2
Mean bandit CTR: 0.1358 | Std: 0.0061 | Mean uplift vs random: 46.1%

Cumulative Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Cumulative Avg Seed 1](/test_output/V2/optimistic/seed1_eps020/simulate_bandit_cumavg_seed1_r5000.png) | Seed 2<br>![Cumulative Avg Seed 2](/test_output/V2/optimistic/seed2_eps020/simulate_bandit_cumavg_seed2_r5000.png) | Seed 3<br>![Cumulative Avg Seed 3](/test_output/V2/optimistic/seed3_eps020/simulate_bandit_cumavg_seed3_r5000.png) |

Moving Average Reward

| Seed 1 | Seed 2 | Seed 3 |
|---|---|---|
| Seed 1<br>![Moving Avg Seed 1](/test_output/V2/optimistic/seed1_eps020/simulate_bandit_movingavg_seed1_r5000.png) | Seed 2<br>![Moving Avg Seed 2](/test_output/V2/optimistic/seed2_eps020/simulate_bandit_movingavg_seed2_r5000.png) | Seed 3<br>![Moving Avg Seed 3](/test_output/V2/optimistic/seed3_eps020/simulate_bandit_movingavg_seed3_r5000.png) |


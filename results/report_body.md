## 1. Comprehensive comparison
Paired seeds: 30 at 50 agents, 30 at 100 agents, 30 at 200 agents. Mean ± SD. Same maps, tasks and failures for every algorithm within a seed. Safety violations across all 540 runs: **0**.

| Scenario | Metric | Traditional A* | Replanning A* (D*-style) | Multi-agent A* (prioritized, Cooperative A*) | WHCA* (Silver 2005) | PIBT (Okumura 2022) | EPP-ACE | EPP-ACE minus Multi-agent A* (Holm p) | EPP-ACE minus PIBT (Holm p) |
|---|---|---|---|---|---|---|---|---|---|
| Low (50 agents) | Task completion on time (%) | 45.1 ± 11.4 | 45.6 ± 11.3 | 93.9 ± 1.9 | 93.7 ± 2.2 | 92.8 ± 2.0 | 93.3 ± 2.5 | -0.6 (p=0.526) | +0.5 (p=0.786) |
|  | Path efficiency | 1.000 ± 0.001 | 0.998 ± 0.002 | 0.996 ± 0.001 | 0.996 ± 0.002 | 0.984 ± 0.006 | 0.983 ± 0.003 | -0.013 (p<0.001) | -0.001 (p=0.786) |
|  | Adaptation time (steps) | 42.7 ± 17.7 | 7.6 ± 11.7 | 3.6 ± 0.2 | 3.1 ± 0.1 | n/a | 3.0 ± 0.2 | -0.6 (p<0.001) | n/a |
|  | Throughput (tasks/step) | 0.146 ± 0.035 | 0.147 ± 0.036 | 0.442 ± 0.044 | 0.443 ± 0.042 | 0.438 ± 0.041 | 0.440 ± 0.044 | -0.002 (p=1.000) | +0.002 (p=0.786) |
|  | Mean congestion (evaluator density) | 0.256 ± 0.024 | 0.255 ± 0.025 | 0.129 ± 0.003 | 0.130 ± 0.002 | 0.131 ± 0.003 | 0.124 ± 0.002 | -0.005 (p<0.001) | -0.008 (p<0.001) |
|  | Planner conflicts left to the arbiter | 8687 ± 966 | 8662 ± 951 | 0 ± 1 | 0 ± 1 | 0 ± 0 | 0 ± 0 | -0 (p=1.000) | +0 (p=0.786) |
| Medium-low (100 agents) | Task completion on time (%) | 25.1 ± 4.9 | 25.6 ± 5.2 | 93.1 ± 1.3 | 93.1 ± 1.5 | 92.3 ± 1.6 | 92.7 ± 1.4 | -0.4 (p=0.321) | +0.4 (p=1.000) |
|  | Path efficiency | 0.999 ± 0.001 | 0.997 ± 0.002 | 0.994 ± 0.002 | 0.992 ± 0.002 | 0.971 ± 0.005 | 0.971 ± 0.003 | -0.023 (p<0.001) | -0.000 (p=1.000) |
|  | Adaptation time (steps) | 64.8 ± 17.7 | 3.1 ± 0.3 | 3.5 ± 0.1 | 3.2 ± 0.1 | n/a | 3.0 ± 0.1 | -0.5 (p<0.001) | n/a |
|  | Throughput (tasks/step) | 0.147 ± 0.027 | 0.149 ± 0.028 | 0.872 ± 0.060 | 0.875 ± 0.059 | 0.865 ± 0.059 | 0.865 ± 0.059 | -0.007 (p=0.074) | +0.000 (p=1.000) |
|  | Mean congestion (evaluator density) | 0.302 ± 0.020 | 0.304 ± 0.020 | 0.145 ± 0.002 | 0.146 ± 0.002 | 0.150 ± 0.003 | 0.137 ± 0.002 | -0.008 (p<0.001) | -0.013 (p<0.001) |
|  | Planner conflicts left to the arbiter | 20317 ± 1072 | 20266 ± 1094 | 1 ± 1 | 2 ± 2 | 0 ± 0 | 1 ± 1 | -1 (p=0.076) | +1 (p=0.015) |
| Medium (200 agents) | Task completion on time (%) | 13.7 ± 2.5 | 14.0 ± 2.6 | 92.7 ± 1.3 | 92.3 ± 1.4 | 91.1 ± 1.5 | 92.0 ± 1.5 | -0.7 (p=0.028) | +0.9 (p<0.001) |
|  | Path efficiency | 0.999 ± 0.001 | 0.998 ± 0.003 | 0.989 ± 0.002 | 0.986 ± 0.002 | 0.947 ± 0.006 | 0.958 ± 0.004 | -0.031 (p<0.001) | +0.012 (p<0.001) |
|  | Adaptation time (steps) | 84.4 ± 17.2 | 31.1 ± 43.2 | 3.6 ± 0.1 | 3.2 ± 0.1 | n/a | 3.0 ± 0.1 | -0.6 (p<0.001) | n/a |
|  | Throughput (tasks/step) | 0.152 ± 0.028 | 0.155 ± 0.028 | 1.709 ± 0.072 | 1.702 ± 0.068 | 1.683 ± 0.064 | 1.695 ± 0.072 | -0.014 (p=0.028) | +0.012 (p=0.007) |
|  | Mean congestion (evaluator density) | 0.360 ± 0.015 | 0.361 ± 0.018 | 0.178 ± 0.002 | 0.179 ± 0.002 | 0.188 ± 0.003 | 0.164 ± 0.002 | -0.014 (p<0.001) | -0.024 (p<0.001) |
|  | Planner conflicts left to the arbiter | 43883 ± 1258 | 43806 ± 1254 | 26 ± 23 | 30 ± 29 | 0 ± 0 | 44 ± 80 | +18 (p=0.930) | +44 (p<0.001) |

### Paired effect sizes (EPP-ACE)
| Scenario | Comparison | Metric | Mean paired diff | 95% bootstrap CI | Holm p | Cliff's δ |
|---|---|---|---|---|---|---|
| Low (50 agents) | EPP-ACE vs Traditional A* | tcr_on_time | +48.171 | [+44.315, +51.838] | <0.001 | +1.00 |
| Low (50 agents) | EPP-ACE vs Traditional A* | mean_density | -0.132 | [-0.140, -0.123] | <0.001 | -1.00 |
| Low (50 agents) | EPP-ACE vs Multi-agent A* (prioritized, Cooperative A*) | tcr_on_time | -0.649 | [-1.268, -0.025] | 0.526 | -0.20 |
| Low (50 agents) | EPP-ACE vs Multi-agent A* (prioritized, Cooperative A*) | mean_density | -0.005 | [-0.006, -0.005] | <0.001 | -0.90 |
| Low (50 agents) | EPP-ACE vs PIBT (Okumura 2022) | tcr_on_time | +0.516 | [-0.328, +1.379] | 0.786 | +0.07 |
| Low (50 agents) | EPP-ACE vs PIBT (Okumura 2022) | mean_density | -0.008 | [-0.008, -0.007] | <0.001 | -0.97 |
| Medium-low (100 agents) | EPP-ACE vs Traditional A* | tcr_on_time | +67.635 | [+65.783, +69.428] | <0.001 | +1.00 |
| Medium-low (100 agents) | EPP-ACE vs Traditional A* | mean_density | -0.165 | [-0.172, -0.159] | <0.001 | -1.00 |
| Medium-low (100 agents) | EPP-ACE vs Multi-agent A* (prioritized, Cooperative A*) | tcr_on_time | -0.426 | [-0.897, +0.078] | 0.321 | -0.15 |
| Medium-low (100 agents) | EPP-ACE vs Multi-agent A* (prioritized, Cooperative A*) | mean_density | -0.008 | [-0.009, -0.008] | <0.001 | -1.00 |
| Medium-low (100 agents) | EPP-ACE vs PIBT (Okumura 2022) | tcr_on_time | +0.422 | [-0.143, +1.024] | 1.000 | +0.16 |
| Medium-low (100 agents) | EPP-ACE vs PIBT (Okumura 2022) | mean_density | -0.013 | [-0.014, -0.012] | <0.001 | -1.00 |
| Medium (200 agents) | EPP-ACE vs Traditional A* | tcr_on_time | +78.343 | [+77.303, +79.441] | <0.001 | +1.00 |
| Medium (200 agents) | EPP-ACE vs Traditional A* | mean_density | -0.196 | [-0.201, -0.190] | <0.001 | -1.00 |
| Medium (200 agents) | EPP-ACE vs Multi-agent A* (prioritized, Cooperative A*) | tcr_on_time | -0.714 | [-1.145, -0.305] | 0.028 | -0.27 |
| Medium (200 agents) | EPP-ACE vs Multi-agent A* (prioritized, Cooperative A*) | mean_density | -0.014 | [-0.015, -0.013] | <0.001 | -1.00 |
| Medium (200 agents) | EPP-ACE vs PIBT (Okumura 2022) | tcr_on_time | +0.898 | [+0.440, +1.352] | <0.001 | +0.32 |
| Medium (200 agents) | EPP-ACE vs PIBT (Okumura 2022) | mean_density | -0.024 | [-0.025, -0.023] | <0.001 | -1.00 |

## 2. Congestion reduction  (1 − density / density of Traditional A*)
Caution: gridlocked agents stand still, so a failed baseline can show *lower* or higher density depending on where it jams. Read with Table 1.

| Scenario | Algorithm | A* density | Density | Reduction vs A* |
|---|---|---|---|---|
| Low (50 agents) | Replanning A* (D*-style) | 0.256 | 0.255 | +0.1% |
| Low (50 agents) | Multi-agent A* (prioritized, Cooperative A*) | 0.256 | 0.129 | +49.5% |
| Low (50 agents) | WHCA* (Silver 2005) | 0.256 | 0.130 | +49.3% |
| Low (50 agents) | PIBT (Okumura 2022) | 0.256 | 0.131 | +48.6% |
| Low (50 agents) | EPP-ACE | 0.256 | 0.124 | +51.6% |
| Medium-low (100 agents) | Replanning A* (D*-style) | 0.302 | 0.304 | -0.6% |
| Medium-low (100 agents) | Multi-agent A* (prioritized, Cooperative A*) | 0.302 | 0.145 | +51.9% |
| Medium-low (100 agents) | WHCA* (Silver 2005) | 0.302 | 0.146 | +51.6% |
| Medium-low (100 agents) | PIBT (Okumura 2022) | 0.302 | 0.150 | +50.3% |
| Medium-low (100 agents) | EPP-ACE | 0.302 | 0.137 | +54.7% |
| Medium (200 agents) | Replanning A* (D*-style) | 0.360 | 0.361 | -0.5% |
| Medium (200 agents) | Multi-agent A* (prioritized, Cooperative A*) | 0.360 | 0.178 | +50.5% |
| Medium (200 agents) | WHCA* (Silver 2005) | 0.360 | 0.179 | +50.3% |
| Medium (200 agents) | PIBT (Okumura 2022) | 0.360 | 0.188 | +47.7% |
| Medium (200 agents) | EPP-ACE | 0.360 | 0.164 | +54.4% |

## 3. Priority-based task completion (Medium (200 agents))
| Priority | Traditional A* | Replanning A* (D*-style) | Multi-agent A* (prioritized, Cooperative A*) | WHCA* (Silver 2005) | PIBT (Okumura 2022) | EPP-ACE | EPP-ACE − MA-A* (raw p) |
|---|---|---|---|---|---|---|---|
| Critical | 13.7 ± 4.4 | 14.2 ± 3.7 | 93.1 ± 2.2 | 92.3 ± 2.3 | 91.8 ± 2.5 | 92.7 ± 1.7 | -0.4 (p=0.213) |
| High | 13.3 ± 3.7 | 13.7 ± 3.1 | 92.8 ± 1.7 | 92.6 ± 1.9 | 91.1 ± 1.9 | 92.5 ± 1.9 | -0.3 (p=0.670) |
| Medium | 14.1 ± 3.5 | 14.3 ± 4.2 | 92.5 ± 1.8 | 91.8 ± 2.4 | 90.9 ± 3.0 | 91.2 ± 2.1 | -1.3 (p=0.003) |
| Low | 13.6 ± 8.0 | 14.1 ± 7.3 | 92.5 ± 4.8 | 92.5 ± 4.5 | 90.6 ± 3.9 | 91.1 ± 5.3 | -1.4 (p=0.119) |

## 4. Robustness (50 agents)
| Disturbance | Traditional A* | Multi-agent A* | EPP-ACE |
|---|---|---|---|
| none | 45.1 ± 11.4 | 93.9 ± 1.9 | 93.3 ± 2.5 |
| 20% communication loss | 45.1 ± 11.4 | 93.9 ± 1.9 | 93.3 ± 2.5 |
| 10% agent failure | 46.7 ± 11.0 | 92.8 ± 2.2 | 92.9 ± 2.1 |
| 10% agent failure, 20% communication loss | 46.7 ± 11.0 | 92.8 ± 2.2 | 92.8 ± 2.0 |

## 5. Ablation (Medium (200 agents), 30 seeds)
| Variant | On-time % | Density | Plan ms | On-time vs Multi-agent A* (Holm p) |
|---|---|---|---|---|
| Multi-agent A* (prioritized, Cooperative A*) | 92.7 ± 1.3 | 0.178 ± 0.002 | 1.40 ± 0.15 | baseline |
| A2 congestion only | 24.9 ± 4.0 | 0.333 ± 0.015 | 22.24 ± 8.81 | -67.87 (p<0.001) |
| A3 + priority | 14.2 ± 2.9 | 0.359 ± 0.015 | 0.57 ± 0.06 | -78.50 (p<0.001) |
| A4 + adaptation | 14.0 ± 2.6 | 0.361 ± 0.018 | 0.56 ± 0.05 | -78.74 (p<0.001) |
| A5 full, no coordination | 27.4 ± 4.8 | 0.318 ± 0.014 | 32.44 ± 6.39 | -65.36 (p<0.001) |
| EPP-ACE | 92.0 ± 1.5 | 0.164 ± 0.002 | 35.87 ± 7.82 | -0.71 (p=0.009) |
| EPP-ACE + reservation predictor | 92.4 ± 1.5 | 0.162 ± 0.002 | 2.94 ± 0.22 | -0.35 (p=0.158) |
| EPP-ACE (manuscript CDS score) | 91.8 ± 1.5 | 0.170 ± 0.002 | 41.28 ± 6.73 | -0.95 (p<0.001) |

## 6. Control: same grid, scattered 15% walls instead of rooms
| Scenario | Traditional A* | Replanning A* (D*-style) | Multi-agent A* (prioritized, Cooperative A*) | EPP-ACE |
|---|---|---|---|---|
| Low (50 agents) | 24.4 ± 5.8 | 24.4 ± 5.2 | 94.3 ± 1.4 | 93.7 ± 1.2 |
| Medium (200 agents) | 43.8 ± 5.6 | 43.5 ± 5.4 | 94.3 ± 1.8 | 92.9 ± 1.8 |

## 7. Computational cost
| Scenario | Traditional A* plan ms | Replanning A* (D*-style) plan ms | Multi-agent A* (prioritized, Cooperative A*) plan ms | WHCA* (Silver 2005) plan ms | PIBT (Okumura 2022) plan ms | EPP-ACE plan ms | MA-A* run s | EPP-ACE run s |
|---|---|---|---|---|---|---|---|---|
| Low (50 agents) | 0.57 | 0.60 | 1.23 | 0.07 | 0.01 | 4.42 | 1.0 | 2.6 |
| Medium-low (100 agents) | 0.50 | 0.50 | 1.22 | 0.07 | 0.01 | 8.44 | 1.9 | 8.9 |
| Medium (200 agents) | 0.70 | 0.61 | 1.39 | 0.06 | 0.01 | 39.09 | 3.9 | 102.1 |

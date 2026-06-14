# Example complete workflow

## 1. Analyze

```bash
python wdl_chess_analyzer_v3_6_1_ccp_v2_root_branch_diagnostics_fix.py 1971-09_fischer_petrosian.pgn ^
--stockfish stockfish-18-windows-x86-64-bmi2.exe ^
--main-nodes 10000000 ^
--difficulty-nodes 500000 ^
--ccp-v2 ^
--ccp-v2-two-stage ^
--ccp-v2-nodes 10000 ^
--ccp-v2-probe-nodes 3000 ^
--ccp-v2-depth 12 ^
--ccp-v2-probe-depth 8 ^
--ccp-v2-max-expanded-positions 1000 ^
--ccp-v2-probe-max-expanded-positions 300 ^
--ccp-v2-max-engine-calls-per-root 1500 ^
--ccp-v2-probe-max-engine-calls-per-root 300 ^
--ccp-v2-confirm-candidates 16 ^
--ccp-v2-confirm-score-mode log ^
--ccp-v2-quiet-candidates 12 ^
--ccp-v2-vision-depth 3 ^
--ccp-v2-vision-branch 6 ^
--ccp-v2-vision-decay 0.65 ^
--ccp-v2-vision-mode root ^
--ccp-v2-vision-candidates 12 ^
--threads 6 ^
--hash 2048 ^
--difficulty-mode all-legal ^
--outdir 2026-06-14_analysis_2_Fischer-Petrosian_1971
```

## 2. Make match report

```bash
python make_wdl_report_v4_7_dpq_pressure_yield.py ^
  --per-game 2026-06-13_analysis_1_Kasparov-Karpov_1985\per_game_wdl_metrics.csv ^
  --per-move 2026-06-13_analysis_1_Kasparov-Karpov_1985\per_move_wdl.csv ^
  --metadata 2026-06-13_analysis_1_Kasparov-Karpov_1985\analysis_metadata.csv ^
  --root-branches 2026-06-13_analysis_1_Kasparov-Karpov_1985\ccp_v2_root_branch_diagnostics.csv ^
  --outdir 2026-06-13_report_1_Kasparov-Karpov_1985 ^
  --match-name "Kasparov-Karpov 1985 — v3.6.1 1500/16" ^
  --top-n 30
```

## 3. Prepare combiner input

The input directory should contain prefixed files such as:

```text
01_fischer-taimanov_all_metrics_3source.csv
01_fischer-taimanov_game_summary_readable.csv
01_fischer-taimanov_metric_ratios.csv
01_fischer-taimanov_ccp_v2_root_branch_summary.csv
01_fischer-taimanov_ccp_v2_root_branch_ply_summary.csv
01_fischer-taimanov_ccp_v2_root_branch_top_moves.csv
01_fischer-taimanov_ccp_v2_root_branch_payoff_moves.csv
01_fischer-taimanov_ccp_v2_root_branch_workload_rows.csv
```

and

```text
02_fischer-larsen_all_metrics_3source.csv
02_fischer-larsen_game_summary_readable.csv
02_fischer-larsen_metric_ratios.csv
02_fischer-larsen_ccp_v2_root_branch_summary.csv
02_fischer-larsen_ccp_v2_root_branch_ply_summary.csv
02_fischer-larsen_ccp_v2_root_branch_top_moves.csv
02_fischer-larsen_ccp_v2_root_branch_payoff_moves.csv
02_fischer-larsen_ccp_v2_root_branch_workload_rows.csv
```

and so on.

## 4. Combine matches

```bash
python combine_match_reports_v4_7_dpq_pressure_yield.py ^
  --input-dir "run_input" ^
  --main-player "Robert James Fischer" ^
  --run-name "Fischer 1971-1972 World-Championship Run" ^
  --outdir "fischer_1971_1972_combined_report"
```

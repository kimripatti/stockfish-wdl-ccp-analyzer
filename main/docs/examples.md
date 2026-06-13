# Example complete workflow

## 1. Analyze

```bash
python wdl_chess_analyzer_v3_6_1_ccp_v2_root_branch_diagnostics_fix.py "fischer_taimanov_1971.pgn" ^
  --stockfish "C:\Engines\Stockfish\stockfish.exe" ^
  --threads 6 ^
  --hash 2048 ^
  --main-nodes 10000000 ^
  --difficulty-nodes 500000 ^
  --difficulty-mode all-legal ^
  --difficulty-tau 0.03 ^
  --outdir "01_fischer-taimanov_output"
```

## 2. Make match report

```bash
python make_wdl_report_v4_7_dpq_pressure_yield.py ^
  --per-game "01_fischer-taimanov_output/per_game_wdl_metrics.csv" ^
  --per-move "01_fischer-taimanov_output/per_move_wdl.csv" ^
  --summary "01_fischer-taimanov_output/summary_wdl_metrics.csv" ^
  --pgn "fischer_taimanov_1971.pgn" ^
  --outdir "01_fischer-taimanov_report" ^
  --match-name "Fischer–Taimanov 1971" ^
  --top-n 30
```

## 3. Prepare combiner input

Copy or rename:

```text
01_fischer-taimanov_report/all_metrics_3source.csv
```

to:

```text
run_input/01_fischer-taimanov_all_metrics_3source.csv
```

Copy or rename:

```text
01_fischer-taimanov_report/metric_ratios.csv
```

to:

```text
run_input/01_fischer-taimanov_metric_ratios.csv
```

Copy or rename:

```text
01_fischer-taimanov_report/game_summary_readable.csv
```

to:

```text
run_input/01_fischer-taimanov_game_summary_readable.csv
```

Repeat for every match.

## 4. Combine matches

```bash
python combine_match_reports_v4_7_dpq_pressure_yield.py ^
  --input-dir "run_input" ^
  --main-player "Robert James Fischer" ^
  --run-name "Fischer 1971-1972 World-Championship Run" ^
  --outdir "fischer_1971_1972_combined_report"
```

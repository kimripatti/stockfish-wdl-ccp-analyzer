# stockfish-wdl-ccp-analyzer
Stockfish WDL-based chess game analyzer with CCP search-difficulty metrics, root-branch diagnostics, DPQ pressure/yield metrics, and match-report generation.

# Stockfish WDL CCP Analyzer

Stockfish WDL-based chess game analyzer with CCP search-difficulty metrics, root-branch diagnostics, DPQ pressure/yield metrics, and match-report generation.

This repository contains a three-program Python pipeline for analyzing chess games with Stockfish WDL expected-score data.

The main idea is to measure chess games not only by centipawn-style error, but by **WDL expected-score movement**:

```text
ES = W + 0.5D
```

where:

```text
W = Stockfish-estimated win probability
D = Stockfish-estimated draw probability
L = Stockfish-estimated loss probability
W + D + L = 1
ES = expected score
```

The analyzer then calculates WDL move accuracy, expected-score loss, volatility, performance quality, CCP search difficulty, root-branch diagnostics, DPQ pressure/yield metrics, and readable match/run reports.

---

## Repository contents

The repository is built around three main programs:

```text
wdl_chess_analyzer_v3_6_1_ccp_v2_root_branch_diagnostics_fix.py
make_wdl_report_v4_7_dpq_pressure_yield.py
combine_match_reports_v4_7_dpq_pressure_yield.py
```

### 1. `wdl_chess_analyzer_v3_6_1_ccp_v2_root_branch_diagnostics_fix.py`

Reads a PGN file, calls Stockfish, enables WDL output, and produces move-by-move and game-by-game CSV files.

It calculates:

* WDL expected score
* WDL move accuracy
* expected-score loss
* WDL volatility
* Performance Quality
* Difficulty Pressure Quality / DPQ-related data
* CCP search-difficulty metrics
* root-branch diagnostics
* metadata about the run

### 2. `make_wdl_report_v4_7_dpq_pressure_yield.py`

Reads one analyzer output folder and produces readable match-level reports.

It creates files such as:

```text
all_metrics_3source.csv
player_summary.csv
game_summary_readable.csv
critical_moves.csv
volatility_swings.csv
article_report.md
```

In the newer DPQ/pressure-yield version, it also summarizes pressure/difficulty-related quantities when the relevant columns are present in `per_move_wdl.csv`.

### 3. `combine_match_reports_v4_7_dpq_pressure_yield.py`

Reads several match-level reports and combines them into a run-level report.

For example, it can combine four Fischer 1971–1972 match reports into one complete Fischer World-Championship-run report.

It creates files such as:

```text
run_all_metrics.csv
run_metric_ratios.csv
run_summary_by_match.csv
run_summary_overall.csv
run_game_summary.csv
run_game_metric_ratios.csv
run_article_report.md
```

---

## Requirements

Recommended:

```text
Python 3.10+
Stockfish 18 or newer
python-chess
pandas
```

Install Python dependencies:

```bash
pip install python-chess pandas
```

You also need a Stockfish executable. The analyzer calls Stockfish directly through UCI and tries to enable:

```text
UCI_ShowWDL = true
```

This is required because the project is based on Stockfish WDL output, not only centipawn output.

---

## Basic workflow

The normal workflow is:

```text
PGN file
  ↓
wdl_chess_analyzer...
  ↓
per_game_wdl_metrics.csv + per_move_wdl.csv + summary_wdl_metrics.csv
  ↓
make_wdl_report...
  ↓
match-level readable report files
  ↓
combine_match_reports...
  ↓
run-level combined report files
```

---

# Step 1: Analyze a PGN file

Example:

```bash
python wdl_chess_analyzer_v3_6_1_ccp_v2_root_branch_diagnostics_fix.py "my_match.pgn" ^
  --stockfish "C:\Engines\stockfish\stockfish-windows-x86-64-avx2.exe" ^
  --threads 7 ^
  --hash 2048 ^
  --main-nodes 1000000 ^
  --difficulty-nodes 50000 ^
  --outdir "wdl_output_my_match"
```

On Linux/macOS:

```bash
python wdl_chess_analyzer_v3_6_1_ccp_v2_root_branch_diagnostics_fix.py "my_match.pgn" \
  --stockfish "/path/to/stockfish" \
  --threads 7 \
  --hash 2048 \
  --main-nodes 1000000 \
  --difficulty-nodes 50000 \
  --outdir "wdl_output_my_match"
```

---

## Analyzer command-line options

Run this to confirm the exact options in your current version:

```bash
python wdl_chess_analyzer_v3_6_1_ccp_v2_root_branch_diagnostics_fix.py --help
```

The known inherited options are:

| Option                     | Required? |                    Default | Meaning                                                                                       |
| -------------------------- | --------: | -------------------------: | --------------------------------------------------------------------------------------------- |
| `pgn`                      |       yes |                          — | Input PGN file. Positional argument.                                                          |
| `--stockfish`              |       yes |                          — | Path to the Stockfish executable.                                                             |
| `--depth`                  |        no |                       `16` | Default search depth, used when more specific limits are not given.                           |
| `--movetime`               |        no |                     `None` | Default time per engine call, in seconds.                                                     |
| `--nodes`                  |        no |                     `None` | Default node limit per engine call.                                                           |
| `--main-depth`             |        no |                     `None` | Search depth for normal game-flow WDL analysis.                                               |
| `--main-movetime`          |        no |                     `None` | Time per move for normal game-flow WDL analysis.                                              |
| `--main-nodes`             |        no |                     `None` | Node limit for normal game-flow WDL analysis.                                                 |
| `--difficulty-depth`       |        no |                     `None` | Search depth for difficulty / all-legal / CCP-style analysis.                                 |
| `--difficulty-movetime`    |        no |                     `None` | Time limit for difficulty analysis.                                                           |
| `--difficulty-nodes`       |        no |                     `None` | Node limit for difficulty analysis.                                                           |
| `--hybrid-depth`           |        no |                     `None` | Optional deeper depth for hybrid top-K re-analysis.                                           |
| `--hybrid-movetime`        |        no |                     `None` | Optional deeper movetime for hybrid top-K re-analysis.                                        |
| `--hybrid-nodes`           |        no |                     `None` | Optional deeper node limit for hybrid top-K re-analysis.                                      |
| `--threads`                |        no |                        `1` | Number of Stockfish CPU threads.                                                              |
| `--hash`                   |        no |                       `16` | Stockfish hash size in MB.                                                                    |
| `--weighting`              |        no |                      `ply` | Expected-score weighting method for Conversion. Choices: `ply`, `uniform`.                    |
| `--outdir`                 |        no | `wdl_output_v3_difficulty` | Output directory.                                                                             |
| `--no-difficulty`          |        no |                        off | Disables difficulty analysis and runs closer to the older WDL analyzer.                       |
| `--difficulty-mode`        |        no |                `all-legal` | Difficulty method. Choices: `all-legal`, `multipv`, `hybrid`.                                 |
| `--difficulty-multipv`     |        no |                       `10` | Top-K moves for `--difficulty-mode multipv`.                                                  |
| `--difficulty-hybrid-topk` |        no |                        `5` | Top-K shallow legal moves re-analyzed in hybrid mode.                                         |
| `--difficulty-tau`         |        no |                     `0.03` | Softmax sensitivity for legal-move losses. Smaller values make near-best separation stricter. |

The newest v3.6.1 file may contain additional CCP v2 or root-branch diagnostic options. Always check:

```bash
python wdl_chess_analyzer_v3_6_1_ccp_v2_root_branch_diagnostics_fix.py --help
```

before publishing final documentation.

---

## Recommended analyzer settings

### Recommended serious-analysis setting

Good balance between speed and quality:

```bash
--main-nodes 1000000 --difficulty-nodes 50000 --threads 6 --hash 2048
```

This setting is useful when analyzing multi-game matches and when you want the results to be reproducible enough for comparison.

### Faster test setting

Use this to check that the pipeline works:

```bash
--main-nodes 100000 --difficulty-nodes 10000 --threads 2 --hash 256
```

This is useful for testing file paths, PGN parsing, and report generation before running a serious analysis.

### Higher-quality setting

Use this if you want more robust results and do not mind waiting longer:

```bash
--main-nodes 2000000 --difficulty-nodes 100000 --threads 6 --hash 2048
```

or:

```bash
--main-nodes 10000000 --difficulty-nodes 500000 --threads 6 --hash 4096
```

### Depth-based alternative

If you prefer depth limits instead of node limits:

```bash
--main-depth 16 --difficulty-depth 12
```

or:

```bash
--main-depth 18 --difficulty-depth 14
```

Node limits are often better for reproducibility across positions, while time limits are often more convenient for casual use.

### Time-based alternative

Example:

```bash
--main-movetime 1.0 --difficulty-movetime 0.1
```

This means roughly 1 second per normal game-flow analysis call and 0.1 seconds per difficulty-analysis call.

Time-based settings are less reproducible across machines, because faster hardware will search more nodes in the same time.

---

## Difficulty-mode advice

### `--difficulty-mode all-legal`

This is the most complete mode.

It evaluates every legal move from the position and estimates how hard the move choice was.

Use this when quality matters more than speed.

```bash
--difficulty-mode all-legal
```

### `--difficulty-mode multipv`

This is faster.

It asks Stockfish for only the top-K candidate moves.

```bash
--difficulty-mode multipv --difficulty-multipv 10
```

Use this when you want a quick approximation of candidate-move difficulty.

Main limitation: it does not fully measure the complete legal-move field.

### `--difficulty-mode hybrid`

This begins with a broader pass and then re-analyzes the best top-K moves more deeply.

Example:

```bash
--difficulty-mode hybrid ^
  --difficulty-nodes 50000 ^
  --hybrid-nodes 250000 ^
  --difficulty-hybrid-topk 5
```

Use this when you want a compromise between all-legal breadth and deeper candidate-move checking.

---

## Recommended `--difficulty-tau`

Default:

```bash
--difficulty-tau 0.03
```

Interpretation:

* Lower `tau` = stricter separation between best and near-best moves.
* Higher `tau` = more forgiving; more moves count as “effectively good.”

Recommended:

```bash
--difficulty-tau 0.03
```

This is a good default for WDL expected-score losses.

Try:

```bash
--difficulty-tau 0.02
```

if you want a stricter model.

Try:

```bash
--difficulty-tau 0.05
```

if you want a smoother, more forgiving model.

For published comparisons, use the same `tau` in every run.

---

## Analyzer output files

The analyzer normally produces:

```text
per_game_wdl_metrics.csv
per_move_wdl.csv
summary_wdl_metrics.csv
analysis_metadata.csv
analysis_metadata_wide.csv
```

### `per_move_wdl.csv`

This is the most detailed file.

It contains one row per played move.

Important columns include:

```text
game_id
ply
move_uci
mover
player_label
es_before_white
es_after_white
es_best_before_mover
es_after_played_mover
wdl_es_loss
wdl_move_accuracy
wdl_volatility_swing
```

If difficulty and CCP/root-branch diagnostics are enabled, this file also contains the difficulty columns.

Typical difficulty/diagnostic ideas include:

```text
legal_move_count
best_legal_es
worst_legal_es
mean_legal_es
rms_legal_loss
narrowness
effective_good_moves
ccp_search_difficulty
ccp_search_difficulty_pure
root_branch diagnostics
```

Exact column names may differ by version.

### `per_game_wdl_metrics.csv`

This contains one row per game.

It summarizes both players separately and together.

Important columns include:

```text
game_id
white
black
player_A
player_B
result
plies
accuracy_A_wdl
accuracy_B_wdl
game_accuracy_wdl
mutual_accuracy_wdl
pq_A_wdl
pq_B_wdl
dominance_A_wdl
dominance_B_wdl
volatility_A_wdl
volatility_B_wdl
mean_es_loss_A
mean_es_loss_B
rms_es_loss_A
rms_es_loss_B
error_concentration_A
error_concentration_B
score_A
score_B
expected_score_A
expected_score_B
conversion_A
conversion_B
hard_rap_A
hard_rap_B
soft_rap_A
soft_rap_B
```

If difficulty analysis is enabled, game-level difficulty averages are added too.

### `summary_wdl_metrics.csv`

This gives summary statistics for numeric columns across the analyzed games.

### `analysis_metadata.csv`

Long key-value metadata file.

Useful for recording:

```text
command
pgn_path
stockfish_path
threads
hash_mb
main_nodes
difficulty_nodes
difficulty_mode
difficulty_tau
games_analyzed
plies_analyzed
elapsed_minutes
engine_calls
cache_hits
```

### `analysis_metadata_wide.csv`

A wide one-row version of metadata.

This is often easier to inspect in spreadsheet software.

---

# Step 2: Create a match report

After running the analyzer, run:

```bash
python make_wdl_report_v4_7_dpq_pressure_yield.py ^
  --per-game "wdl_output_my_match/per_game_wdl_metrics.csv" ^
  --per-move "wdl_output_my_match/per_move_wdl.csv" ^
  --summary "wdl_output_my_match/summary_wdl_metrics.csv" ^
  --pgn "my_match.pgn" ^
  --outdir "wdl_report_my_match" ^
  --match-name "My Match Name" ^
  --top-n 30
```

The `--pgn` argument is optional, but recommended, because it allows the report to add SAN notation to move tables.

---

## Report-generator command-line options

Run:

```bash
python make_wdl_report_v4_7_dpq_pressure_yield.py --help
```

Known inherited options:

| Option         | Required? |            Default | Meaning                                                                         |
| -------------- | --------: | -----------------: | ------------------------------------------------------------------------------- |
| `--per-game`   |       yes |                  — | Path to `per_game_wdl_metrics.csv`.                                             |
| `--per-move`   |       yes |                  — | Path to `per_move_wdl.csv`.                                                     |
| `--summary`    |        no |             `None` | Optional path to `summary_wdl_metrics.csv`.                                     |
| `--pgn`        |        no |             `None` | Optional PGN path for adding SAN notation.                                      |
| `--outdir`     |        no |  version-dependent | Output directory for the match report.                                          |
| `--match-name` |        no | `WDL Match Report` | Name shown in the markdown report.                                              |
| `--top-n`      |        no |       usually `30` | Number of critical moves / volatility swings / difficulty positions to include. |

The v4.7 DPQ pressure-yield version may add or auto-generate additional DPQ/pressure-yield outputs when the relevant columns are present.

---

## Match-report output files

The report generator normally creates:

```text
all_metrics_3source.csv
player_summary.csv
game_summary_readable.csv
critical_moves.csv
volatility_swings.csv
article_report.md
```

In the DPQ/pressure-yield version, it may also create additional files such as:

```text
hardest_positions.csv
difficulty_critical_moves.csv
ccp_hardest_positions.csv
root_branch_diagnostics.csv
pressure_yield tables
```

Exact names depend on the current script version.

---

## Most important match-report file

The central match-level file is:

```text
all_metrics_3source.csv
```

It reports metrics for:

```text
Player A
Player B
Both players together
```

Important columns:

```text
metric_key
metric
definition
aggregation
player_A_name
player_A_value
player_A_sd
player_B_name
player_B_value
player_B_sd
both_players_value
both_players_sd
```

This file is the main source used later by the run-level combiner.

---

# Step 3: Combine several match reports

To combine several match reports, place the key report files into one input folder.

The combiner expects filenames with a common numbered prefix.

Example:

```text
01_fischer-taimanov_all_metrics_3source.csv
01_fischer-taimanov_metric_ratios.csv
01_fischer-taimanov_game_summary_readable.csv

02_fischer-larsen_all_metrics_3source.csv
02_fischer-larsen_metric_ratios.csv
02_fischer-larsen_game_summary_readable.csv

03_fischer-petrosian_all_metrics_3source.csv
03_fischer-petrosian_metric_ratios.csv
03_fischer-petrosian_game_summary_readable.csv

04_fischer-spassky_all_metrics_3source.csv
04_fischer-spassky_metric_ratios.csv
04_fischer-spassky_game_summary_readable.csv
```

Then run:

```bash
python combine_match_reports_v4_7_dpq_pressure_yield.py ^
  --input-dir "fischer_run_reports" ^
  --main-player "Robert James Fischer" ^
  --run-name "Fischer 1971-1972 World-Championship Run" ^
  --outdir "fischer_run_combined"
```

---

## Combiner command-line options

Run:

```bash
python combine_match_reports_v4_7_dpq_pressure_yield.py --help
```

Known inherited options:

| Option          | Required? |               Default | Meaning                                                                     |
| --------------- | --------: | --------------------: | --------------------------------------------------------------------------- |
| `--input-dir`   |       yes |                     — | Directory containing numbered match-report CSV files.                       |
| `--main-player` |       yes |                     — | Exact player name to track across all matches. Must match the CSV spelling. |
| `--run-name`    |        no |    `Combined WDL Run` | Name shown in run-level outputs.                                            |
| `--outdir`      |        no | `combined_run_report` | Output directory.                                                           |

---

## Combiner output files

The combiner creates:

```text
run_all_metrics.csv
run_metric_ratios.csv
run_summary_by_match.csv
run_summary_overall.csv
run_game_summary.csv
run_game_metric_ratios.csv
run_article_report.md
```

### `run_all_metrics.csv`

Long-form table containing every metric from every match.

### `run_metric_ratios.csv`

Adds ratio/difference comparisons between the main player and the opponent/opponent pool.

### `run_summary_by_match.csv`

One row per match.

Useful for comparing the main player’s performance across matches.

### `run_summary_overall.csv`

Overall run-level summary.

Useful for article headlines and comparisons.

### `run_game_summary.csv`

One row per game, normalized from the match-level game summaries.

### `run_game_metric_ratios.csv`

Per-game ratio and difference comparisons.

### `run_article_report.md`

Readable markdown report summarizing the whole run.

---

# Metric guide

## Expected Score

```text
ES = W + 0.5D
```

Expected Score is the Stockfish-WDL estimate of the player’s expected game result from a position.

An ES of:

```text
1.0 = winning expectation
0.5 = drawish expectation
0.0 = losing expectation
```

## WDL Expected-Score Loss

```text
ESLoss = ES_best_before_move − ES_after_played_move
```

This measures how much expected score the played move lost compared with the best available move.

## WDL Move Accuracy

```text
MoveAccuracy = 100 × (1 − ESLoss)
```

A perfect move has accuracy 100.

A move that loses 0.05 expected score has accuracy:

```text
100 × (1 − 0.05) = 95
```

## Game Accuracy

```text
GameAccuracy = (AccuracyA + AccuracyB) / 2
```

This is the average accuracy of both players.

## Mutual Accuracy

```text
MutualAccuracy = AccuracyA × AccuracyB / 100
```

This is a stricter two-player quality metric. It rewards games where both players played accurately.

## Performance Quality

```text
PQ = PlayerAccuracy × GameAccuracy / 100
```

This adjusts a player’s accuracy by the total quality of the game.

The idea:

* high accuracy against high accuracy = more impressive
* high accuracy against low accuracy = still good, but less demanding

## Dominance

```text
DominanceA = AccuracyA − AccuracyB
DominanceB = AccuracyB − AccuracyA
```

Dominance is the accuracy gap between the players.

## Mean ES Loss

Average expected-score loss per move.

Lower is better.

## RMS ES Loss

Root mean square of expected-score losses.

This emphasizes larger errors more than Mean ES Loss.

Lower is better.

## Error Concentration

```text
ErrorConcentration = RMS_ES_Loss / Mean_ES_Loss
```

This estimates whether the player’s errors were spread evenly or concentrated in a few larger mistakes.

## WDL Volatility

WDL Volatility measures how much the expected score moved from one position to the next.

Important:

```text
Volatility is not the same as bad play.
```

A brilliant sacrifice can create volatility. A blunder can also create volatility.

Volatility measures movement, not quality.

## Conversion

```text
Conversion = ActualScore − ExpectedScore
```

Positive conversion means the player scored more than the WDL game-flow expectation.

Negative conversion means the player scored less than the WDL game-flow expectation.

## HardRAP

Result-adjusted performance metric that rewards actual score more directly.

## SoftRAP

Softer result-adjusted performance metric.

Usually less brutally result-dependent than HardRAP.

## CCP Search Difficulty

CCP means:

```text
Checks
Captures
Promotions
```

CCP search difficulty estimates how tactically forcing and candidate-heavy the move choice was.

The general idea:

* Checks, captures, and promotions are forcing candidate moves.
* Positions with many serious forcing candidates are harder to search.
* Positions where one exact forcing line matters are often difficult even if the correct move looks natural afterward.

## Root-Branch Diagnostics

Root-branch diagnostics are intended to explain the structure behind the move choice.

They help answer questions such as:

```text
What were the serious root candidates?
How many candidate branches mattered?
Was the played move close to best?
Was the best move hidden among many branches?
Was the root position narrow or wide?
Did the move require seeing a forcing continuation?
```

Root-branch diagnostics are more structural than DPQ. They are about the search tree and candidate branches.

## DPQ Pressure/Yield Metrics

DPQ means:

```text
Difficulty Pressure Quality
```

DPQ pressure/yield metrics are higher-level interpretive metrics derived from difficulty and performance data.

They help answer questions such as:

```text
How much difficulty did a player face?
How much difficulty did a player cause?
How well did the player survive difficult positions?
How much did the opponent lose under the pressure caused?
```

A useful distinction:

```text
Root-branch diagnostics = structural explanation layer.
DPQ pressure/yield = interpretive player-performance layer.
```

---

# Practical advice

## Use node limits for serious comparisons

For published comparisons, prefer:

```text
--main-nodes
--difficulty-nodes
```

over movetime settings.

Reason: node limits are usually more reproducible than time limits.

## Keep settings consistent

Do not compare one match analyzed at:

```text
--main-nodes 1000000 --difficulty-nodes 50000
```

with another match analyzed at:

```text
--main-nodes 100000 --difficulty-nodes 10000
```

unless you clearly label the difference.

## Keep metadata files

Always keep:

```text
analysis_metadata.csv
analysis_metadata_wide.csv
```

These files record the analysis settings and make the results easier to audit later.

## Use separate folders per match

Recommended structure:

```text
analyses/
  fischer-taimanov/
    wdl_output/
    wdl_report/
  fischer-larsen/
    wdl_output/
    wdl_report/
  fischer-petrosian/
    wdl_output/
    wdl_report/
  fischer-spassky/
    wdl_output/
    wdl_report/
```

Then copy or rename the key report files into a combined folder:

```text
run-input/
  01_fischer-taimanov_all_metrics_3source.csv
  01_fischer-taimanov_metric_ratios.csv
  01_fischer-taimanov_game_summary_readable.csv
  02_fischer-larsen_all_metrics_3source.csv
  02_fischer-larsen_metric_ratios.csv
  02_fischer-larsen_game_summary_readable.csv
```

## Use exact player names

The combiner uses `--main-player` to find the player across matches.

The name must match the spelling in the CSV files.

For example:

```bash
--main-player "Robert James Fischer"
```

is not the same as:

```bash
--main-player "Bobby Fischer"
```

If the name does not match, the combiner may not correctly identify the main player.

## Use `--pgn` in the report step

Adding the PGN to the report generator allows SAN notation in move tables.

This makes `critical_moves.csv`, `difficulty_critical_moves.csv`, and markdown reports much easier to read.

## Start with `--top-n 30`

Recommended:

```bash
--top-n 30
```

This gives enough critical moves and difficulty positions for interpretation without making the report too large.

Use:

```bash
--top-n 50
```

for deeper articles.

Use:

```bash
--top-n 10
```

for quick summaries.

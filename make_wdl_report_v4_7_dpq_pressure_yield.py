#!/usr/bin/env python3
"""
make_wdl_report_v4_7_dpq_pressure_yield.py

One-step match-level report generator for outputs from:
  - wdl_chess_analyzer_v2.py
  - wdl_chess_analyzer_v3_difficulty.py
  - wdl_chess_analyzer_v3_1_3_difficulty.py
  - wdl_chess_analyzer_v3_2_ccp.py

It replaces the older two-step match-level pipeline:
  1) make_wdl_report_v3.py -> all_metrics_3source.csv + game_summary_readable.csv
  2) make_wdl_ratio_report.py -> metric_ratios.csv

Main outputs:
  - all_metrics_3source.csv
  - metric_ratios.csv
  - player_summary.csv
  - game_summary_readable.csv
  - critical_moves.csv
  - volatility_swings.csv
  - hardest_positions.csv                (if difficulty columns exist; faced-by-mover positions)
  - difficulty_critical_moves.csv         (if difficulty columns exist)
  - ccp_hardest_positions.csv             (if CCP columns exist)
  - ccp_critical_moves.csv                (if CCP columns exist)
  - ccp_v2_hardest_positions.csv          (if CCP-v2 columns exist)
  - ccp_v2_critical_moves.csv             (if CCP-v2 columns exist)
  - ccp_v2_log_critical_moves.csv         (if CCP-v2 log columns exist)
  - ccp_v2_log_hardest_positions.csv       (if CCP-v2 log columns exist; log-scaled hardest positions)
  - ccp_v2_probe_confirm_summary.csv       (if v3.5 two-stage columns exist)
  - ccp_v2_probe_confirm_diagnostics.csv   (top v3.5 probe/confirm workload rows)
  - ccp_v2_root_branch_summary.csv           (if v3.6 root-branch diagnostics are supplied)
  - ccp_v2_root_branch_ply_summary.csv       (one row per real game ply summarizing root branches)
  - ccp_v2_root_branch_top_moves.csv         (top confirmed root branches by log score)
  - ccp_v2_root_branch_payoff_moves.csv      (positive/delayed-payoff root branches)
  - ccp_v2_root_branch_workload_rows.csv     (highest root-branch subtree workload rows)
  - cleaner metric tables: string/constant control fields are excluded from all_metrics weighted rows
  - log-scaled CCP-v2 columns in summaries  (if CCP-v2 columns exist)
  - caused/faced difficulty metrics in all_metrics_3source.csv
  - article_report.md

Usage:
python make_wdl_report_v4_7_dpq_pressure_yield.py \
  --per-game wdl_output/per_game_wdl_metrics.csv \
  --per-move wdl_output/per_move_wdl.csv \
  --pgn match.pgn \
  --outdir wdl_report \
  --match-name "Fischer-Petrosian 1971" \
  --top-n 30
"""

import argparse
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------
# Metric direction metadata
# ---------------------------------------------------------------------

SIGNED_OR_ZERO_CROSSING = {
    "conversion", "dominance_wdl", "conversion_sum", "conversion_game",
    "game_conversion_magnitude",
}

LOWER_IS_BETTER = {
    "mean_es_loss", "rms_es_loss", "error_concentration", "volatility_wdl",
    "total_volatility_wdl", "mean_es_loss_game", "rms_es_loss_game",
    "error_concentration_game", "volatility_game_wdl", "total_volatility_game_wdl",
    "difficulty_pure_weighted_es_loss", "difficulty_uncertainty_weighted_es_loss",
    "difficulty_soft_uncertainty_weighted_es_loss", "difficulty_risk_weighted_es_loss",
    "difficulty_defender_pressure_weighted_es_loss", "difficulty_swing_weighted_es_loss",
    "difficulty_pure_weighted_es_loss_game", "difficulty_uncertainty_weighted_es_loss_game",
    "difficulty_soft_uncertainty_weighted_es_loss_game", "difficulty_risk_weighted_es_loss_game",
    "difficulty_defender_pressure_weighted_es_loss_game", "difficulty_swing_weighted_es_loss_game",
}

HIGHER_IS_BETTER = {
    "score", "expected_score", "accuracy_wdl", "pq_wdl", "game_accuracy_wdl",
    "mutual_accuracy_wdl", "hard_rap", "soft_rap",
    "difficulty_pure_weighted_accuracy", "difficulty_uncertainty_weighted_accuracy",
    "difficulty_soft_uncertainty_weighted_accuracy", "difficulty_risk_weighted_accuracy",
    "difficulty_defender_pressure_weighted_accuracy", "difficulty_swing_weighted_accuracy",
    "difficulty_pure_weighted_accuracy_game", "difficulty_uncertainty_weighted_accuracy_game",
    "difficulty_soft_uncertainty_weighted_accuracy_game", "difficulty_risk_weighted_accuracy_game",
    "difficulty_defender_pressure_weighted_accuracy_game", "difficulty_swing_weighted_accuracy_game",
}

# Difficulty / complexity metrics are not "better" or "worse" in the same sense;
# higher means harder, narrower, more live, more unstable, or more forcing.
HIGHER_IS_HARDER = {
    "difficulty_pure", "difficulty_uncertainty", "difficulty_soft_uncertainty",
    "difficulty_risk", "difficulty_defender_pressure", "difficulty_swing",
    "difficulty_pure_game", "difficulty_uncertainty_game", "difficulty_soft_uncertainty_game",
    "difficulty_risk_game", "difficulty_defender_pressure_game", "difficulty_swing_game",
    "legal_rms_loss", "narrowness", "legal_loss_swing", "best_second_gap", "best_third_gap",
    "position_difficulty_pure", "position_difficulty_uncertainty",
    "position_difficulty_soft_uncertainty", "position_difficulty_risk",
    "position_difficulty_defender_pressure", "position_difficulty_swing",
    "ccp_search_difficulty_pure", "ccp_search_difficulty_soft",
    "ccp_v2_search_difficulty_pure", "ccp_v2_search_difficulty_soft",
    "ccp_v2_log_search_difficulty_pure", "ccp_v2_log_search_difficulty_soft", "ccp_v2_log_branch_total",
    "ccp_immediate_burden", "ccp_quiet_to_ccp_burden", "ccp_total_burden",
    "ccp_candidate_ambiguity", "ccp_v2_quiet_pause_burden", "ccp_v2_branch_total",
    "ccp_v2_branch_max", "ccp_v2_branch_mean", "ccp_v2_branch_ambiguity",
    "ccp_v2_log_search_difficulty_pure", "ccp_v2_log_search_difficulty_soft", "ccp_v2_log_branch_total",
}

LOWER_IS_BROADER = {"effective_good_moves", "effective_good_moves_entropy", "ccp_candidate_effective_count", "ccp_v2_branch_effective_count"}

SUM_METRICS = {
    "score", "expected_score", "conversion", "total_volatility_wdl",
    "hard_rap", "soft_rap",
    "total_difficulty_pure", "total_difficulty_uncertainty", "total_difficulty_soft_uncertainty",
    "total_difficulty_risk", "total_difficulty_defender_pressure", "total_difficulty_swing",
}

DIFFICULTY_VARIANTS = [
    "pure",
    "uncertainty",
    "soft_uncertainty",
    "risk",
    "defender_pressure",
    "swing",
]

# Columns in this list receive total exposure and ES-loss-weighted rows in
# all_metrics_3source.csv. Keep it limited to numeric difficulty/burden
# scales. String controls and near-constant configuration flags belong in
# metadata/probe-confirm diagnostics, not in all_metrics as fake metrics.
CCP_SEARCH_VARIANTS = [
    "ccp_search_difficulty_pure",
    "ccp_search_difficulty_soft",
    # Raw CCP-v2 tree-mass variants are kept for diagnostics/backward
    # compatibility, but their weighted accuracies are outlier-sensitive.
    "ccp_v2_search_difficulty_pure",
    "ccp_v2_search_difficulty_soft",
    # Preferred reportable CCP-v2 scales.
    "ccp_v2_log_search_difficulty_pure",
    "ccp_v2_log_search_difficulty_soft",
    "ccp_v2_log_branch_total",
    # Numeric v3.5 workload/allocation diagnostics.
    "ccp_v2_probe_nodes_searched",
    "ccp_v2_probe_eval_attempts",
    "ccp_v2_probe_cap_hit",
    "ccp_v2_probe_root_branch_count",
    "ccp_v2_probe_branch_total",
    "ccp_v2_probe_branch_max",
    "ccp_v2_probe_branch_ambiguity",
    "ccp_v2_confirm_root_moves_selected",
    "ccp_v2_total_two_stage_eval_attempts",
    "ccp_v2_confirm_share_of_probe_branches",
    "ccp_v2_probe_log_branch_total",
]

# Configuration/string columns that should be surfaced only in metadata or
# probe/confirm diagnostics, never as totals or weighted accuracies.
CCP_V2_NON_METRIC_CONTROL_COLS = {
    "ccp_v2_vision_mode",
    "ccp_v2_vision_candidates",
    "ccp_v2_two_stage_enabled",
    "ccp_v2_probe_depth",
    "ccp_v2_confirm_candidates",
    "ccp_v2_confirm_score_mode",
    "ccp_v2_confirm_root_moves_uci",
}

CCP_MOVE_COL_MAP = {
    "ccp_search_difficulty_pure": "ccp_search_difficulty_pure",
    "ccp_search_difficulty_soft": "ccp_search_difficulty_soft",
    "ccp_immediate_burden": "ccp_immediate_burden",
    "ccp_quiet_to_ccp_burden": "ccp_quiet_to_ccp_burden",
    "ccp_total_burden": "ccp_total_burden",
    "ccp_candidate_effective_count": "ccp_candidate_effective_count",
    "ccp_candidate_ambiguity": "ccp_candidate_ambiguity",
    "ccp_legal_check_count": "ccp_legal_check_count",
    "ccp_legal_capture_count": "ccp_legal_capture_count",
    "ccp_legal_promotion_count": "ccp_legal_promotion_count",
    "ccp_legal_immediate_count": "ccp_legal_immediate_count",
    "ccp_attacked_material_value": "ccp_attacked_material_value",
    "ccp_highest_attacked_piece_value": "ccp_highest_attacked_piece_value",
    "ccp_attacked_material_count": "ccp_attacked_material_count",
    # CCP Search Difficulty v2 candidate-tree metrics.
    "ccp_v2_search_difficulty_pure": "ccp_v2_search_difficulty_pure",
    "ccp_v2_search_difficulty_soft": "ccp_v2_search_difficulty_soft",
    "ccp_v2_nodes_searched": "ccp_v2_nodes_searched",
    "ccp_v2_vision_depth": "ccp_v2_vision_depth",
    "ccp_v2_vision_branch": "ccp_v2_vision_branch",
    "ccp_v2_vision_decay": "ccp_v2_vision_decay",
    "ccp_v2_leaf_count": "ccp_v2_leaf_count",
    "ccp_v2_max_chain_length": "ccp_v2_max_chain_length",
    "ccp_v2_total_chain_length": "ccp_v2_total_chain_length",
    "ccp_v2_mean_chain_length": "ccp_v2_mean_chain_length",
    "ccp_v2_quiet_pause_count": "ccp_v2_quiet_pause_count",
    "ccp_v2_quiet_pause_burden": "ccp_v2_quiet_pause_burden",
    "ccp_v2_branch_total": "ccp_v2_branch_total",
    "ccp_v2_branch_max": "ccp_v2_branch_max",
    "ccp_v2_branch_mean": "ccp_v2_branch_mean",
    "ccp_v2_branch_effective_count": "ccp_v2_branch_effective_count",
    "ccp_v2_branch_ambiguity": "ccp_v2_branch_ambiguity",
    "ccp_v2_log_search_difficulty_pure": "ccp_v2_log_search_difficulty_pure",
    "ccp_v2_log_search_difficulty_soft": "ccp_v2_log_search_difficulty_soft",
    "ccp_v2_log_branch_total": "ccp_v2_log_branch_total",
    # v3.5 two-stage probe/confirm diagnostics. These are workload/allocation
    # diagnostics, not quality metrics; they are still useful as faced/caused
    # exposure means in all_metrics and player_summary.
    "ccp_v2_eval_attempts": "ccp_v2_eval_attempts",
    "ccp_v2_cap_hit": "ccp_v2_cap_hit",
    "ccp_v2_probe_nodes_searched": "ccp_v2_probe_nodes_searched",
    "ccp_v2_probe_eval_attempts": "ccp_v2_probe_eval_attempts",
    "ccp_v2_probe_cap_hit": "ccp_v2_probe_cap_hit",
    "ccp_v2_probe_root_branch_count": "ccp_v2_probe_root_branch_count",
    "ccp_v2_probe_branch_total": "ccp_v2_probe_branch_total",
    "ccp_v2_probe_branch_max": "ccp_v2_probe_branch_max",
    "ccp_v2_probe_branch_ambiguity": "ccp_v2_probe_branch_ambiguity",
    "ccp_v2_confirm_root_moves_selected": "ccp_v2_confirm_root_moves_selected",
    "ccp_v2_total_two_stage_eval_attempts": "ccp_v2_total_two_stage_eval_attempts",
    "ccp_v2_confirm_share_of_probe_branches": "ccp_v2_confirm_share_of_probe_branches",
    "ccp_v2_probe_log_branch_total": "ccp_v2_probe_log_branch_total",
}

CCP_V2_COLS = [
    "ccp_v2_available",
    "ccp_v2_depth",
    "ccp_v2_vision_depth",
    "ccp_v2_vision_branch",
    "ccp_v2_vision_decay",
    "ccp_v2_nodes_searched",
    "ccp_v2_leaf_count",
    "ccp_v2_max_chain_length",
    "ccp_v2_total_chain_length",
    "ccp_v2_mean_chain_length",
    "ccp_v2_quiet_pause_count",
    "ccp_v2_quiet_pause_burden",
    "ccp_v2_branch_total",
    "ccp_v2_branch_max",
    "ccp_v2_branch_mean",
    "ccp_v2_branch_effective_count",
    "ccp_v2_branch_ambiguity",
    "ccp_v2_search_difficulty_pure",
    "ccp_v2_search_difficulty_soft",
    "ccp_v2_log_search_difficulty_pure",
    "ccp_v2_log_search_difficulty_soft",
    "ccp_v2_log_branch_total",
]


# ---------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------

def clean_values(values: Iterable[Any]) -> List[float]:
    out: List[float] = []
    for v in values:
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
        except Exception:
            pass
        try:
            f = float(v)
        except Exception:
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def mean(values: Iterable[Any]) -> Optional[float]:
    vals = clean_values(values)
    return sum(vals) / len(vals) if vals else None


def pstdev(values: Iterable[Any]) -> Optional[float]:
    vals = clean_values(values)
    if not vals:
        return None
    if len(vals) == 1:
        return 0.0
    return statistics.pstdev(vals)


def rms(values: Iterable[Any]) -> Optional[float]:
    vals = clean_values(values)
    if not vals:
        return None
    return math.sqrt(sum(v * v for v in vals) / len(vals))


def safe_float(x: Any) -> Optional[float]:
    try:
        if pd.isna(x):
            return None
        f = float(x)
        if not math.isfinite(f):
            return None
        return f
    except Exception:
        return None


def safe_ratio(a: Any, b: Any) -> Optional[float]:
    a = safe_float(a)
    b = safe_float(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def diff(a: Any, b: Any) -> Optional[float]:
    a = safe_float(a)
    b = safe_float(b)
    if a is None or b is None:
        return None
    return a - b


def pct_advantage(a: Any, b: Any) -> Optional[float]:
    a = safe_float(a)
    b = safe_float(b)
    if a is None or b is None or b == 0:
        return None
    return 100.0 * (a - b) / b


def aggregate(values: Iterable[Any], mode: str) -> Optional[float]:
    vals = clean_values(values)
    if not vals:
        return None
    if mode == "sum":
        return sum(vals)
    if mode == "mean":
        return sum(vals) / len(vals)
    if mode == "rms":
        return math.sqrt(sum(v * v for v in vals) / len(vals))
    raise ValueError(f"Unknown aggregation mode: {mode}")


def fmt(x: Any, digits: int = 3) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        return str(x)
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return str(x)


def metric_direction(metric_key: str) -> str:
    key = str(metric_key)
    if key.endswith("_pressure_yield_suffered"):
        return "lower_is_better"
    if key.endswith("_pressure_yield_caused"):
        return "higher_is_better"
    if key.endswith("_dpq"):
        return "higher_is_more_pressure_quality"
    if key.endswith("_caused_share"):
        return "higher_share_of_match_pressure"
    if key.endswith("_faced") or key.endswith("_caused"):
        base = key.rsplit("_", 1)[0]
        if base in CCP_MOVE_COL_MAP:
            return "higher_is_harder"
        if base.startswith("total_ccp_"):
            return "higher_is_more_exposure"
    if (key.startswith("ccp_search_difficulty_") or key.startswith("ccp_v2_log_")) and key.endswith("_weighted_es_loss"):
        return "lower_is_better"
    if (key.startswith("ccp_search_difficulty_") or key.startswith("ccp_v2_log_")) and key.endswith("_weighted_accuracy"):
        return "higher_is_better"
    if key in CCP_MOVE_COL_MAP:
        return "higher_is_harder"
    if key.endswith("_faced") or key.endswith("_caused"):
        base = key.rsplit("_", 1)[0]
        if base in {"effective_good_moves", "effective_good_moves_entropy"}:
            return "lower_means_narrower_or_more_selective"
        if base.startswith("total_difficulty_"):
            return "higher_is_more_exposure"
        if base in {"difficulty_pure", "difficulty_uncertainty", "difficulty_soft_uncertainty", "difficulty_risk", "difficulty_defender_pressure", "difficulty_swing", "legal_rms_loss", "narrowness", "legal_loss_swing", "best_second_gap", "best_third_gap"}:
            return "higher_is_harder"
    if key in LOWER_IS_BETTER:
        return "lower_is_better"
    if key in HIGHER_IS_BETTER:
        return "higher_is_better"
    if key in SIGNED_OR_ZERO_CROSSING:
        return "signed_or_zero_crossing"
    if key in HIGHER_IS_HARDER:
        return "higher_is_harder"
    if key in LOWER_IS_BROADER:
        return "lower_means_narrower_or_more_selective"
    return "context_dependent"

def better_player(metric_key: str, player_A: str, value_A: Any, player_B: str, value_B: Any) -> str:
    va = safe_float(value_A)
    vb = safe_float(value_B)
    if va is None or vb is None:
        return ""
    direction = metric_direction(metric_key)
    if direction == "higher_is_better":
        if va > vb:
            return player_A
        if vb > va:
            return player_B
        return "equal"
    if direction == "lower_is_better":
        if va < vb:
            return player_A
        if vb < va:
            return player_B
        return "equal"
    return ""


def warning_for_metric(metric_key: str, value_A: Any, value_B: Any) -> str:
    va = safe_float(value_A)
    vb = safe_float(value_B)
    key = str(metric_key)
    warnings: List[str] = []
    if key.endswith("_pressure_yield_suffered"):
        warnings.append("Pressure Yield Suffered is difficulty/pressure-weighted ES loss on the player's own moves; lower is better.")
    if key.endswith("_pressure_yield_caused"):
        warnings.append("Pressure Yield Caused is opponent ES loss weighted by the difficulty/pressure immediately caused by this player; higher means more pressure converted into opponent loss.")
    if key.endswith("_dpq"):
        warnings.append("DPQ = player's mean caused pressure × match mean caused pressure; higher means more caused pressure in a high-pressure match, not direct accuracy.")
    if key.endswith("_caused_share"):
        warnings.append("Caused share is the player's proportion of total match pressure caused; it is a style/asymmetry metric, not automatically better play.")
    if key.endswith("_faced"):
        warnings.append("Faced difficulty is measured before this player's own move; higher means more difficulty exposure, not better play by itself.")
    if key.endswith("_caused"):
        warnings.append("Caused difficulty is attributed one ply backward to the previous mover; higher means more immediate opponent difficulty caused, not necessarily better play by itself.")
    if key in SIGNED_OR_ZERO_CROSSING:
        warnings.append("Ratios may be misleading because the metric is signed or can cross zero; prefer difference.")
    if va == 0 or vb == 0:
        warnings.append("One value is zero; one directional ratio is undefined.")
    if va is not None and vb is not None and (va < 0 or vb < 0):
        warnings.append("Negative values present; ratio interpretation is unstable.")
    if key in HIGHER_IS_HARDER or key.startswith("ccp_v2_log_"):
        warnings.append("Higher means more difficult/complex, not necessarily better play. Log CCP-v2 metrics are outlier-compressed companion scales for stability checks.")
    if key in LOWER_IS_BROADER:
        warnings.append("Lower usually means fewer effective good moves / narrower choice, not necessarily worse play.")
    return " ".join(warnings)

def result_score_for_white(result: Any) -> Optional[float]:
    if result == "1-0":
        return 1.0
    if result == "0-1":
        return 0.0
    if result == "1/2-1/2":
        return 0.5
    return None


def maybe_col(df: pd.DataFrame, col: str) -> bool:
    return col in df.columns


def side_col(side: str) -> str:
    return "A" if side == "White" else "B"


# ---------------------------------------------------------------------
# Input enrichment
# ---------------------------------------------------------------------

def add_san_if_available(per_move: pd.DataFrame, pgn_path: Optional[str] = None) -> pd.DataFrame:
    df = per_move.copy()
    if pgn_path is None:
        if "move_san" not in df.columns:
            df["move_san"] = ""
        return df

    try:
        import chess.pgn  # type: ignore
        san_map: Dict[Tuple[int, int], str] = {}
        with open(pgn_path, encoding="utf-8", errors="replace") as f:
            game_id = 1
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                board = game.board()
                ply = 1
                for move in game.mainline_moves():
                    san_map[(game_id, ply)] = board.san(move)
                    board.push(move)
                    ply += 1
                game_id += 1

        df["move_san"] = df.apply(
            lambda r: san_map.get((int(r["game_id"]), int(r["ply"])), ""),
            axis=1,
        )
    except Exception as e:
        print(f"Warning: SAN generation failed: {e}")
        df["move_san"] = ""
    return df



def add_best_move_san_if_available(per_move: pd.DataFrame, pgn_path: Optional[str] = None) -> pd.DataFrame:
    """Add best_move_uci / best_move_san columns when analyzer provides legal_best_move_uci.

    Older analyzer outputs did not include the best move UCI. For those files, this
    function leaves best_move_* blank, except that if played_move_rank == 1 it can
    safely mirror the played move as the best move.
    """
    df = per_move.copy()
    if "best_move_uci" not in df.columns:
        if "legal_best_move_uci" in df.columns:
            df["best_move_uci"] = df["legal_best_move_uci"]
        else:
            df["best_move_uci"] = ""
            if "played_move_rank" in df.columns and "move_uci" in df.columns:
                try:
                    mask = pd.to_numeric(df["played_move_rank"], errors="coerce") == 1
                    df.loc[mask, "best_move_uci"] = df.loc[mask, "move_uci"]
                except Exception:
                    pass
    if "best_move_san" not in df.columns:
        df["best_move_san"] = ""

    if pgn_path is None or "best_move_uci" not in df.columns:
        return df

    try:
        import chess  # type: ignore
        import chess.pgn  # type: ignore
        san_map: Dict[Tuple[int, int], str] = {}
        with open(pgn_path, encoding="utf-8", errors="replace") as f:
            game_id = 1
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                board = game.board()
                ply = 1
                for _played in game.mainline_moves():
                    row = df[(df["game_id"] == game_id) & (df["ply"] == ply)]
                    if not row.empty:
                        uci = str(row.iloc[0].get("best_move_uci", "") or "")
                        if uci:
                            try:
                                m = chess.Move.from_uci(uci)
                                if m in board.legal_moves:
                                    san_map[(game_id, ply)] = board.san(m)
                            except Exception:
                                pass
                    board.push(_played)
                    ply += 1
                game_id += 1
        df["best_move_san"] = df.apply(
            lambda r: san_map.get((int(r["game_id"]), int(r["ply"])), ""),
            axis=1,
        )
    except Exception as e:
        print(f"Warning: best-move SAN generation failed: {e}")
    return df

def add_player_names_to_moves(per_move: pd.DataFrame, per_game: pd.DataFrame) -> pd.DataFrame:
    names = per_game[["game_id", "white", "black", "result"]].copy()
    df = per_move.merge(names, on="game_id", how="left")
    df["player"] = df.apply(lambda r: r["white"] if r["mover"] == "White" else r["black"], axis=1)
    df["opponent"] = df.apply(lambda r: r["black"] if r["mover"] == "White" else r["white"], axis=1)
    df["move_no"] = ((df["ply"] + 1) // 2).astype(int)
    return df


def add_difficulty_causation(per_move_named: pd.DataFrame) -> pd.DataFrame:
    """
    Add previous-move causation labels for difficulty interpretation.

    The raw analyzer difficulty columns describe the position BEFORE the current
    move. Therefore they are difficulty FACED by the current mover. Except for
    ply 1, that same position was CAUSED, in the immediate practical sense, by
    the previous mover's move. This does not claim full strategic causation; it
    is a one-ply attribution useful for reports such as "difficulty caused".
    """
    df = per_move_named.sort_values(["game_id", "ply"]).copy()
    for col in ["player", "mover", "move_uci", "move_san", "ply"]:
        if col in df.columns:
            df[f"caused_by_{col}"] = df.groupby("game_id")[col].shift(1)

    df["difficulty_faced_by_player"] = df.get("player")
    df["difficulty_caused_by_player"] = df.get("caused_by_player")
    df["difficulty_target_player"] = df.get("player")
    return df


def log1p_nonnegative_value(x: Any) -> Optional[float]:
    f = safe_float(x)
    if f is None:
        return None
    return math.log1p(max(0.0, f))


def add_ccp_v2_log_metrics(per_move_named: pd.DataFrame, per_game: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Add log1p-scaled CCP-v2 metrics and per-game summaries.

    Raw recursive CCP-v2 branch totals can span many orders of magnitude as
    depth/call limits rise. These companion metrics preserve ordering within a
    fixed raw column but make match/run comparisons more stable and readable.
    """
    pm = per_move_named.copy()
    pg = per_game.copy()
    derived = {
        "ccp_v2_search_difficulty_pure": "ccp_v2_log_search_difficulty_pure",
        "ccp_v2_search_difficulty_soft": "ccp_v2_log_search_difficulty_soft",
        "ccp_v2_branch_total": "ccp_v2_log_branch_total",
    }
    for src, dst in derived.items():
        if src in pm.columns and dst not in pm.columns:
            pm[dst] = pm[src].map(log1p_nonnegative_value)

    log_cols = [c for c in derived.values() if c in pm.columns]
    if not log_cols or "game_id" not in pm.columns or "mover" not in pm.columns:
        return pm, pg

    def summarize_moves(moves: pd.DataFrame, suffix: str, idx: int) -> None:
        for col in log_cols:
            vals = moves[col] if col in moves.columns else []
            pg.loc[idx, f"mean_{col}_{suffix}"] = mean(vals)
            pg.loc[idx, f"sd_{col}_{suffix}"] = pstdev(vals)
            pg.loc[idx, f"total_{col}_{suffix}"] = sum(clean_values(vals))
            wl = weighted_loss_from_moves(moves, col)
            pg.loc[idx, f"{col}_weighted_es_loss_{suffix}"] = wl
            pg.loc[idx, f"{col}_weighted_accuracy_{suffix}"] = None if wl is None else 100.0 * (1.0 - wl)

    for idx, gr in pg.iterrows():
        gid = gr.get("game_id")
        gpm = pm[pm["game_id"] == gid]
        summarize_moves(gpm[gpm["mover"] == "White"], "A", idx)
        summarize_moves(gpm[gpm["mover"] == "Black"], "B", idx)
        summarize_moves(gpm, "game", idx)
    return pm, pg


def add_ccp_v2_probe_confirm_derived(per_move_named: pd.DataFrame) -> pd.DataFrame:
    """Add v3.5 two-stage probe/confirm companion diagnostics.

    The analyzer writes raw per-root probe/confirm fields. This function adds a
    few safe derived columns so reports can compare allocation/workload without
    requiring spreadsheet formulas. These columns are purely diagnostic.
    """
    df = per_move_named.copy()

    if "ccp_v2_probe_branch_total" in df.columns and "ccp_v2_probe_log_branch_total" not in df.columns:
        df["ccp_v2_probe_log_branch_total"] = df["ccp_v2_probe_branch_total"].map(log1p_nonnegative_value)

    if "ccp_v2_probe_eval_attempts" in df.columns or "ccp_v2_eval_attempts" in df.columns:
        probe = pd.to_numeric(df.get("ccp_v2_probe_eval_attempts", 0), errors="coerce").fillna(0)
        confirm = pd.to_numeric(df.get("ccp_v2_eval_attempts", 0), errors="coerce").fillna(0)
        df["ccp_v2_total_two_stage_eval_attempts"] = probe + confirm

    if "ccp_v2_confirm_root_moves_selected" in df.columns and "ccp_v2_probe_root_branch_count" in df.columns:
        selected = pd.to_numeric(df["ccp_v2_confirm_root_moves_selected"], errors="coerce")
        branches = pd.to_numeric(df["ccp_v2_probe_root_branch_count"], errors="coerce").replace({0: pd.NA})
        df["ccp_v2_confirm_share_of_probe_branches"] = selected / branches

    # Normalize booleans to numeric companions for stable aggregation if needed.
    for col in ["ccp_v2_two_stage_enabled", "ccp_v2_cap_hit", "ccp_v2_probe_cap_hit"]:
        if col in df.columns:
            num_col = f"{col}_numeric"
            if num_col not in df.columns:
                df[num_col] = df[col].map(lambda x: 1.0 if str(x).strip().lower() in {"true", "1", "yes"} else (0.0 if str(x).strip().lower() in {"false", "0", "no"} else safe_float(x)))
    return df


def build_ccp_v2_probe_confirm_summary(per_move_named: pd.DataFrame) -> pd.DataFrame:
    """Create a compact one-row summary of v3.5 probe/confirm workload."""
    if "ccp_v2_probe_eval_attempts" not in per_move_named.columns and "ccp_v2_two_stage_enabled" not in per_move_named.columns:
        return pd.DataFrame()

    df = per_move_named.copy()
    rows = []
    row: Dict[str, Any] = {
        "plies": len(df),
        "two_stage_rows": int(pd.to_numeric(df.get("ccp_v2_two_stage_enabled_numeric", pd.Series([0]*len(df))), errors="coerce").fillna(0).sum()) if "ccp_v2_two_stage_enabled_numeric" in df.columns else None,
        "mean_probe_eval_attempts": mean(df.get("ccp_v2_probe_eval_attempts", [])),
        "mean_confirm_eval_attempts": mean(df.get("ccp_v2_eval_attempts", [])),
        "mean_total_eval_attempts": mean(df.get("ccp_v2_total_two_stage_eval_attempts", [])),
        "probe_cap_hit_rate": mean(df.get("ccp_v2_probe_cap_hit_numeric", [])),
        "confirm_cap_hit_rate": mean(df.get("ccp_v2_cap_hit_numeric", [])),
        "mean_probe_nodes_searched": mean(df.get("ccp_v2_probe_nodes_searched", [])),
        "mean_confirm_nodes_searched": mean(df.get("ccp_v2_nodes_searched", [])),
        "mean_probe_root_branch_count": mean(df.get("ccp_v2_probe_root_branch_count", [])),
        "mean_confirm_root_moves_selected": mean(df.get("ccp_v2_confirm_root_moves_selected", [])),
        "mean_confirm_share_of_probe_branches": mean(df.get("ccp_v2_confirm_share_of_probe_branches", [])),
        "mean_probe_log_branch_total": mean(df.get("ccp_v2_probe_log_branch_total", [])),
        "mean_confirm_log_branch_total": mean(df.get("ccp_v2_log_branch_total", [])),
        "mean_confirm_log_search_difficulty": mean(df.get("ccp_v2_log_search_difficulty_pure", [])),
        "mean_confirm_log_soft_search_difficulty": mean(df.get("ccp_v2_log_search_difficulty_soft", [])),
        "mean_max_chain_length": mean(df.get("ccp_v2_max_chain_length", [])),
        "mean_quiet_pause_burden": mean(df.get("ccp_v2_quiet_pause_burden", [])),
    }
    rows.append(row)

    # Optional by-player rows make it easier to inspect asymmetry.
    if "player" in df.columns:
        for player, g in df.groupby("player", dropna=True):
            prow = dict(row)
            prow.update({
                "scope": f"player:{player}",
                "plies": len(g),
                "two_stage_rows": int(pd.to_numeric(g.get("ccp_v2_two_stage_enabled_numeric", pd.Series([0]*len(g))), errors="coerce").fillna(0).sum()) if "ccp_v2_two_stage_enabled_numeric" in g.columns else None,
                "mean_probe_eval_attempts": mean(g.get("ccp_v2_probe_eval_attempts", [])),
                "mean_confirm_eval_attempts": mean(g.get("ccp_v2_eval_attempts", [])),
                "mean_total_eval_attempts": mean(g.get("ccp_v2_total_two_stage_eval_attempts", [])),
                "probe_cap_hit_rate": mean(g.get("ccp_v2_probe_cap_hit_numeric", [])),
                "confirm_cap_hit_rate": mean(g.get("ccp_v2_cap_hit_numeric", [])),
                "mean_probe_nodes_searched": mean(g.get("ccp_v2_probe_nodes_searched", [])),
                "mean_confirm_nodes_searched": mean(g.get("ccp_v2_nodes_searched", [])),
                "mean_probe_root_branch_count": mean(g.get("ccp_v2_probe_root_branch_count", [])),
                "mean_confirm_root_moves_selected": mean(g.get("ccp_v2_confirm_root_moves_selected", [])),
                "mean_confirm_share_of_probe_branches": mean(g.get("ccp_v2_confirm_share_of_probe_branches", [])),
                "mean_probe_log_branch_total": mean(g.get("ccp_v2_probe_log_branch_total", [])),
                "mean_confirm_log_branch_total": mean(g.get("ccp_v2_log_branch_total", [])),
                "mean_confirm_log_search_difficulty": mean(g.get("ccp_v2_log_search_difficulty_pure", [])),
                "mean_confirm_log_soft_search_difficulty": mean(g.get("ccp_v2_log_search_difficulty_soft", [])),
                "mean_max_chain_length": mean(g.get("ccp_v2_max_chain_length", [])),
                "mean_quiet_pause_burden": mean(g.get("ccp_v2_quiet_pause_burden", [])),
            })
            rows.append(prow)
    if rows and "scope" not in rows[0]:
        rows[0]["scope"] = "all"
    return pd.DataFrame(rows)


def build_ccp_v2_probe_confirm_diagnostics(per_move_named: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Return the highest-workload probe/confirm rows for debugging allocation."""
    if "ccp_v2_probe_eval_attempts" not in per_move_named.columns and "ccp_v2_total_two_stage_eval_attempts" not in per_move_named.columns:
        return pd.DataFrame()
    df = per_move_named.copy()
    sort_col = "ccp_v2_total_two_stage_eval_attempts" if "ccp_v2_total_two_stage_eval_attempts" in df.columns else "ccp_v2_probe_eval_attempts"
    cols = [
        "game_id", "ply", "move_no", "mover", "player", "move_uci", "move_san", "best_move_uci", "best_move_san",
        "wdl_es_loss", "wdl_move_accuracy",
        "ccp_v2_two_stage_enabled", "ccp_v2_depth", "ccp_v2_probe_depth",
        "ccp_v2_probe_eval_attempts", "ccp_v2_eval_attempts", "ccp_v2_total_two_stage_eval_attempts",
        "ccp_v2_probe_cap_hit", "ccp_v2_cap_hit",
        "ccp_v2_probe_nodes_searched", "ccp_v2_nodes_searched",
        "ccp_v2_probe_root_branch_count", "ccp_v2_confirm_candidates", "ccp_v2_confirm_root_moves_selected",
        "ccp_v2_confirm_share_of_probe_branches", "ccp_v2_confirm_score_mode", "ccp_v2_confirm_root_moves_uci",
        "ccp_v2_probe_log_branch_total", "ccp_v2_log_branch_total",
        "ccp_v2_log_search_difficulty_pure", "ccp_v2_log_search_difficulty_soft",
        "ccp_v2_max_chain_length", "ccp_v2_leaf_count", "ccp_v2_quiet_pause_burden",
    ]
    return select_columns(df, cols).sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)


# ---------------------------------------------------------------------
# Player/game rows
# ---------------------------------------------------------------------

def build_player_game_rows(per_game: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, r in per_game.iterrows():
        white_score = result_score_for_white(r.get("result"))
        black_score = None if white_score is None else 1.0 - white_score
        for side_name, suffix, player_col, opp_col, score in [
            ("White", "A", "white", "black", white_score),
            ("Black", "B", "black", "white", black_score),
        ]:
            row: Dict[str, Any] = {
                "game_id": r.get("game_id"),
                "player": r.get(player_col),
                "side": side_name,
                "opponent": r.get(opp_col),
                "result": r.get("result"),
                "score": score,
                "accuracy_wdl": r.get(f"accuracy_{suffix}_wdl"),
                "accuracy_sd_wdl": r.get(f"accuracy_sd_{suffix}_wdl"),
                "pq_wdl": r.get(f"pq_{suffix}_wdl"),
                "dominance_wdl": r.get(f"dominance_{suffix}_wdl"),
                "volatility_wdl": r.get(f"volatility_{suffix}_wdl"),
                "volatility_sd_wdl": r.get(f"volatility_sd_{suffix}_wdl"),
                "total_volatility_wdl": r.get(f"total_volatility_{suffix}_wdl"),
                "mean_es_loss": r.get(f"mean_es_loss_{suffix}"),
                "es_loss_sd": r.get(f"es_loss_sd_{suffix}"),
                "rms_es_loss": r.get(f"rms_es_loss_{suffix}"),
                "error_concentration": r.get(f"error_concentration_{suffix}"),
                "hard_rap": r.get(f"hard_rap_{suffix}"),
                "soft_rap": r.get(f"soft_rap_{suffix}"),
                "expected_score": r.get(f"expected_score_{suffix}"),
                "conversion": r.get(f"conversion_{suffix}"),
            }

            # Difficulty variants already summarized by analyzer v3+.
            for variant in DIFFICULTY_VARIANTS:
                for stem in ["mean", "sd", "total"]:
                    src = f"{stem}_difficulty_{variant}_{suffix}"
                    if src in per_game.columns:
                        row[f"{stem}_difficulty_{variant}"] = r.get(src)
                for stem in ["difficulty"]:
                    for tail in ["weighted_es_loss", "weighted_accuracy"]:
                        src = f"{stem}_{variant}_{tail}_{suffix}"
                        # actual source name is difficulty_{variant}_weighted_es_loss_A
                        if src in per_game.columns:
                            row[f"difficulty_{variant}_{tail}"] = r.get(src)
                src_loss = f"difficulty_{variant}_weighted_es_loss_{suffix}"
                src_acc = f"difficulty_{variant}_weighted_accuracy_{suffix}"
                if src_loss in per_game.columns:
                    row[f"difficulty_{variant}_weighted_es_loss"] = r.get(src_loss)
                if src_acc in per_game.columns:
                    row[f"difficulty_{variant}_weighted_accuracy"] = r.get(src_acc)

            for base in ["legal_rms_loss", "narrowness", "effective_good_moves"]:
                mean_src = f"mean_{base}_{suffix}"
                sd_src = f"sd_{base}_{suffix}"
                if mean_src in per_game.columns:
                    row[f"mean_{base}"] = r.get(mean_src)
                if sd_src in per_game.columns:
                    row[f"sd_{base}"] = r.get(sd_src)

            rows.append(row)
    return pd.DataFrame(rows)


def choose_two_players(player_summary: pd.DataFrame, player_order: Optional[List[str]] = None) -> Tuple[Optional[str], Optional[str]]:
    if player_order:
        existing = set(player_summary["player"].dropna().astype(str).tolist()) if "player" in player_summary else set()
        ordered = [p for p in player_order if p in existing]
        if len(ordered) >= 2:
            return ordered[0], ordered[1]
    players = player_summary["player"].tolist() if "player" in player_summary else []
    if len(players) >= 2:
        return players[0], players[1]
    if len(players) == 1:
        return players[0], None
    return None, None


# ---------------------------------------------------------------------
# Summary construction
# ---------------------------------------------------------------------

def move_values_for_player(player_name: Optional[str], per_move_named: pd.DataFrame, col: str) -> List[Any]:
    if player_name is None or col not in per_move_named.columns:
        return []
    return per_move_named.loc[per_move_named["player"] == player_name, col].tolist()


def move_values_caused_by_player(player_name: Optional[str], per_move_named: pd.DataFrame, col: str) -> List[Any]:
    if player_name is None or col not in per_move_named.columns or "difficulty_caused_by_player" not in per_move_named.columns:
        return []
    return per_move_named.loc[per_move_named["difficulty_caused_by_player"] == player_name, col].tolist()


def game_values_for_player(player_name: Optional[str], player_games: pd.DataFrame, col: str) -> List[Any]:
    if player_name is None or col not in player_games.columns:
        return []
    return player_games.loc[player_games["player"] == player_name, col].tolist()


def weighted_loss_from_moves(moves: pd.DataFrame, difficulty_col: str) -> Optional[float]:
    if difficulty_col not in moves.columns or "wdl_es_loss" not in moves.columns:
        return None
    pairs = []
    for _, r in moves.iterrows():
        d = safe_float(r.get(difficulty_col))
        loss = safe_float(r.get("wdl_es_loss"))
        if d is not None and loss is not None and d > 0:
            pairs.append((d, loss))
    if not pairs:
        return None
    denom = sum(d for d, _ in pairs)
    if denom == 0:
        return None
    return sum(d * loss for d, loss in pairs) / denom



# ---------------------------------------------------------------------
# Difficulty Pressure Quality (DPQ) and Pressure Yield helpers
# ---------------------------------------------------------------------

# These are derived in the reporter, not the analyzer, because they combine
# already-existing difficulty/pressure exposure columns with WDL ES-loss.
# Keep this list focused on genuine pressure/difficulty scales. Workload-only
# controls such as eval attempts, cap hits, and selected-root counts are excluded.
PRESSURE_METRIC_SPECS = [
    ("difficulty_pure", "Pure Position Difficulty", "position_difficulty_pure"),
    ("difficulty_soft_uncertainty", "Soft-Uncertainty Difficulty", "position_difficulty_soft_uncertainty"),
    ("difficulty_swing", "Swing-Leveraged Difficulty", "position_difficulty_swing"),
    ("ccp_search_difficulty_pure", "CCP Search Difficulty", "ccp_search_difficulty_pure"),
    ("ccp_search_difficulty_soft", "CCP Soft Search Difficulty", "ccp_search_difficulty_soft"),
    ("ccp_total_burden", "CCP Total Burden", "ccp_total_burden"),
    ("ccp_quiet_to_ccp_burden", "CCP Quiet-to-CCP Burden", "ccp_quiet_to_ccp_burden"),
    ("ccp_candidate_ambiguity", "CCP Candidate Ambiguity", "ccp_candidate_ambiguity"),
    ("ccp_v2_log_search_difficulty_pure", "CCP v2 Log Search Difficulty", "ccp_v2_log_search_difficulty_pure"),
    ("ccp_v2_log_search_difficulty_soft", "CCP v2 Log Soft Search Difficulty", "ccp_v2_log_search_difficulty_soft"),
    ("ccp_v2_log_branch_total", "CCP v2 Log Branch Total", "ccp_v2_log_branch_total"),
    ("ccp_v2_quiet_pause_burden", "CCP v2 Quiet-Pause Burden", "ccp_v2_quiet_pause_burden"),
]


def pressure_metric_col_map() -> Dict[str, str]:
    return {key: col for key, _label, col in PRESSURE_METRIC_SPECS}


def available_pressure_metric_specs(per_move_named: pd.DataFrame) -> List[Tuple[str, str, str]]:
    return [(key, label, col) for key, label, col in PRESSURE_METRIC_SPECS if col in per_move_named.columns]


def caused_moves_for_player(per_move_named: pd.DataFrame, player_name: Optional[str]) -> pd.DataFrame:
    if player_name is None or "difficulty_caused_by_player" not in per_move_named.columns:
        return pd.DataFrame()
    return per_move_named[per_move_named["difficulty_caused_by_player"] == player_name]


def pressure_total_caused(per_move_named: pd.DataFrame, col: str, player_name: Optional[str] = None) -> Optional[float]:
    if col not in per_move_named.columns:
        return None
    if player_name is None:
        if "difficulty_caused_by_player" in per_move_named.columns:
            rows = per_move_named[per_move_named["difficulty_caused_by_player"].notna()]
        else:
            rows = per_move_named
    else:
        rows = caused_moves_for_player(per_move_named, player_name)
    vals = clean_values(rows[col]) if col in rows.columns else []
    return sum(vals) if vals else None


def pressure_mean_caused(per_move_named: pd.DataFrame, col: str, player_name: Optional[str] = None) -> Optional[float]:
    if col not in per_move_named.columns:
        return None
    if player_name is None:
        if "difficulty_caused_by_player" in per_move_named.columns:
            rows = per_move_named[per_move_named["difficulty_caused_by_player"].notna()]
        else:
            rows = per_move_named
    else:
        rows = caused_moves_for_player(per_move_named, player_name)
    return mean(rows[col]) if col in rows.columns else None


def pressure_caused_share(per_move_named: pd.DataFrame, col: str, player_name: Optional[str]) -> Optional[float]:
    player_total = pressure_total_caused(per_move_named, col, player_name)
    match_total = pressure_total_caused(per_move_named, col, None)
    if player_total is None or match_total is None or match_total == 0:
        return None
    return player_total / match_total


def difficulty_pressure_quality(per_move_named: pd.DataFrame, col: str, player_name: Optional[str]) -> Optional[float]:
    """DPQ = player's mean caused pressure × match mean caused pressure.

    This is a per-move, match-length-neutral analogue to Performance Quality:
    it rewards a player for causing high pressure inside a match that itself
    had a high average pressure level.
    """
    player_mean = pressure_mean_caused(per_move_named, col, player_name)
    match_mean = pressure_mean_caused(per_move_named, col, None)
    if player_mean is None or match_mean is None:
        return None
    return player_mean * match_mean


def pressure_yield_suffered(per_move_named: pd.DataFrame, col: str, player_name: Optional[str]) -> Optional[float]:
    """Difficulty-weighted ES loss suffered by this player on their own moves."""
    if player_name is None or col not in per_move_named.columns:
        return None
    return weighted_loss_from_moves(per_move_named[per_move_named["player"] == player_name], col)


def pressure_yield_caused(per_move_named: pd.DataFrame, col: str, player_name: Optional[str]) -> Optional[float]:
    """Opponent ES loss in positions whose pressure is attributed to this player.

    This is continuous: every row contributes weight = difficulty/pressure value
    and loss = opponent's WDL ES loss on the move they then chose.
    """
    if player_name is None or col not in per_move_named.columns:
        return None
    rows = caused_moves_for_player(per_move_named, player_name)
    return weighted_loss_from_moves(rows, col)


def pressure_metric_base_from_key(metric_key: str, suffix: str) -> Optional[str]:
    key = str(metric_key)
    if key.endswith(suffix):
        base = key[:-len(suffix)]
        if base in pressure_metric_col_map():
            return base
    return None

def values_for_metric(player_name: Optional[str], per_move_named: pd.DataFrame, player_games: pd.DataFrame, metric_key: str) -> List[Any]:
    if player_name is None:
        return []
    # Game-level / result metrics
    if metric_key in {
        "score", "expected_score", "conversion", "pq_wdl", "dominance_wdl",
        "rms_es_loss", "error_concentration", "total_volatility_wdl", "hard_rap", "soft_rap",
    }:
        return game_values_for_player(player_name, player_games, metric_key)

    # Move-level WDL metrics
    if metric_key == "accuracy_wdl":
        return move_values_for_player(player_name, per_move_named, "wdl_move_accuracy")
    if metric_key == "mean_es_loss":
        return move_values_for_player(player_name, per_move_named, "wdl_es_loss")
    if metric_key == "volatility_wdl":
        return move_values_for_player(player_name, per_move_named, "wdl_volatility_swing")

    # Difficulty move-level metrics.
    # "faced" = position difficulty before this player's own move.
    # "caused" = position difficulty before the opponent's next move, attributed to this player's previous move.
    move_col_map = {
        "difficulty_pure": "position_difficulty_pure",
        "difficulty_uncertainty": "position_difficulty_uncertainty",
        "difficulty_soft_uncertainty": "position_difficulty_soft_uncertainty",
        "difficulty_risk": "position_difficulty_risk",
        "difficulty_defender_pressure": "position_difficulty_defender_pressure",
        "difficulty_swing": "position_difficulty_swing",
        "legal_rms_loss": "legal_rms_loss",
        "narrowness": "narrowness",
        "effective_good_moves": "effective_good_moves",
        "legal_loss_swing": "legal_loss_swing",
        "best_second_gap": "best_second_gap",
        "best_third_gap": "best_third_gap",
    }
    move_col_map.update(CCP_MOVE_COL_MAP)
    if metric_key.endswith("_faced"):
        base = metric_key[:-6]
        if base in move_col_map:
            return move_values_for_player(player_name, per_move_named, move_col_map[base])
    if metric_key.endswith("_caused"):
        base = metric_key[:-7]
        if base in move_col_map:
            return move_values_caused_by_player(player_name, per_move_named, move_col_map[base])
    if metric_key in move_col_map:
        # Backward-compatible fallback: raw difficulty is FACED by the mover.
        return move_values_for_player(player_name, per_move_named, move_col_map[metric_key])

    # Total difficulty exposure metrics.
    if metric_key.startswith("total_") and metric_key.endswith("_faced"):
        base = metric_key[len("total_"):-6]
        if base in move_col_map:
            return move_values_for_player(player_name, per_move_named, move_col_map[base])
    if metric_key.startswith("total_") and metric_key.endswith("_caused"):
        base = metric_key[len("total_"):-7]
        if base in move_col_map:
            return move_values_caused_by_player(player_name, per_move_named, move_col_map[base])

    # Difficulty weighted metrics are naturally FACED-performance metrics.
    for variant in DIFFICULTY_VARIANTS:
        if metric_key == f"difficulty_{variant}_weighted_es_loss":
            return game_values_for_player(player_name, player_games, metric_key)
        if metric_key == f"difficulty_{variant}_weighted_accuracy":
            return game_values_for_player(player_name, player_games, metric_key)
        if metric_key == f"total_difficulty_{variant}":
            return game_values_for_player(player_name, player_games, f"total_difficulty_{variant}")

    return []


def aggregate_value_for_metric(player_name: Optional[str], per_move_named: pd.DataFrame, player_games: pd.DataFrame, metric_key: str, mode: str) -> Optional[float]:
    if player_name is None:
        return None
    moves = per_move_named[per_move_named["player"] == player_name]

    base = pressure_metric_base_from_key(metric_key, "_caused_share")
    if base is not None:
        return pressure_caused_share(per_move_named, pressure_metric_col_map()[base], player_name)
    base = pressure_metric_base_from_key(metric_key, "_dpq")
    if base is not None:
        return difficulty_pressure_quality(per_move_named, pressure_metric_col_map()[base], player_name)
    base = pressure_metric_base_from_key(metric_key, "_pressure_yield_suffered")
    if base is not None:
        return pressure_yield_suffered(per_move_named, pressure_metric_col_map()[base], player_name)
    base = pressure_metric_base_from_key(metric_key, "_pressure_yield_caused")
    if base is not None:
        return pressure_yield_caused(per_move_named, pressure_metric_col_map()[base], player_name)
    # Compute match-level difficulty-weighted loss/accuracy from all moves, not merely mean of games.
    for variant in DIFFICULTY_VARIANTS:
        if metric_key == f"difficulty_{variant}_weighted_es_loss":
            return weighted_loss_from_moves(moves, f"position_difficulty_{variant}")
        if metric_key == f"difficulty_{variant}_weighted_accuracy":
            loss = weighted_loss_from_moves(moves, f"position_difficulty_{variant}")
            return None if loss is None else 100.0 * (1.0 - loss)
    for ccp_variant in CCP_SEARCH_VARIANTS:
        if metric_key == f"{ccp_variant}_weighted_es_loss":
            return weighted_loss_from_moves(moves, ccp_variant)
        if metric_key == f"{ccp_variant}_weighted_accuracy":
            loss = weighted_loss_from_moves(moves, ccp_variant)
            return None if loss is None else 100.0 * (1.0 - loss)

    vals = values_for_metric(player_name, per_move_named, player_games, metric_key)
    return aggregate(vals, mode)


def build_player_summary(per_game: pd.DataFrame, per_move_named: pd.DataFrame) -> pd.DataFrame:
    pg = build_player_game_rows(per_game)
    rows: List[Dict[str, Any]] = []
    for player, player_games in pg.groupby("player", dropna=True):
        player_moves = per_move_named[per_move_named["player"] == player]
        row: Dict[str, Any] = {
            "player": player,
            "games": int(player_games["game_id"].nunique()),
            "moves": int(len(player_moves)),
            "score_sum": aggregate(player_games["score"], "sum"),
            "score_mean": mean(player_games["score"]),
            "score_sd": pstdev(player_games["score"]),
            "expected_score_sum": aggregate(player_games["expected_score"], "sum"),
            "expected_score_mean": mean(player_games["expected_score"]),
            "expected_score_sd": pstdev(player_games["expected_score"]),
            "conversion_sum": diff(aggregate(player_games["score"], "sum"), aggregate(player_games["expected_score"], "sum")),
            "conversion_mean": mean(player_games["conversion"]),
            "conversion_sd": pstdev(player_games["conversion"]),
            "accuracy_wdl_mean": mean(player_moves.get("wdl_move_accuracy", [])),
            "accuracy_wdl_sd": pstdev(player_moves.get("wdl_move_accuracy", [])),
            "pq_wdl_mean": mean(player_games.get("pq_wdl", [])),
            "pq_wdl_sd": pstdev(player_games.get("pq_wdl", [])),
            "dominance_wdl_mean": mean(player_games.get("dominance_wdl", [])),
            "dominance_wdl_sd": pstdev(player_games.get("dominance_wdl", [])),
            "mean_es_loss": mean(player_moves.get("wdl_es_loss", [])),
            "es_loss_sd": pstdev(player_moves.get("wdl_es_loss", [])),
            "rms_es_loss": rms(player_moves.get("wdl_es_loss", [])),
            "error_concentration": safe_ratio(rms(player_moves.get("wdl_es_loss", [])), mean(player_moves.get("wdl_es_loss", []))),
            "volatility_wdl_mean": mean(player_moves.get("wdl_volatility_swing", [])),
            "volatility_wdl_sd": pstdev(player_moves.get("wdl_volatility_swing", [])),
            "total_volatility_wdl": sum(clean_values(player_moves.get("wdl_volatility_swing", []))),
            "hard_rap_sum": aggregate(player_games.get("hard_rap", []), "sum"),
            "hard_rap_mean": mean(player_games.get("hard_rap", [])),
            "hard_rap_sd": pstdev(player_games.get("hard_rap", [])),
            "soft_rap_sum": aggregate(player_games.get("soft_rap", []), "sum"),
            "soft_rap_mean": mean(player_games.get("soft_rap", [])),
            "soft_rap_sd": pstdev(player_games.get("soft_rap", [])),
        }
        if "position_difficulty_pure" in player_moves.columns:
            caused_moves = per_move_named[per_move_named.get("difficulty_caused_by_player") == player] if "difficulty_caused_by_player" in per_move_named.columns else pd.DataFrame()
            for variant in DIFFICULTY_VARIANTS:
                dcol = f"position_difficulty_{variant}"
                if dcol in player_moves.columns:
                    row[f"difficulty_{variant}_faced_mean"] = mean(player_moves[dcol])
                    row[f"difficulty_{variant}_faced_sd"] = pstdev(player_moves[dcol])
                    row[f"difficulty_{variant}_faced_sum"] = sum(clean_values(player_moves[dcol]))
                    wl = weighted_loss_from_moves(player_moves, dcol)
                    row[f"difficulty_{variant}_weighted_es_loss"] = wl
                    row[f"difficulty_{variant}_weighted_accuracy"] = None if wl is None else 100.0 * (1.0 - wl)
                if not caused_moves.empty and dcol in caused_moves.columns:
                    row[f"difficulty_{variant}_caused_mean"] = mean(caused_moves[dcol])
                    row[f"difficulty_{variant}_caused_sd"] = pstdev(caused_moves[dcol])
                    row[f"difficulty_{variant}_caused_sum"] = sum(clean_values(caused_moves[dcol]))
            for col in ["legal_rms_loss", "narrowness", "effective_good_moves", "legal_loss_swing", "best_second_gap", "best_third_gap"]:
                if col in player_moves.columns:
                    row[f"{col}_faced_mean"] = mean(player_moves[col])
                    row[f"{col}_faced_sd"] = pstdev(player_moves[col])
                if not caused_moves.empty and col in caused_moves.columns:
                    row[f"{col}_caused_mean"] = mean(caused_moves[col])
                    row[f"{col}_caused_sd"] = pstdev(caused_moves[col])
        if "ccp_search_difficulty_pure" in player_moves.columns:
            caused_moves_ccp = per_move_named[per_move_named.get("difficulty_caused_by_player") == player] if "difficulty_caused_by_player" in per_move_named.columns else pd.DataFrame()
            for col in CCP_MOVE_COL_MAP.values():
                if col in player_moves.columns:
                    row[f"{col}_faced_mean"] = mean(player_moves[col])
                    row[f"{col}_faced_sd"] = pstdev(player_moves[col])
                    row[f"{col}_faced_sum"] = sum(clean_values(player_moves[col]))
                if not caused_moves_ccp.empty and col in caused_moves_ccp.columns:
                    row[f"{col}_caused_mean"] = mean(caused_moves_ccp[col])
                    row[f"{col}_caused_sd"] = pstdev(caused_moves_ccp[col])
                    row[f"{col}_caused_sum"] = sum(clean_values(caused_moves_ccp[col]))
            for ccp_variant in CCP_SEARCH_VARIANTS:
                if ccp_variant in player_moves.columns:
                    wl = weighted_loss_from_moves(player_moves, ccp_variant)
                    row[f"{ccp_variant}_weighted_es_loss"] = wl
                    row[f"{ccp_variant}_weighted_accuracy"] = None if wl is None else 100.0 * (1.0 - wl)

        # DPQ / Pressure Yield family. These are match-length-neutral,
        # continuous derived pressure metrics. They are calculated for a
        # selected set of real pressure/difficulty scales, not workload controls.
        for base, _label, col in available_pressure_metric_specs(per_move_named):
            row[f"{base}_caused_share"] = pressure_caused_share(per_move_named, col, player)
            row[f"{base}_dpq"] = difficulty_pressure_quality(per_move_named, col, player)
            row[f"{base}_pressure_yield_suffered"] = pressure_yield_suffered(per_move_named, col, player)
            row[f"{base}_pressure_yield_caused"] = pressure_yield_caused(per_move_named, col, player)
        rows.append(row)

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["score_sum", "accuracy_wdl_mean"], ascending=[False, False])
    return out


def build_metric_specs(has_difficulty: bool, has_ccp: bool = False) -> List[Tuple[str, str, str, str]]:
    specs: List[Tuple[str, str, str, str]] = [
        ("score", "Score", "Actual match score. SD is calculated from game-by-game scores.", "sum"),
        ("expected_score", "Expected Score", "Total WDL expected match score. SD is calculated from game-by-game expected scores.", "sum"),
        ("conversion", "Conversion", "Total Score minus total Expected Score. SD is calculated from game-by-game conversion.", "sum"),
        ("accuracy_wdl", "WDL Accuracy", "Move accuracy = 100 × (1 − WDL expected-score loss).", "mean"),
        ("pq_wdl", "Performance Quality", "WDL Accuracy weighted by Game Accuracy.", "mean"),
        ("dominance_wdl", "Dominance", "Accuracy gap versus opponent.", "mean"),
        ("mean_es_loss", "Mean ES Loss", "Average WDL expected-score loss per move.", "mean"),
        ("rms_es_loss", "RMS ES Loss", "Root mean square of WDL expected-score losses.", "rms"),
        ("error_concentration", "Error Concentration", "RMS ES Loss divided by Mean ES Loss.", "mean"),
        ("volatility_wdl", "WDL Volatility", "Absolute WDL expected-score swing per move.", "mean"),
        ("total_volatility_wdl", "Total WDL Volatility", "Total absolute WDL expected-score movement over the match. SD is calculated from game totals.", "sum"),
        ("hard_rap", "Hard RAP", "Total HardRAP over the match. SD is calculated from game HardRAP values.", "sum"),
        ("soft_rap", "Soft RAP", "Total SoftRAP over the match. SD is calculated from game SoftRAP values.", "sum"),
    ]
    if has_difficulty:
        exposure_specs = [
            ("difficulty_pure", "Pure Position Difficulty", "Narrowness × sqrt(legal RMS loss), calculated from all legal moves."),
            ("difficulty_uncertainty", "Uncertainty-Leveraged Difficulty", "Pure difficulty × 4B(1−B)."),
            ("difficulty_soft_uncertainty", "Soft-Uncertainty Difficulty", "Pure difficulty × sqrt(4B(1−B)). Main practical difficulty candidate."),
            ("difficulty_risk", "Risk-Leveraged Difficulty", "Pure difficulty × side-to-move remaining risk (1−B)."),
            ("difficulty_defender_pressure", "Defender-Pressure Difficulty", "Pure difficulty × defender/opponent pressure leverage B."),
            ("difficulty_swing", "Swing-Leveraged Difficulty", "Pure difficulty × legal ES swing."),
            ("legal_rms_loss", "Legal RMS Loss", "RMS of best-move ES minus each legal move's ES. Higher = wrong moves are more costly."),
            ("narrowness", "Narrowness", "Softmax effective-good-move narrowness. Higher = fewer effective good moves."),
            ("effective_good_moves", "Effective Good Moves", "Inverse-Simpson effective number of good moves. Lower = narrower/more selective."),
            ("legal_loss_swing", "Legal Loss Swing", "Best legal ES minus worst legal ES for the side to move. Higher = larger possible result swing."),
            ("best_second_gap", "Best-Second Gap", "ES gap between best and second-best legal move. Higher = more decisive top choice."),
            ("best_third_gap", "Best-Third Gap", "ES gap between best and third-best legal move. Higher = top choice separates from alternatives."),
        ]
        for key, label, definition in exposure_specs:
            specs.append((f"{key}_faced", f"{label} Faced", definition + " This is measured before the player's own move.", "mean"))
            specs.append((f"{key}_caused", f"{label} Caused", definition + " This is attributed to the previous mover as immediate opponent difficulty caused.", "mean"))
        for variant in DIFFICULTY_VARIANTS:
            pretty = variant.replace("_", " ").title()
            base = f"difficulty_{variant}"
            specs.append((f"total_{base}_faced", f"Total {pretty} Difficulty Faced", f"Sum of position_difficulty_{variant} over the player's own moves.", "sum"))
            specs.append((f"total_{base}_caused", f"Total {pretty} Difficulty Caused", f"Sum of position_difficulty_{variant} over positions immediately caused for the opponent by the player's previous moves.", "sum"))
        for variant in DIFFICULTY_VARIANTS:
            pretty = variant.replace("_", " ").title()
            specs += [
                (f"difficulty_{variant}_weighted_es_loss", f"{pretty} Faced Difficulty-Weighted ES Loss", f"Player's ES loss weighted by position_difficulty_{variant} faced before the player's own moves; lower is better.", "mean"),
                (f"difficulty_{variant}_weighted_accuracy", f"{pretty} Faced Difficulty-Weighted Accuracy", f"100 × (1 − faced difficulty-weighted ES loss) using position_difficulty_{variant}; higher is better.", "mean"),
            ]
    if has_ccp:
        ccp_exposure_specs = [
            ("ccp_search_difficulty_pure", "CCP Search Difficulty", "Checks/Captures/Promotions forcing-search burden: total CCP burden × candidate ambiguity."),
            ("ccp_search_difficulty_soft", "CCP Soft Search Difficulty", "CCP Search Difficulty × sqrt(4B(1−B)); result-sensitive CCP burden."),
            ("ccp_immediate_burden", "CCP Immediate Burden", "Weighted burden of immediate checks, captures, and promotions."),
            ("ccp_quiet_to_ccp_burden", "CCP Quiet-to-CCP Burden", "Version-1 proxy for quiet moves that create later CCP pressure."),
            ("ccp_total_burden", "CCP Total Burden", "Immediate CCP burden plus quiet-to-CCP burden."),
            ("ccp_candidate_effective_count", "CCP Candidate Effective Count", "Effective number of plausible forcing candidates; higher usually means more candidate ambiguity."),
            ("ccp_candidate_ambiguity", "CCP Candidate Ambiguity", "log(1 + effective CCP candidate count)."),
            ("ccp_legal_check_count", "CCP Legal Check Count", "Number of legal checking moves."),
            ("ccp_legal_capture_count", "CCP Legal Capture Count", "Number of legal capture moves."),
            ("ccp_legal_promotion_count", "CCP Legal Promotion Count", "Number of legal promotion moves."),
            ("ccp_legal_immediate_count", "CCP Legal Immediate Count", "Number of legal checks, captures, or promotions."),
            ("ccp_attacked_material_value", "CCP Attacked Material Value", "Total basic material value of side-to-move material currently attacked."),
            ("ccp_highest_attacked_piece_value", "CCP Highest Attacked Piece Value", "Highest basic material value of side-to-move material currently attacked."),
            ("ccp_attacked_material_count", "CCP Attacked Material Count", "Count of side-to-move pieces/pawns currently attacked."),
            ("ccp_v2_search_difficulty_pure", "CCP v2 Search Difficulty", "Recursive CCP candidate-tree difficulty: branch total × branch ambiguity."),
            ("ccp_v2_search_difficulty_soft", "CCP v2 Soft Search Difficulty", "CCP v2 Search Difficulty × sqrt(4B(1−B)); result-sensitive recursive CCP difficulty."),
            ("ccp_v2_log_search_difficulty_pure", "CCP v2 Log Search Difficulty", "log1p-scaled recursive CCP-v2 pure difficulty; useful for stable comparison when raw tree mass is huge."),
            ("ccp_v2_log_search_difficulty_soft", "CCP v2 Log Soft Search Difficulty", "log1p-scaled CCP-v2 soft difficulty; recommended companion scale for reports and cross-parameter checks."),
            ("ccp_v2_log_branch_total", "CCP v2 Log Branch Total", "log1p-scaled CCP-v2 branch total."),
            ("ccp_v2_nodes_searched", "CCP v2 Expanded Positions", "Number of candidate-tree positions expanded for CCP v2."),
            ("ccp_v2_leaf_count", "CCP v2 Leaf Count", "Number of terminal/leaf nodes reached in the CCP v2 tree."),
            ("ccp_v2_max_chain_length", "CCP v2 Max Chain Length", "Maximum check/capture/promotion chain length found in the candidate tree."),
            ("ccp_v2_mean_chain_length", "CCP v2 Mean Chain Length", "Mean chain length proxy across CCP v2 leaves."),
            ("ccp_v2_quiet_pause_count", "CCP v2 Quiet Pause Count", "Number of quiet moves inside/delaying forcing CCP continuations."),
            ("ccp_v2_quiet_pause_burden", "CCP v2 Quiet Pause Burden", "Delayed-payoff burden contributed by quiet pauses before later CCP continuations."),
            ("ccp_v2_branch_total", "CCP v2 Branch Total", "Total scored branch burden in the recursive CCP candidate tree."),
            ("ccp_v2_branch_max", "CCP v2 Branch Max", "Highest single branch score in the recursive CCP candidate tree."),
            ("ccp_v2_branch_mean", "CCP v2 Branch Mean", "Mean positive branch score in the recursive CCP candidate tree."),
            ("ccp_v2_branch_effective_count", "CCP v2 Branch Effective Count", "Effective number of serious CCP-v2 branches."),
            ("ccp_v2_branch_ambiguity", "CCP v2 Branch Ambiguity", "log(1 + effective CCP-v2 branch count)."),
            ("ccp_v2_eval_attempts", "CCP v2 Confirm Eval Attempts", "Number of confirmation-stage CCP-v2 evaluation attempts at this root; in one-stage runs this is the normal CCP-v2 eval count."),
            ("ccp_v2_cap_hit", "CCP v2 Confirm Cap Hit", "1 if the confirmation/normal CCP-v2 evaluation cap was reached at this root."),
            ("ccp_v2_probe_nodes_searched", "CCP v2 Probe Expanded Positions", "Number of probe-stage candidate-tree positions expanded."),
            ("ccp_v2_probe_eval_attempts", "CCP v2 Probe Eval Attempts", "Number of probe-stage evaluation attempts at this root."),
            ("ccp_v2_probe_cap_hit", "CCP v2 Probe Cap Hit", "1 if the probe-stage evaluation cap was reached at this root."),
            ("ccp_v2_probe_root_branch_count", "CCP v2 Probe Root Branch Count", "Number of root branches found by the probe before confirmation selection."),
            ("ccp_v2_confirm_root_moves_selected", "CCP v2 Confirm Root Moves Selected", "Number of root moves selected from the probe for high-budget confirmation."),
            ("ccp_v2_confirm_share_of_probe_branches", "CCP v2 Confirm Share of Probe Branches", "Confirmed root moves divided by probed root branch count."),
            ("ccp_v2_total_two_stage_eval_attempts", "CCP v2 Total Two-Stage Eval Attempts", "Probe plus confirmation evaluation attempts at this root."),
            ("ccp_v2_probe_log_branch_total", "CCP v2 Probe Log Branch Total", "log1p-scaled probe-stage branch total used as a diagnostic companion to confirmed log branch total."),
        ]
        for key, label, definition in ccp_exposure_specs:
            specs.append((f"{key}_faced", f"{label} Faced", definition + " This is measured before the player's own move.", "mean"))
            specs.append((f"{key}_caused", f"{label} Caused", definition + " This is attributed to the previous mover as immediate opponent CCP pressure caused.", "mean"))
        for ccp_variant in CCP_SEARCH_VARIANTS:
            pretty = ccp_variant.replace("_", " ").upper() if ccp_variant == "ccp" else ccp_variant.replace("_", " ").title()
            specs.append((f"total_{ccp_variant}_faced", f"Total {pretty} Faced", f"Sum of {ccp_variant} over the player's own moves.", "sum"))
            specs.append((f"total_{ccp_variant}_caused", f"Total {pretty} Caused", f"Sum of {ccp_variant} over positions immediately caused for the opponent by the player's previous moves.", "sum"))
            specs.append((f"{ccp_variant}_weighted_es_loss", f"{pretty} Weighted ES Loss", f"Player's ES loss weighted by {ccp_variant} faced before the player's own moves; lower is better.", "mean"))
            specs.append((f"{ccp_variant}_weighted_accuracy", f"{pretty} Weighted Accuracy", f"100 × (1 − CCP-weighted ES loss) using {ccp_variant}; higher is better.", "mean"))
    # Derived pressure metrics: match-pressure share, DPQ, and continuous
    # pressure-yield formulas. These appropriate the WDL/PQ idea to the
    # post-WDL difficulty layer without requiring analyzer changes.
    for key, label, definition_col in PRESSURE_METRIC_SPECS:
        if key.startswith("difficulty_") and not has_difficulty:
            continue
        if key.startswith("ccp_") and not has_ccp:
            continue
        specs.append((
            f"{key}_caused_share",
            f"{label} Caused Share",
            f"Player's share of total match {label} caused. Style/asymmetry metric; not automatically better.",
            "mean",
        ))
        specs.append((
            f"{key}_dpq",
            f"{label} Difficulty Pressure Quality (DPQ)",
            f"DPQ = player's mean {label} caused × match mean {label} caused. Higher means more pressure caused in a higher-pressure match.",
            "mean",
        ))
        specs.append((
            f"{key}_pressure_yield_suffered",
            f"{label} Pressure Yield Suffered",
            f"Player's WDL ES loss weighted by {label} faced on the player's own moves. This is a continuous difficulty-weighted ES-loss measure; lower is better.",
            "mean",
        ))
        specs.append((
            f"{key}_pressure_yield_caused",
            f"{label} Pressure Yield Caused",
            f"Opponent WDL ES loss weighted by {label} immediately caused by this player. Continuous pressure-conversion measure; higher means the opponent yielded more under this player's pressure.",
            "mean",
        ))
    return specs


def build_all_metrics_3source(per_game: pd.DataFrame, per_move_named: pd.DataFrame, player_summary: pd.DataFrame, player_order: Optional[List[str]] = None) -> pd.DataFrame:
    player_games = build_player_game_rows(per_game)
    player_A, player_B = choose_two_players(player_summary, player_order)
    has_difficulty = "position_difficulty_pure" in per_move_named.columns
    has_ccp = "ccp_search_difficulty_pure" in per_move_named.columns

    rows: List[Dict[str, Any]] = []
    for key, label, definition, mode in build_metric_specs(has_difficulty, has_ccp):
        vals_A = values_for_metric(player_A, per_move_named, player_games, key)
        vals_B = values_for_metric(player_B, per_move_named, player_games, key)

        value_A = aggregate_value_for_metric(player_A, per_move_named, player_games, key, mode)
        value_B = aggregate_value_for_metric(player_B, per_move_named, player_games, key, mode)

        base_share = pressure_metric_base_from_key(key, "_caused_share")
        base_dpq = pressure_metric_base_from_key(key, "_dpq")
        base_pys = pressure_metric_base_from_key(key, "_pressure_yield_suffered")
        base_pyc = pressure_metric_base_from_key(key, "_pressure_yield_caused")

        if base_share is not None:
            both_value = 1.0
            both_sd = None
        elif base_dpq is not None:
            both_value = mean([value_A, value_B])
            both_sd = None
        elif base_pys is not None:
            col = pressure_metric_col_map()[base_pys]
            both_value = weighted_loss_from_moves(per_move_named, col)
            both_sd = None
        elif base_pyc is not None:
            col = pressure_metric_col_map()[base_pyc]
            rows_caused = per_move_named[per_move_named["difficulty_caused_by_player"].notna()] if "difficulty_caused_by_player" in per_move_named.columns else per_move_named
            both_value = weighted_loss_from_moves(rows_caused, col)
            both_sd = None
        elif key in {"score", "expected_score", "conversion"}:
            both_per_game = []
            source_col = key
            for _, g in player_games.groupby("game_id"):
                both_per_game.append(g[source_col].sum())
            both_value = sum(clean_values(both_per_game))
            both_sd = pstdev(both_per_game)
        elif key in {"hard_rap", "soft_rap", "total_volatility_wdl"} or key.startswith("total_difficulty_"):
            both_per_game = []
            for _, g in player_games.groupby("game_id"):
                if key in g.columns:
                    both_per_game.append(g[key].sum())
            both_value = sum(clean_values(both_per_game)) if clean_values(both_per_game) else None
            both_sd = pstdev(both_per_game)
        elif key.startswith("ccp_search_difficulty_") and (key.endswith("_weighted_es_loss") or key.endswith("_weighted_accuracy")):
            if key.endswith("_weighted_es_loss"):
                ccp_variant = key.replace("_weighted_es_loss", "")
                loss = weighted_loss_from_moves(per_move_named, ccp_variant)
                both_value = loss
            else:
                ccp_variant = key.replace("_weighted_accuracy", "")
                loss = weighted_loss_from_moves(per_move_named, ccp_variant)
                both_value = None if loss is None else 100.0 * (1.0 - loss)
            game_col = f"{key}_game"
            both_sd = pstdev(per_game[game_col]) if game_col in per_game.columns else None
        elif key.endswith("_weighted_es_loss") or key.endswith("_weighted_accuracy"):
            if key.endswith("_weighted_es_loss"):
                variant = key.replace("difficulty_", "").replace("_weighted_es_loss", "")
                loss = weighted_loss_from_moves(per_move_named, f"position_difficulty_{variant}")
                both_value = loss
            else:
                variant = key.replace("difficulty_", "").replace("_weighted_accuracy", "")
                loss = weighted_loss_from_moves(per_move_named, f"position_difficulty_{variant}")
                both_value = None if loss is None else 100.0 * (1.0 - loss)
            game_col = f"{key}_game"
            both_sd = pstdev(per_game[game_col]) if game_col in per_game.columns else None
        else:
            vals_both = clean_values(vals_A) + clean_values(vals_B)
            both_value = aggregate(vals_both, mode)
            both_sd = pstdev(vals_both)

        rows.append({
            "metric_key": key,
            "metric": label,
            "definition": definition,
            "aggregation": mode,
            "direction": metric_direction(key),
            "player_A_name": player_A,
            "player_A_value": value_A,
            "player_A_sd": pstdev(vals_A),
            "player_B_name": player_B,
            "player_B_value": value_B,
            "player_B_sd": pstdev(vals_B),
            "both_players_value": both_value,
            "both_players_sd": both_sd,
        })

    game_specs = [
        ("game_accuracy_wdl", "Game Accuracy", "Average WDL Accuracy of both players."),
        ("mutual_accuracy_wdl", "Mutual Accuracy", "Strict two-sided accuracy: Accuracy(A) × Accuracy(B) / 100."),
        ("volatility_game_wdl", "Game WDL Volatility", "Average WDL volatility across both players."),
        ("total_volatility_game_wdl", "Game Total WDL Volatility", "Total WDL volatility across the game."),
        ("mean_es_loss_game", "Game Mean ES Loss", "Average expected-score loss across both players."),
        ("es_loss_sd_game", "Game ES Loss SD", "Within-game SD of expected-score losses."),
        ("rms_es_loss_game", "Game RMS ES Loss", "RMS expected-score loss across both players."),
        ("error_concentration_game", "Game Error Concentration", "Game RMS ES Loss / Game Mean ES Loss."),
        ("hard_rap_game", "Game HardRAP", "HardRAP(A)+HardRAP(B)."),
        ("soft_rap_game", "Game SoftRAP", "SoftRAP(A)+SoftRAP(B)."),
        ("conversion_game", "Game Conversion Magnitude", "|Conversion(A)|+|Conversion(B)."),
    ]
    if has_difficulty:
        game_specs += [
            (f"mean_difficulty_{v}_game", f"Game Mean {v.replace('_',' ').title()} Difficulty", f"Average position_difficulty_{v} across both players.")
            for v in DIFFICULTY_VARIANTS
        ]
        game_specs += [
            (f"difficulty_{v}_weighted_accuracy_game", f"Game {v.replace('_',' ').title()} Difficulty-Weighted Accuracy", f"Game-level difficulty-weighted accuracy using position_difficulty_{v}.")
            for v in DIFFICULTY_VARIANTS
        ]
        game_specs += [
            ("mean_legal_rms_loss_game", "Game Mean Legal RMS Loss", "Average legal RMS loss across both players."),
            ("mean_narrowness_game", "Game Mean Narrowness", "Average legal-move narrowness across both players."),
            ("mean_effective_good_moves_game", "Game Mean Effective Good Moves", "Average effective good moves across both players."),
        ]
    if has_ccp:
        game_specs += [
            ("mean_ccp_search_difficulty_pure_game", "Game Mean CCP Search Difficulty", "Average CCP Search Difficulty across both players."),
            ("mean_ccp_search_difficulty_soft_game", "Game Mean CCP Soft Search Difficulty", "Average result-sensitive CCP Search Difficulty across both players."),
            ("ccp_search_difficulty_pure_weighted_accuracy_game", "Game CCP Search Difficulty-Weighted Accuracy", "Game-level accuracy weighted by CCP Search Difficulty."),
            ("ccp_search_difficulty_soft_weighted_accuracy_game", "Game CCP Soft Search Difficulty-Weighted Accuracy", "Game-level accuracy weighted by CCP Soft Search Difficulty."),
            ("mean_ccp_immediate_burden_game", "Game Mean CCP Immediate Burden", "Average immediate CCP burden across both players."),
            ("mean_ccp_quiet_to_ccp_burden_game", "Game Mean CCP Quiet-to-CCP Burden", "Average quiet-to-CCP burden across both players."),
            ("mean_ccp_candidate_effective_count_game", "Game Mean CCP Candidate Effective Count", "Average effective forcing candidate count across both players."),
            ("mean_ccp_v2_search_difficulty_pure_game", "Game Mean CCP v2 Search Difficulty", "Average recursive CCP-v2 search difficulty across both players."),
            ("mean_ccp_v2_search_difficulty_soft_game", "Game Mean CCP v2 Soft Search Difficulty", "Average result-sensitive recursive CCP-v2 search difficulty across both players."),
            ("ccp_v2_search_difficulty_pure_weighted_accuracy_game", "Game CCP v2 Search Difficulty-Weighted Accuracy", "Game-level accuracy weighted by CCP v2 Search Difficulty."),
            ("ccp_v2_search_difficulty_soft_weighted_accuracy_game", "Game CCP v2 Soft Search Difficulty-Weighted Accuracy", "Game-level accuracy weighted by CCP v2 Soft Search Difficulty."),
            ("mean_ccp_v2_log_search_difficulty_pure_game", "Game Mean CCP v2 Log Search Difficulty", "Average log1p-scaled CCP-v2 pure difficulty across both players."),
            ("mean_ccp_v2_log_search_difficulty_soft_game", "Game Mean CCP v2 Log Soft Search Difficulty", "Average log1p-scaled CCP-v2 soft difficulty across both players."),
            ("ccp_v2_log_search_difficulty_pure_weighted_accuracy_game", "Game CCP v2 Log Search Difficulty-Weighted Accuracy", "Game-level accuracy weighted by log1p CCP v2 Search Difficulty."),
            ("ccp_v2_log_search_difficulty_soft_weighted_accuracy_game", "Game CCP v2 Log Soft Search Difficulty-Weighted Accuracy", "Game-level accuracy weighted by log1p CCP v2 Soft Search Difficulty."),
            ("mean_ccp_v2_max_chain_length_game", "Game Mean CCP v2 Max Chain Length", "Average maximum CCP chain length across both players."),
            ("mean_ccp_v2_quiet_pause_burden_game", "Game Mean CCP v2 Quiet Pause Burden", "Average CCP-v2 quiet-pause burden across both players."),
            ("mean_ccp_v2_branch_total_game", "Game Mean CCP v2 Branch Total", "Average CCP-v2 branch total across both players."),
            ("mean_ccp_v2_branch_effective_count_game", "Game Mean CCP v2 Branch Effective Count", "Average effective number of serious CCP-v2 branches across both players."),
        ]

    for key, label, definition in game_specs:
        if key in per_game.columns:
            vals = per_game[key].tolist()
        else:
            vals = []
        rows.append({
            "metric_key": key,
            "metric": label,
            "definition": definition,
            "aggregation": "mean",
            "direction": metric_direction(key),
            "player_A_name": player_A,
            "player_A_value": None,
            "player_A_sd": None,
            "player_B_name": player_B,
            "player_B_value": None,
            "player_B_sd": None,
            "both_players_value": mean(vals),
            "both_players_sd": pstdev(vals),
        })

    return pd.DataFrame(rows)


def make_metric_ratios(all_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, r in all_metrics.iterrows():
        metric_key = r.get("metric_key", "")
        metric = r.get("metric", "")
        player_A = r.get("player_A_name", "Player A")
        player_B = r.get("player_B_name", "Player B")
        value_A = r.get("player_A_value")
        value_B = r.get("player_B_value")
        sd_A = r.get("player_A_sd")
        sd_B = r.get("player_B_sd")
        rows.append({
            "metric_key": metric_key,
            "metric": metric,
            "direction": metric_direction(metric_key),
            "player_A_name": player_A,
            "player_A_value": value_A,
            "player_A_sd": sd_A,
            "player_B_name": player_B,
            "player_B_value": value_B,
            "player_B_sd": sd_B,
            "both_players_value": r.get("both_players_value"),
            "both_players_sd": r.get("both_players_sd"),
            "value_A_over_B": safe_ratio(value_A, value_B),
            "value_B_over_A": safe_ratio(value_B, value_A),
            "value_difference_A_minus_B": diff(value_A, value_B),
            "value_difference_B_minus_A": diff(value_B, value_A),
            "percent_advantage_A_vs_B": pct_advantage(value_A, value_B),
            "percent_advantage_B_vs_A": pct_advantage(value_B, value_A),
            "sd_A_over_B": safe_ratio(sd_A, sd_B),
            "sd_B_over_A": safe_ratio(sd_B, sd_A),
            "sd_difference_A_minus_B": diff(sd_A, sd_B),
            "sd_difference_B_minus_A": diff(sd_B, sd_A),
            "better_player_by_direction": better_player(metric_key, player_A, value_A, player_B, value_B),
            "interpretation_warning": warning_for_metric(metric_key, value_A, value_B),
        })
    return pd.DataFrame(rows)


def build_game_summary(per_game: pd.DataFrame) -> pd.DataFrame:
    cols_map: Dict[str, str] = {
        "game_id": "game_id", "white": "white", "black": "black", "result": "result", "plies": "plies",
        "accuracy_A_wdl": "accuracy_white", "accuracy_B_wdl": "accuracy_black",
        "accuracy_sd_A_wdl": "accuracy_white_sd", "accuracy_sd_B_wdl": "accuracy_black_sd",
        "game_accuracy_wdl": "game_accuracy", "mutual_accuracy_wdl": "mutual_accuracy",
        "pq_A_wdl": "pq_white", "pq_B_wdl": "pq_black",
        "dominance_A_wdl": "dominance_white", "dominance_B_wdl": "dominance_black",
        "mean_es_loss_A": "mean_es_loss_white", "mean_es_loss_B": "mean_es_loss_black", "mean_es_loss_game": "mean_es_loss_game",
        "rms_es_loss_A": "rms_es_loss_white", "rms_es_loss_B": "rms_es_loss_black", "rms_es_loss_game": "rms_es_loss_game",
        "volatility_A_wdl": "volatility_white", "volatility_B_wdl": "volatility_black", "volatility_game_wdl": "volatility_game",
        "total_volatility_game_wdl": "total_volatility_game",
        "expected_score_A": "expected_score_white", "expected_score_B": "expected_score_black",
        "conversion_A": "conversion_white", "conversion_B": "conversion_black", "conversion_game": "conversion_game",
    }
    # Difficulty summaries: include all per-game analyzer columns with clear names.
    for variant in DIFFICULTY_VARIANTS:
        pretty = variant
        for suffix, side in [("A", "white"), ("B", "black"), ("game", "game")]:
            for stem in ["mean_difficulty", "sd_difficulty", "total_difficulty"]:
                src = f"{stem}_{variant}_{suffix}"
                dst = f"{stem}_{pretty}_{side}"
                cols_map[src] = dst
            for stem in ["difficulty"]:
                src_loss = f"difficulty_{variant}_weighted_es_loss_{suffix}"
                src_acc = f"difficulty_{variant}_weighted_accuracy_{suffix}"
                cols_map[src_loss] = f"difficulty_{pretty}_weighted_es_loss_{side}"
                cols_map[src_acc] = f"difficulty_{pretty}_weighted_accuracy_{side}"
    for base in ["legal_rms_loss", "narrowness", "effective_good_moves"]:
        for suffix, side in [("A", "white"), ("B", "black"), ("game", "game")]:
            cols_map[f"mean_{base}_{suffix}"] = f"mean_{base}_{side}"
            cols_map[f"sd_{base}_{suffix}"] = f"sd_{base}_{side}"
    for base in ["ccp_search_difficulty_pure", "ccp_search_difficulty_soft", "ccp_immediate_burden", "ccp_quiet_to_ccp_burden", "ccp_candidate_effective_count",
                 "ccp_v2_search_difficulty_pure", "ccp_v2_search_difficulty_soft",
                 "ccp_v2_log_search_difficulty_pure", "ccp_v2_log_search_difficulty_soft", "ccp_v2_log_branch_total",
                 "ccp_v2_nodes_searched", "ccp_v2_leaf_count",
                 "ccp_v2_max_chain_length", "ccp_v2_mean_chain_length", "ccp_v2_quiet_pause_count", "ccp_v2_quiet_pause_burden",
                 "ccp_v2_branch_total", "ccp_v2_branch_effective_count", "ccp_v2_branch_ambiguity",
                 "ccp_v2_eval_attempts", "ccp_v2_probe_eval_attempts", "ccp_v2_total_two_stage_eval_attempts",
                 "ccp_v2_probe_nodes_searched", "ccp_v2_probe_root_branch_count", "ccp_v2_confirm_root_moves_selected",
                 "ccp_v2_confirm_share_of_probe_branches", "ccp_v2_probe_log_branch_total"]:
        for suffix, side in [("A", "white"), ("B", "black"), ("game", "game")]:
            cols_map[f"mean_{base}_{suffix}"] = f"mean_{base}_{side}"
            cols_map[f"sd_{base}_{suffix}"] = f"sd_{base}_{side}"
    for ccp_variant in CCP_SEARCH_VARIANTS:
        for suffix, side in [("A", "white"), ("B", "black"), ("game", "game")]:
            cols_map[f"total_{ccp_variant}_{suffix}"] = f"total_{ccp_variant}_{side}"
            cols_map[f"{ccp_variant}_weighted_es_loss_{suffix}"] = f"{ccp_variant}_weighted_es_loss_{side}"
            cols_map[f"{ccp_variant}_weighted_accuracy_{suffix}"] = f"{ccp_variant}_weighted_accuracy_{side}"

    data = {new: per_game[old] for old, new in cols_map.items() if old in per_game.columns}
    return pd.DataFrame(data)



def select_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    return df[[c for c in cols if c in df.columns]].copy()


# ---------------------------------------------------------------------
# CCP-v2 root-branch diagnostics (v3.6+ optional input)
# ---------------------------------------------------------------------

def truthy_value(x: Any) -> bool:
    if x is None:
        return False
    try:
        if pd.isna(x):
            return False
    except Exception:
        pass
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "t"}


def add_root_branch_derived(root_branches: pd.DataFrame) -> pd.DataFrame:
    """Normalize v3.6 root-branch diagnostics and add safe derived fields.

    Idempotent: callers may safely pass an already-normalized DataFrame.
    This matters for long matches where root-branch diagnostics can contain
    tens of thousands of rows and repeated coercion becomes expensive.
    """
    if {"root_played_move_numeric", "branch_score_log"}.issubset(root_branches.columns):
        return root_branches.copy()
    df = root_branches.copy()

    numeric_cols = [
        "game_id", "ply", "move_no", "stage_rank", "probe_rank", "confirm_rank",
        "probe_root_branch_count", "confirm_root_moves_selected",
        "quiet_attack_proxy", "quiet_vision_proxy", "quiet_proxy",
        "es_node_mover", "es_after_mover", "es_delta_from_node", "local_best_es",
        "local_loss_vs_best", "gain", "pre_loss", "plausibility", "immediate_value",
        "delayed_payoff", "best_descendant_es_for_root_mover", "payoff_depth",
        "branch_core", "branch_chain", "branch_total_chain", "quiet_pause",
        "quiet_pause_burden", "child_nodes_searched", "child_leaf_count",
        "child_max_chain_length", "child_quiet_pause_count", "child_quiet_pause_burden",
        "child_branch_total", "branch_score", "branch_score_log", "confirm_priority",
        "wdl_es_loss", "wdl_move_accuracy", "es_best_before_mover", "es_after_played_mover",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    bool_cols = [
        "root_played_move", "is_ccp", "is_check", "is_capture", "is_promotion",
        "is_recapture", "captures_attacker", "saves_material", "forced_inclusion",
        "has_positive_payoff", "branch_has_ccp", "selected_for_confirm",
    ]
    for col in bool_cols:
        if col in df.columns:
            df[f"{col}_numeric"] = df[col].map(lambda x: 1.0 if truthy_value(x) else 0.0)

    if "branch_score_log" not in df.columns and "branch_score" in df.columns:
        df["branch_score_log"] = df["branch_score"].map(log1p_nonnegative_value)
    if "child_branch_total_log" not in df.columns and "child_branch_total" in df.columns:
        df["child_branch_total_log"] = df["child_branch_total"].map(log1p_nonnegative_value)
    if "delayed_payoff_log" not in df.columns and "delayed_payoff" in df.columns:
        df["delayed_payoff_log"] = df["delayed_payoff"].map(log1p_nonnegative_value)

    return df


def root_branch_stage_summary(root_branches: pd.DataFrame) -> pd.DataFrame:
    """Summarize root-branch diagnostics by all/stage/player/stage.

    Rows are workload and search-shape diagnostics. They are not playing-strength
    metrics by themselves.
    """
    if root_branches is None or root_branches.empty:
        return pd.DataFrame()
    df = add_root_branch_derived(root_branches)

    def summarize(scope: str, g: pd.DataFrame) -> Dict[str, Any]:
        if g.empty:
            return {"scope": scope, "rows": 0}
        unique_plies = g[["game_id", "ply"]].drop_duplicates().shape[0] if {"game_id", "ply"}.issubset(g.columns) else None
        rows = len(g)
        out: Dict[str, Any] = {
            "scope": scope,
            "rows": rows,
            "unique_plies": unique_plies,
            "branches_per_ply": (rows / unique_plies) if unique_plies else None,
            "mean_branch_score_log": mean(g.get("branch_score_log", [])),
            "mean_branch_score": mean(g.get("branch_score", [])),
            "mean_child_nodes_searched": mean(g.get("child_nodes_searched", [])),
            "mean_child_leaf_count": mean(g.get("child_leaf_count", [])),
            "mean_child_max_chain_length": mean(g.get("child_max_chain_length", [])),
            "mean_child_quiet_pause_burden": mean(g.get("child_quiet_pause_burden", [])),
            "mean_quiet_pause_burden": mean(g.get("quiet_pause_burden", [])),
            "mean_delayed_payoff": mean(g.get("delayed_payoff", [])),
            "mean_payoff_depth": mean(g.get("payoff_depth", [])),
            "mean_local_loss_vs_best": mean(g.get("local_loss_vs_best", [])),
            "mean_plausibility": mean(g.get("plausibility", [])),
            "positive_payoff_rate": mean(g.get("has_positive_payoff_numeric", [])),
            "ccp_rate": mean(g.get("is_ccp_numeric", [])),
            "quiet_rate": None if "is_ccp_numeric" not in g.columns else 1.0 - (mean(g.get("is_ccp_numeric", [])) or 0.0),
            "played_move_row_rate": mean(g.get("root_played_move_numeric", [])),
            "selected_for_confirm_rate": mean(g.get("selected_for_confirm_numeric", [])),
            "forced_inclusion_rate": mean(g.get("forced_inclusion_numeric", [])),
            "mean_stage_rank": mean(g.get("stage_rank", [])),
            "mean_probe_rank": mean(g.get("probe_rank", [])),
            "mean_confirm_rank": mean(g.get("confirm_rank", [])),
        }
        return out

    rows: List[Dict[str, Any]] = [summarize("all", df)]
    if "ccp_v2_stage" in df.columns:
        for stage, g in df.groupby("ccp_v2_stage", dropna=True):
            rows.append(summarize(f"stage:{stage}", g))
    if "player" in df.columns:
        for player, g in df.groupby("player", dropna=True):
            rows.append(summarize(f"player:{player}", g))
    if "ccp_v2_stage" in df.columns and "player" in df.columns:
        for (player, stage), g in df.groupby(["player", "ccp_v2_stage"], dropna=True):
            rows.append(summarize(f"player:{player}|stage:{stage}", g))
    return pd.DataFrame(rows)


def _best_root_branch_row(g: pd.DataFrame, sort_col: str = "branch_score_log") -> Optional[pd.Series]:
    if g is None or g.empty:
        return None
    col = sort_col if sort_col in g.columns else ("branch_score" if "branch_score" in g.columns else None)
    if col is None:
        return g.iloc[0]
    gg = g.sort_values(col, ascending=False, na_position="last")
    return gg.iloc[0] if not gg.empty else None


def root_branch_ply_summary(root_branches: pd.DataFrame) -> pd.DataFrame:
    """One row per real game ply, summarizing probe/confirm root branches."""
    if root_branches is None or root_branches.empty or not {"game_id", "ply"}.issubset(root_branches.columns):
        return pd.DataFrame()
    df = add_root_branch_derived(root_branches)
    rows: List[Dict[str, Any]] = []

    for (gid, ply), g in df.groupby(["game_id", "ply"], dropna=True):
        probe = g[g.get("ccp_v2_stage", pd.Series(index=g.index, dtype=object)).astype(str).str.lower() == "probe"] if "ccp_v2_stage" in g.columns else pd.DataFrame()
        confirm = g[g.get("ccp_v2_stage", pd.Series(index=g.index, dtype=object)).astype(str).str.lower() == "confirm"] if "ccp_v2_stage" in g.columns else pd.DataFrame()
        first = g.iloc[0]
        top_probe = _best_root_branch_row(probe)
        top_confirm = _best_root_branch_row(confirm)
        played_probe = probe[probe.get("root_played_move_numeric", pd.Series(index=probe.index, dtype=float)) == 1.0] if not probe.empty else pd.DataFrame()
        played_confirm = confirm[confirm.get("root_played_move_numeric", pd.Series(index=confirm.index, dtype=float)) == 1.0] if not confirm.empty else pd.DataFrame()

        def top_value(row: Optional[pd.Series], col: str) -> Any:
            return None if row is None else row.get(col)

        row: Dict[str, Any] = {
            "game_id": gid,
            "ply": ply,
            "move_no": first.get("move_no"),
            "mover": first.get("mover"),
            "player": first.get("player"),
            "played_move_uci": first.get("played_move_uci"),
            "played_move_san": first.get("played_move_san"),
            "best_move_uci": first.get("best_move_uci"),
            "best_move_san": first.get("best_move_san"),
            "wdl_es_loss": first.get("wdl_es_loss"),
            "wdl_move_accuracy": first.get("wdl_move_accuracy"),
            "probe_branch_count": len(probe),
            "confirm_branch_count": len(confirm),
            "confirm_share_of_probe": (len(confirm) / len(probe)) if len(probe) else None,
            "probe_positive_payoff_count": int((probe.get("has_positive_payoff_numeric", pd.Series(dtype=float)) == 1.0).sum()) if not probe.empty else 0,
            "confirm_positive_payoff_count": int((confirm.get("has_positive_payoff_numeric", pd.Series(dtype=float)) == 1.0).sum()) if not confirm.empty else 0,
            "confirm_ccp_count": int((confirm.get("is_ccp_numeric", pd.Series(dtype=float)) == 1.0).sum()) if not confirm.empty else 0,
            "confirm_quiet_count": int((confirm.get("is_ccp_numeric", pd.Series(dtype=float)) == 0.0).sum()) if not confirm.empty else 0,
            "confirm_total_child_nodes_searched": sum(clean_values(confirm.get("child_nodes_searched", []))) if not confirm.empty else 0,
            "confirm_total_child_leaf_count": sum(clean_values(confirm.get("child_leaf_count", []))) if not confirm.empty else 0,
            "confirm_max_child_chain_length": max(clean_values(confirm.get("child_max_chain_length", []))) if clean_values(confirm.get("child_max_chain_length", [])) else None,
            "confirm_mean_branch_score_log": mean(confirm.get("branch_score_log", [])),
            "confirm_max_branch_score_log": max(clean_values(confirm.get("branch_score_log", []))) if clean_values(confirm.get("branch_score_log", [])) else None,
            "top_probe_move_uci": top_value(top_probe, "move_uci"),
            "top_probe_move_san": top_value(top_probe, "move_san"),
            "top_probe_branch_score_log": top_value(top_probe, "branch_score_log"),
            "top_probe_local_loss_vs_best": top_value(top_probe, "local_loss_vs_best"),
            "top_confirm_move_uci": top_value(top_confirm, "move_uci"),
            "top_confirm_move_san": top_value(top_confirm, "move_san"),
            "top_confirm_branch_score_log": top_value(top_confirm, "branch_score_log"),
            "top_confirm_local_loss_vs_best": top_value(top_confirm, "local_loss_vs_best"),
            "played_probe_rank": mean(played_probe.get("stage_rank", [])) if not played_probe.empty else None,
            "played_confirm_rank": mean(played_confirm.get("stage_rank", [])) if not played_confirm.empty else None,
            "played_selected_for_confirm": mean(played_probe.get("selected_for_confirm_numeric", [])) if not played_probe.empty else None,
        }
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["game_id", "ply"]).reset_index(drop=True)


def root_branch_top_moves(root_branches: pd.DataFrame, top_n: int, stage: str = "confirm") -> pd.DataFrame:
    if root_branches is None or root_branches.empty:
        return pd.DataFrame()
    df = add_root_branch_derived(root_branches)
    if "ccp_v2_stage" in df.columns:
        df = df[df["ccp_v2_stage"].astype(str).str.lower() == stage.lower()]
    if df.empty:
        return pd.DataFrame()
    sort_col = "branch_score_log" if "branch_score_log" in df.columns else "branch_score"
    cols = [
        "game_id", "ply", "move_no", "mover", "player", "ccp_v2_stage",
        "stage_rank", "probe_rank", "confirm_rank", "move_uci", "move_san",
        "played_move_uci", "played_move_san", "best_move_uci", "best_move_san",
        "root_played_move", "selected_for_confirm", "is_ccp", "is_check", "is_capture", "is_promotion",
        "quiet_proxy", "quiet_vision_proxy", "es_after_mover", "local_loss_vs_best",
        "plausibility", "delayed_payoff", "payoff_depth", "has_positive_payoff",
        "child_nodes_searched", "child_leaf_count", "child_max_chain_length",
        "child_quiet_pause_burden", "branch_score_log", "branch_score", "wdl_es_loss", "wdl_move_accuracy",
    ]
    return select_columns(df, cols).sort_values(sort_col, ascending=False, na_position="last").head(top_n).reset_index(drop=True)


def root_branch_payoff_moves(root_branches: pd.DataFrame, top_n: int, stage: str = "confirm") -> pd.DataFrame:
    if root_branches is None or root_branches.empty:
        return pd.DataFrame()
    df = add_root_branch_derived(root_branches)
    if "ccp_v2_stage" in df.columns:
        df = df[df["ccp_v2_stage"].astype(str).str.lower() == stage.lower()]
    if "has_positive_payoff_numeric" in df.columns:
        df = df[df["has_positive_payoff_numeric"] == 1.0]
    if df.empty:
        return pd.DataFrame()
    sort_cols = [c for c in ["delayed_payoff", "branch_score_log", "payoff_depth"] if c in df.columns]
    cols = [
        "game_id", "ply", "move_no", "mover", "player", "ccp_v2_stage",
        "stage_rank", "move_uci", "move_san", "root_played_move",
        "played_move_uci", "played_move_san", "best_move_uci", "best_move_san",
        "is_ccp", "is_check", "is_capture", "quiet_proxy", "quiet_vision_proxy",
        "es_after_mover", "es_delta_from_node", "local_loss_vs_best", "pre_loss", "gain",
        "delayed_payoff", "payoff_depth", "best_descendant_es_for_root_mover",
        "child_nodes_searched", "child_leaf_count", "child_max_chain_length",
        "child_quiet_pause_burden", "branch_score_log", "branch_score", "wdl_es_loss", "wdl_move_accuracy",
    ]
    if sort_cols:
        return select_columns(df, cols).sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last").head(top_n).reset_index(drop=True)
    return select_columns(df, cols).head(top_n).reset_index(drop=True)


def root_branch_workload_rows(root_branches: pd.DataFrame, top_n: int, stage: str = "confirm") -> pd.DataFrame:
    if root_branches is None or root_branches.empty:
        return pd.DataFrame()
    df = add_root_branch_derived(root_branches)
    if "ccp_v2_stage" in df.columns:
        df = df[df["ccp_v2_stage"].astype(str).str.lower() == stage.lower()]
    if df.empty:
        return pd.DataFrame()
    sort_cols = [c for c in ["child_leaf_count", "child_nodes_searched", "branch_score_log"] if c in df.columns]
    cols = [
        "game_id", "ply", "move_no", "mover", "player", "ccp_v2_stage",
        "stage_rank", "move_uci", "move_san", "root_played_move",
        "played_move_uci", "played_move_san", "best_move_uci", "best_move_san",
        "is_ccp", "is_check", "is_capture", "quiet_proxy", "quiet_vision_proxy",
        "child_nodes_searched", "child_leaf_count", "child_max_chain_length",
        "child_quiet_pause_count", "child_quiet_pause_burden", "child_branch_total_log",
        "branch_score_log", "branch_score", "local_loss_vs_best", "delayed_payoff", "payoff_depth",
        "wdl_es_loss", "wdl_move_accuracy",
    ]
    if sort_cols:
        return select_columns(df, cols).sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last").head(top_n).reset_index(drop=True)
    return select_columns(df, cols).head(top_n).reset_index(drop=True)


def find_root_branch_diagnostics_path(per_move_path: Path, explicit_path: Optional[str] = None) -> Optional[Path]:
    """Resolve optional v3.6 ccp_v2_root_branch_diagnostics.csv path.

    If no explicit path is supplied, look next to per_move_wdl.csv. This keeps
    the argument optional for analyzer folders using the standard filename.
    """
    if explicit_path:
        return resolve_existing_path(explicit_path, "ccp_v2_root_branch_diagnostics.csv", "--root-branches", required=False)
    candidate = per_move_path.parent / "ccp_v2_root_branch_diagnostics.csv"
    if candidate.exists():
        return candidate
    # Some users keep prefixed copies; use the only matching file in the same folder if unambiguous.
    matches = list(per_move_path.parent.glob("*ccp_v2_root_branch_diagnostics.csv"))
    if len(matches) == 1:
        return matches[0]
    return None


def build_critical_moves(per_move_named: pd.DataFrame, top_n: int) -> pd.DataFrame:
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player", "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "es_best_before_mover", "es_after_played_mover", "wdl_es_loss",
            "wdl_move_accuracy", "wdl_volatility_swing"]
    return select_columns(per_move_named, cols).sort_values("wdl_es_loss", ascending=False).head(top_n).reset_index(drop=True)


def build_volatility_swings(per_move_named: pd.DataFrame, top_n: int) -> pd.DataFrame:
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player", "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "es_before_white", "es_after_white", "wdl_volatility_swing", "wdl_es_loss", "wdl_move_accuracy"]
    return select_columns(per_move_named, cols).sort_values("wdl_volatility_swing", ascending=False).head(top_n).reset_index(drop=True)


def build_hardest_positions(per_move_named: pd.DataFrame, top_n: int, sort_col: str = "position_difficulty_soft_uncertainty") -> pd.DataFrame:
    if sort_col not in per_move_named.columns:
        return pd.DataFrame()
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player", "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "wdl_es_loss", "wdl_move_accuracy", "legal_move_count", "legal_moves_evaluated_for_difficulty",
            "legal_best_es_mover", "legal_best_move_uci", "legal_worst_es_mover", "legal_rms_loss", "narrowness",
            "effective_good_moves", "best_second_gap", "best_third_gap", "played_move_rank",
            "played_move_percentile", "position_difficulty_pure", "position_difficulty_soft_uncertainty",
            "position_difficulty_uncertainty", "position_difficulty_swing",
            "ccp_search_difficulty_pure", "ccp_search_difficulty_soft", "ccp_immediate_burden",
            "ccp_quiet_to_ccp_burden", "ccp_total_burden", "ccp_candidate_effective_count",
            "ccp_candidate_ambiguity", "ccp_legal_check_count", "ccp_legal_capture_count",
            "ccp_legal_promotion_count", "ccp_legal_immediate_count", "ccp_played_is_ccp",
            "ccp_played_is_recapture", "ccp_played_captures_attacker", "ccp_played_saves_material",
            "ccp_best_is_ccp", "ccp_best_is_recapture", "ccp_best_captures_attacker", "ccp_best_saves_material"]
    cols += CCP_V2_COLS
    return select_columns(per_move_named, cols).sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)


def build_difficulty_critical_moves(per_move_named: pd.DataFrame, top_n: int, sort_col: str = "difficulty_weighted_loss_proxy") -> pd.DataFrame:
    if "position_difficulty_soft_uncertainty" not in per_move_named.columns:
        return pd.DataFrame()
    df = per_move_named.copy()
    df["difficulty_weighted_loss_proxy"] = df["position_difficulty_soft_uncertainty"].fillna(0) * df["wdl_es_loss"].fillna(0)
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player", "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "wdl_es_loss", "wdl_move_accuracy", "difficulty_weighted_loss_proxy",
            "position_difficulty_pure", "position_difficulty_soft_uncertainty", "legal_rms_loss",
            "narrowness", "effective_good_moves", "best_second_gap", "played_move_rank", "played_move_percentile"]
    return select_columns(df, cols).sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)



def build_ccp_hardest_positions(per_move_named: pd.DataFrame, top_n: int, sort_col: str = "ccp_search_difficulty_soft") -> pd.DataFrame:
    if sort_col not in per_move_named.columns:
        return pd.DataFrame()
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player",
            "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "wdl_es_loss", "wdl_move_accuracy", "legal_best_es_mover", "legal_best_move_uci",
            "ccp_search_difficulty_pure", "ccp_search_difficulty_soft", "ccp_immediate_burden",
            "ccp_quiet_to_ccp_burden", "ccp_total_burden", "ccp_candidate_effective_count",
            "ccp_candidate_ambiguity", "ccp_legal_check_count", "ccp_legal_capture_count",
            "ccp_legal_promotion_count", "ccp_legal_immediate_count",
            "ccp_attacked_material_value", "ccp_highest_attacked_piece_value", "ccp_attacked_material_count",
            "ccp_played_is_check", "ccp_played_is_capture", "ccp_played_is_promotion", "ccp_played_is_ccp",
            "ccp_played_is_recapture", "ccp_played_captures_attacker", "ccp_played_saves_material",
            "ccp_best_is_check", "ccp_best_is_capture", "ccp_best_is_promotion", "ccp_best_is_ccp",
            "ccp_best_is_recapture", "ccp_best_captures_attacker", "ccp_best_saves_material"]
    cols += CCP_V2_COLS
    return select_columns(per_move_named, cols).sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)


def build_ccp_critical_moves(per_move_named: pd.DataFrame, top_n: int, sort_col: str = "ccp_weighted_loss_proxy") -> pd.DataFrame:
    if "ccp_search_difficulty_soft" not in per_move_named.columns:
        return pd.DataFrame()
    df = per_move_named.copy()
    df["ccp_weighted_loss_proxy"] = df["ccp_search_difficulty_soft"].fillna(0) * df["wdl_es_loss"].fillna(0)
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player",
            "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "wdl_es_loss", "wdl_move_accuracy", "ccp_weighted_loss_proxy",
            "ccp_search_difficulty_pure", "ccp_search_difficulty_soft", "ccp_immediate_burden",
            "ccp_quiet_to_ccp_burden", "ccp_total_burden", "ccp_candidate_effective_count",
            "ccp_candidate_ambiguity", "ccp_legal_immediate_count", "ccp_played_is_ccp",
            "ccp_best_is_ccp", "ccp_best_is_recapture", "ccp_best_saves_material"]
    cols += CCP_V2_COLS
    return select_columns(df, cols).sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)


def build_ccp_v2_hardest_positions(per_move_named: pd.DataFrame, top_n: int, sort_col: str = "ccp_v2_search_difficulty_soft") -> pd.DataFrame:
    if sort_col not in per_move_named.columns:
        return pd.DataFrame()
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player",
            "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "wdl_es_loss", "wdl_move_accuracy", "legal_best_es_mover", "legal_best_move_uci",
            "ccp_search_difficulty_pure", "ccp_search_difficulty_soft", "ccp_total_burden",
            "ccp_candidate_effective_count", "ccp_candidate_ambiguity"] + CCP_V2_COLS
    return select_columns(per_move_named, cols).sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)


def build_ccp_v2_log_hardest_positions(per_move_named: pd.DataFrame, top_n: int, sort_col: str = "ccp_v2_log_search_difficulty_soft") -> pd.DataFrame:
    """Hardest positions on the log-scaled CCP-v2 scale.

    This is usually more interpretable than raw ccp_v2_hardest_positions.csv
    because it compresses massive recursive-tree outliers while preserving the
    order of the selected log column.
    """
    if sort_col not in per_move_named.columns:
        return pd.DataFrame()
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player",
            "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "wdl_es_loss", "wdl_move_accuracy",
            "ccp_v2_log_search_difficulty_pure", "ccp_v2_log_search_difficulty_soft", "ccp_v2_log_branch_total",
            "ccp_v2_max_chain_length", "ccp_v2_quiet_pause_burden",
            "ccp_v2_nodes_searched", "ccp_v2_leaf_count",
            "ccp_v2_probe_eval_attempts", "ccp_v2_eval_attempts", "ccp_v2_total_two_stage_eval_attempts",
            "ccp_v2_probe_root_branch_count", "ccp_v2_confirm_root_moves_selected",
            "ccp_v2_confirm_share_of_probe_branches",
            "ccp_v2_search_difficulty_pure", "ccp_v2_search_difficulty_soft"]
    return select_columns(per_move_named, cols).sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)


def build_ccp_v2_critical_moves(per_move_named: pd.DataFrame, top_n: int, sort_col: str = "ccp_v2_weighted_loss_proxy") -> pd.DataFrame:
    if "ccp_v2_search_difficulty_soft" not in per_move_named.columns:
        return pd.DataFrame()
    df = per_move_named.copy()
    df["ccp_v2_weighted_loss_proxy"] = df["ccp_v2_search_difficulty_soft"].fillna(0) * df["wdl_es_loss"].fillna(0)
    if "ccp_v2_log_search_difficulty_soft" in df.columns:
        df["ccp_v2_log_weighted_loss_proxy"] = df["ccp_v2_log_search_difficulty_soft"].fillna(0) * df["wdl_es_loss"].fillna(0)
    cols = ["game_id", "ply", "move_no", "mover", "player", "difficulty_caused_by_player",
            "caused_by_move_uci", "caused_by_move_san", "move_uci", "move_san", "best_move_uci", "best_move_san",
            "wdl_es_loss", "wdl_move_accuracy", "ccp_v2_weighted_loss_proxy", "ccp_v2_log_weighted_loss_proxy",
            "ccp_search_difficulty_pure", "ccp_search_difficulty_soft"] + CCP_V2_COLS
    return select_columns(df, cols).sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)


def df_to_markdown(df: pd.DataFrame, digits: int = 3) -> str:
    if df is None or df.empty:
        return "_No data._"
    df2 = df.copy()
    for col in df2.columns:
        if pd.api.types.is_numeric_dtype(df2[col]):
            df2[col] = df2[col].map(lambda x: fmt(x, digits))
    return df2.to_markdown(index=False)


def write_markdown_report(outpath: Path, match_name: str, all_metrics: pd.DataFrame, player_summary: pd.DataFrame,
                          game_summary: pd.DataFrame, critical_moves: pd.DataFrame, volatility_swings: pd.DataFrame,
                          hardest_positions: pd.DataFrame, difficulty_critical_moves: pd.DataFrame,
                          ccp_hardest_positions: pd.DataFrame, ccp_critical_moves: pd.DataFrame,
                          ccp_v2_hardest_positions: pd.DataFrame, ccp_v2_log_hardest_positions: pd.DataFrame,
                          ccp_v2_critical_moves: pd.DataFrame, ccp_v2_log_critical_moves: pd.DataFrame,
                          ccp_v2_probe_confirm_summary: pd.DataFrame,
                          ccp_v2_probe_confirm_diagnostics: pd.DataFrame,
                          ccp_v2_root_branch_summary: pd.DataFrame,
                          ccp_v2_root_branch_ply_summary: pd.DataFrame,
                          ccp_v2_root_branch_top_moves: pd.DataFrame,
                          ccp_v2_root_branch_payoff_moves: pd.DataFrame,
                          ccp_v2_root_branch_workload_rows: pd.DataFrame) -> None:
    lines: List[str] = [f"# {match_name} — WDL + Difficulty Report", ""]
    lines.append("This report uses Stockfish WDL-based expected-score metrics. If difficulty columns are present, it also reports all-legal-move position-difficulty metrics.")
    lines.append("")

    lines.append("## Interpretation Notes")
    lines.append("")
    lines.append("- Raw CCP-v2 is experimental recursive tree mass. It can be dominated by extreme outliers and should not be used as the main publication scale.")
    lines.append("- CCP-v2 log metrics (`log1p`) are the preferred reportable CCP-v2 scale for cross-parameter comparisons.")
    lines.append("- `ccp_v2_log_critical_moves.csv` is the main practical CCP-v2 critical-move file: it combines log-scaled search burden with real WDL expected-score loss.")
    lines.append("- Probe/confirm fields are workload/allocation diagnostics: probe finds candidate branches, confirm gives the higher-budget final CCP-v2 score.")
    lines.append("- Root-branch diagnostics are v3.6+ internal search-shape tables: they show which root moves were probed/confirmed, how they ranked, and how much subtree work each branch consumed.")
    lines.append("- Difficulty Pressure Quality (DPQ) = player's mean caused pressure × match mean caused pressure. It is a style/pressure metric, not a direct accuracy metric.")
    lines.append("- Pressure Yield is continuous difficulty-weighted ES loss. Suffered = player's own loss under pressure faced; Caused = opponent's loss under pressure attributed to this player.")
    lines.append("")

    lines.append("## All Metrics: Player A, Player B, Both")
    lines.append("")
    cols = ["metric", "aggregation", "direction", "player_A_name", "player_A_value", "player_A_sd",
            "player_B_name", "player_B_value", "player_B_sd", "both_players_value", "both_players_sd"]
    lines.append(df_to_markdown(select_columns(all_metrics, cols), digits=3))
    lines.append("")

    lines.append("## Player Summary")
    lines.append("")
    pcols = ["player", "games", "moves", "score_sum", "expected_score_sum", "conversion_sum",
             "accuracy_wdl_mean", "accuracy_wdl_sd", "mean_es_loss", "es_loss_sd", "rms_es_loss",
             "volatility_wdl_mean", "total_volatility_wdl", "difficulty_pure_faced_mean", "difficulty_pure_caused_mean",
             "difficulty_soft_uncertainty_faced_mean", "difficulty_soft_uncertainty_caused_mean",
             "difficulty_soft_uncertainty_weighted_accuracy",
             "narrowness_faced_mean", "narrowness_caused_mean", "effective_good_moves_faced_mean", "effective_good_moves_caused_mean",
             "ccp_search_difficulty_pure_faced_mean", "ccp_search_difficulty_pure_caused_mean",
             "ccp_search_difficulty_soft_faced_mean", "ccp_search_difficulty_soft_caused_mean",
             "ccp_search_difficulty_soft_weighted_accuracy", "ccp_immediate_burden_faced_mean",
             "ccp_quiet_to_ccp_burden_faced_mean", "ccp_candidate_effective_count_faced_mean",
             "ccp_v2_search_difficulty_pure_faced_mean", "ccp_v2_search_difficulty_pure_caused_mean",
             "ccp_v2_search_difficulty_soft_faced_mean", "ccp_v2_search_difficulty_soft_caused_mean",
             "ccp_v2_search_difficulty_soft_weighted_accuracy", "ccp_v2_max_chain_length_faced_mean",
             "ccp_v2_quiet_pause_burden_faced_mean", "ccp_v2_branch_total_faced_mean",
             "ccp_v2_branch_effective_count_faced_mean",
             "ccp_v2_probe_eval_attempts_faced_mean", "ccp_v2_eval_attempts_faced_mean",
             "ccp_v2_total_two_stage_eval_attempts_faced_mean",
             "ccp_v2_probe_root_branch_count_faced_mean", "ccp_v2_confirm_root_moves_selected_faced_mean",
             "ccp_v2_confirm_share_of_probe_branches_faced_mean",
             "difficulty_soft_uncertainty_caused_share", "difficulty_soft_uncertainty_dpq",
             "difficulty_soft_uncertainty_pressure_yield_suffered", "difficulty_soft_uncertainty_pressure_yield_caused",
             "ccp_search_difficulty_pure_caused_share", "ccp_search_difficulty_pure_dpq",
             "ccp_search_difficulty_pure_pressure_yield_suffered", "ccp_search_difficulty_pure_pressure_yield_caused",
             "ccp_v2_log_search_difficulty_soft_caused_share", "ccp_v2_log_search_difficulty_soft_dpq",
             "ccp_v2_log_search_difficulty_soft_pressure_yield_suffered", "ccp_v2_log_search_difficulty_soft_pressure_yield_caused"]
    lines.append(df_to_markdown(select_columns(player_summary, pcols), digits=3))
    lines.append("")

    lines.append("## Game Summary")
    lines.append("")
    gcols = ["game_id", "white", "black", "result", "plies", "accuracy_white", "accuracy_black",
             "game_accuracy", "mutual_accuracy", "mean_es_loss_white", "mean_es_loss_black",
             "mean_difficulty_pure_white", "mean_difficulty_pure_black",
             "mean_difficulty_soft_uncertainty_white", "mean_difficulty_soft_uncertainty_black",
             "difficulty_soft_uncertainty_weighted_accuracy_white", "difficulty_soft_uncertainty_weighted_accuracy_black",
             "mean_ccp_search_difficulty_pure_white", "mean_ccp_search_difficulty_pure_black",
             "mean_ccp_search_difficulty_soft_white", "mean_ccp_search_difficulty_soft_black",
             "ccp_search_difficulty_soft_weighted_accuracy_white", "ccp_search_difficulty_soft_weighted_accuracy_black",
             "mean_ccp_v2_search_difficulty_pure_white", "mean_ccp_v2_search_difficulty_pure_black",
             "mean_ccp_v2_search_difficulty_soft_white", "mean_ccp_v2_search_difficulty_soft_black",
             "ccp_v2_search_difficulty_soft_weighted_accuracy_white", "ccp_v2_search_difficulty_soft_weighted_accuracy_black",
             "mean_ccp_v2_max_chain_length_white", "mean_ccp_v2_max_chain_length_black",
             "mean_ccp_v2_quiet_pause_burden_white", "mean_ccp_v2_quiet_pause_burden_black",
             "mean_ccp_v2_branch_total_white", "mean_ccp_v2_branch_total_black",
             "mean_ccp_v2_probe_eval_attempts_white", "mean_ccp_v2_probe_eval_attempts_black",
             "mean_ccp_v2_eval_attempts_white", "mean_ccp_v2_eval_attempts_black",
             "mean_ccp_v2_total_two_stage_eval_attempts_white", "mean_ccp_v2_total_two_stage_eval_attempts_black",
             "mean_ccp_v2_probe_root_branch_count_white", "mean_ccp_v2_probe_root_branch_count_black",
             "mean_ccp_v2_confirm_root_moves_selected_white", "mean_ccp_v2_confirm_root_moves_selected_black"]
    lines.append(df_to_markdown(select_columns(game_summary, gcols), digits=3))
    lines.append("")

    lines.append("## Largest WDL Expected-Score Losses")
    lines.append("")
    lines.append(df_to_markdown(critical_moves, digits=4))
    lines.append("")

    lines.append("## Largest WDL Volatility Swings")
    lines.append("")
    lines.append(df_to_markdown(volatility_swings, digits=4))
    lines.append("")

    if hardest_positions is not None and not hardest_positions.empty:
        lines.append("## Hardest Positions by Soft-Uncertainty Difficulty")
        lines.append("")
        lines.append(df_to_markdown(hardest_positions, digits=4))
        lines.append("")

    if difficulty_critical_moves is not None and not difficulty_critical_moves.empty:
        lines.append("## Largest Difficulty-Weighted Loss Proxies")
        lines.append("")
        lines.append(df_to_markdown(difficulty_critical_moves, digits=4))
        lines.append("")

    if ccp_hardest_positions is not None and not ccp_hardest_positions.empty:
        lines.append("## Hardest Positions by CCP Soft Search Difficulty")
        lines.append("")
        lines.append(df_to_markdown(ccp_hardest_positions, digits=4))
        lines.append("")

    if ccp_critical_moves is not None and not ccp_critical_moves.empty:
        lines.append("## Largest CCP Difficulty-Weighted Loss Proxies")
        lines.append("")
        lines.append(df_to_markdown(ccp_critical_moves, digits=4))
        lines.append("")

    if ccp_v2_hardest_positions is not None and not ccp_v2_hardest_positions.empty:
        lines.append("## Hardest Positions by Raw CCP v2 Soft Search Difficulty")
        lines.append("")
        lines.append("_Experimental: raw recursive tree mass is outlier-sensitive; prefer the log-hardest and log-critical files for interpretation._")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_hardest_positions, digits=4))
        lines.append("")

    if ccp_v2_log_hardest_positions is not None and not ccp_v2_log_hardest_positions.empty:
        lines.append("## Hardest Positions by CCP v2 Log Soft Search Difficulty")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_log_hardest_positions, digits=4))
        lines.append("")

    if ccp_v2_critical_moves is not None and not ccp_v2_critical_moves.empty:
        lines.append("## Largest Raw CCP v2 Difficulty-Weighted Loss Proxies")
        lines.append("")
        lines.append("_Experimental: raw CCP-v2 criticality can be dominated by tree-mass outliers; prefer the log-critical section below._")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_critical_moves, digits=4))
        lines.append("")

    if ccp_v2_log_critical_moves is not None and not ccp_v2_log_critical_moves.empty:
        lines.append("## Largest CCP v2 Log Difficulty-Weighted Loss Proxies")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_log_critical_moves, digits=4))
        lines.append("")

    if ccp_v2_probe_confirm_summary is not None and not ccp_v2_probe_confirm_summary.empty:
        lines.append("## CCP v2 Probe/Confirm Summary")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_probe_confirm_summary, digits=4))
        lines.append("")

    if ccp_v2_probe_confirm_diagnostics is not None and not ccp_v2_probe_confirm_diagnostics.empty:
        lines.append("## Highest CCP v2 Probe/Confirm Workload Rows")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_probe_confirm_diagnostics, digits=4))
        lines.append("")

    if ccp_v2_root_branch_summary is not None and not ccp_v2_root_branch_summary.empty:
        lines.append("## CCP v2 Root-Branch Diagnostics Summary")
        lines.append("")
        lines.append("_v3.6+ diagnostic: one row per candidate root move in the probe/confirm search. These rows explain search allocation and branch shape; they are not independent playing-strength scores._")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_root_branch_summary, digits=4))
        lines.append("")

    if ccp_v2_root_branch_top_moves is not None and not ccp_v2_root_branch_top_moves.empty:
        lines.append("## Highest Confirmed CCP v2 Root Branches")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_root_branch_top_moves, digits=4))
        lines.append("")

    if ccp_v2_root_branch_payoff_moves is not None and not ccp_v2_root_branch_payoff_moves.empty:
        lines.append("## Confirmed CCP v2 Positive/Delayed-Payoff Root Branches")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_root_branch_payoff_moves, digits=4))
        lines.append("")

    if ccp_v2_root_branch_workload_rows is not None and not ccp_v2_root_branch_workload_rows.empty:
        lines.append("## Highest CCP v2 Root-Branch Workload Rows")
        lines.append("")
        lines.append(df_to_markdown(ccp_v2_root_branch_workload_rows, digits=4))
        lines.append("")

    lines.append("## Reading Guide")
    lines.append("")
    lines.append("- Score, Expected Score, Conversion, Total Volatility, HardRAP, SoftRAP, and Total Difficulty metrics are match totals in `all_metrics_3source.csv`.")
    lines.append("- Average-type metrics such as WDL Accuracy, Mean ES Loss, WDL Volatility, and Difficulty are means, with SD from their natural source data.")
    lines.append("- WDL Accuracy = 100 × (1 − expected-score loss).")
    lines.append("- Pure Position Difficulty = Narrowness × sqrt(legal RMS loss).")
    lines.append("- Soft-Uncertainty Difficulty = Pure Difficulty × sqrt(4B(1−B)); it is the preferred practical difficulty candidate.")
    lines.append("- Faced difficulty is measured before the player's own move. Caused difficulty is attributed one ply backward to the previous mover, i.e. the difficulty immediately given to the opponent. Higher difficulty is harder/narrower/more result-relevant exposure, not automatically better play.")
    lines.append("- CCP Search Difficulty estimates Checks/Captures/Promotions forcing-search burden. It is separate from all-legal objective difficulty and does not use an obviousness multiplier in v1.")
    lines.append("- CCP v2 Search Difficulty uses a recursive candidate tree with selected CCP and positive-proxy quiet candidates, directed ES gain, delayed payoff, chain length, quiet-pause burden, and branch ambiguity.")
    lines.append("- CCP v2 Log Search Difficulty uses log1p(raw CCP-v2 difficulty). It preserves ordering within a raw column but compresses outliers; use it as the preferred human-readable stability check across higher CCP-v2 settings.")
    lines.append("- In v3.5 two-stage mode, the probe stage is a cheaper broad branch selector, while the confirm stage is the higher-budget final score. Probe/confirm fields are workload and allocation diagnostics, not independent playing-strength metrics.")
    lines.append("- CCP v2 Confirm Eval Attempts equals the final/confirm-stage evaluations. CCP v2 Probe Eval Attempts records the cheap broad scan. Total Two-Stage Eval Attempts is their sum.")
    lines.append("- Difficulty Caused Share shows what fraction of total match pressure a player caused. It is useful for asymmetry/style comparisons.")
    lines.append("- Difficulty Pressure Quality (DPQ) adapts the PQ idea to caused pressure: player mean caused pressure × match mean caused pressure. Use per-move means, not match totals, when comparing different match lengths.")
    lines.append("- Pressure Yield Suffered is the player's pressure-weighted ES loss on their own moves; lower is better. Pressure Yield Caused is the opponent's pressure-weighted ES loss in positions attributed to this player; higher means pressure produced more opponent loss.")
    lines.append("- Root-branch top-move tables should be read as branch-burden diagnostics: a top branch is not automatically Stockfish's best chess move; it is the root move whose confirmed CCP-v2 subtree carried the largest search burden on the selected score.")
    lines.append("")
    outpath.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def parse_player_order(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parts = [p.strip() for p in value.split(";") if p.strip()]
    return parts if parts else None


def resolve_existing_path(path_value: Optional[str], expected_name: Optional[str] = None, label: str = "file", required: bool = True) -> Optional[Path]:
    """Resolve a user-supplied path and give useful diagnostics if it is missing.

    If the supplied value is a directory and expected_name is given, the function
    looks for that file inside the directory. If the supplied full path is missing,
    it searches the existing parent directory recursively for expected_name. This
    helps when analyzer output folders are named slightly differently from the
    command line path.
    """
    if not path_value:
        if required:
            raise SystemExit(f"Missing required {label} path.")
        return None

    raw = Path(path_value)

    candidates = []
    candidates.append(raw)
    if raw.is_dir() and expected_name:
        candidates.append(raw / expected_name)

    for c in candidates:
        if c.exists():
            return c

    # If the exact file is missing but the parent exists, search below parent.
    search_roots = []
    if raw.parent.exists():
        search_roots.append(raw.parent)
    # If the path has a non-existing child folder, try the nearest existing ancestor.
    cur = raw
    while cur != cur.parent:
        cur = cur.parent
        if cur.exists():
            search_roots.append(cur)
            break

    suggestions = []
    if expected_name:
        seen = set()
        for root in search_roots:
            try:
                for found in root.rglob(expected_name):
                    if found not in seen:
                        suggestions.append(found)
                        seen.add(found)
                    if len(suggestions) >= 10:
                        break
            except Exception:
                pass
            if len(suggestions) >= 10:
                break

    msg = [f"Could not find {label}: {raw}"]
    if suggestions:
        msg.append(
            "Possible matching files found:\n" +
            "\n".join(f"  {x}" for x in suggestions[:10])
        )
    else:
        msg.append("No matching file found under the nearest existing folder.")
    raise SystemExit("\n".join(msg))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create readable 3-source WDL + difficulty reports from analyzer CSV output.")
    parser.add_argument("--per-game", required=True, help="Path to per_game_wdl_metrics.csv")
    parser.add_argument("--per-move", required=True, help="Path to per_move_wdl.csv")
    parser.add_argument("--summary", required=False, help="Optional path to summary_wdl_metrics.csv")
    parser.add_argument("--metadata", required=False, help="Optional path to analysis_metadata.csv or analysis_metadata_wide.csv")
    parser.add_argument("--root-branches", required=False, help="Optional path to ccp_v2_root_branch_diagnostics.csv from analyzer v3.6+")
    parser.add_argument("--pgn", required=False, help="Optional PGN path for SAN notation")
    parser.add_argument("--outdir", default="wdl_report_v4", help="Output directory")
    parser.add_argument("--match-name", default="WDL Match Report", help="Name shown in markdown report")
    parser.add_argument("--top-n", type=int, default=30, help="Number of critical/hardest rows to include")
    parser.add_argument("--player-order", default=None, help="Optional explicit Player A;Player B order, separated by semicolon")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    per_game_path = resolve_existing_path(args.per_game, "per_game_wdl_metrics.csv", "--per-game")
    per_move_path = resolve_existing_path(args.per_move, "per_move_wdl.csv", "--per-move")
    metadata_path = resolve_existing_path(args.metadata, None, "--metadata", required=False) if args.metadata else None
    root_branches_path = find_root_branch_diagnostics_path(per_move_path, args.root_branches)
    pgn_path = resolve_existing_path(args.pgn, None, "--pgn", required=False) if args.pgn else None

    per_game = pd.read_csv(per_game_path)
    per_move = pd.read_csv(per_move_path)

    per_move = add_san_if_available(per_move, str(pgn_path) if pgn_path else None)
    per_move = add_best_move_san_if_available(per_move, str(pgn_path) if pgn_path else None)
    per_move_named = add_player_names_to_moves(per_move, per_game)
    per_move_named = add_difficulty_causation(per_move_named)
    per_move_named, per_game = add_ccp_v2_log_metrics(per_move_named, per_game)
    per_move_named = add_ccp_v2_probe_confirm_derived(per_move_named)

    player_order = parse_player_order(args.player_order)
    player_summary = build_player_summary(per_game, per_move_named)
    game_summary = build_game_summary(per_game)
    all_metrics = build_all_metrics_3source(per_game, per_move_named, player_summary, player_order)
    metric_ratios = make_metric_ratios(all_metrics)
    critical_moves = build_critical_moves(per_move_named, args.top_n)
    volatility_swings = build_volatility_swings(per_move_named, args.top_n)
    hardest_positions = build_hardest_positions(per_move_named, args.top_n)
    difficulty_critical_moves = build_difficulty_critical_moves(per_move_named, args.top_n)
    ccp_hardest_positions = build_ccp_hardest_positions(per_move_named, args.top_n)
    ccp_critical_moves = build_ccp_critical_moves(per_move_named, args.top_n)
    ccp_v2_hardest_positions = build_ccp_v2_hardest_positions(per_move_named, args.top_n)
    ccp_v2_log_hardest_positions = build_ccp_v2_log_hardest_positions(per_move_named, args.top_n)
    ccp_v2_critical_moves = build_ccp_v2_critical_moves(per_move_named, args.top_n)
    ccp_v2_log_critical_moves = build_ccp_v2_critical_moves(per_move_named, args.top_n, sort_col="ccp_v2_log_weighted_loss_proxy")
    ccp_v2_probe_confirm_summary = build_ccp_v2_probe_confirm_summary(per_move_named)
    ccp_v2_probe_confirm_diagnostics = build_ccp_v2_probe_confirm_diagnostics(per_move_named, args.top_n)

    if root_branches_path:
        root_branches = add_root_branch_derived(pd.read_csv(root_branches_path))
        ccp_v2_root_branch_summary = root_branch_stage_summary(root_branches)
        ccp_v2_root_branch_ply_summary = root_branch_ply_summary(root_branches)
        ccp_v2_root_branch_top_moves = root_branch_top_moves(root_branches, args.top_n, stage="confirm")
        ccp_v2_root_branch_payoff_moves = root_branch_payoff_moves(root_branches, args.top_n, stage="confirm")
        ccp_v2_root_branch_workload_rows = root_branch_workload_rows(root_branches, args.top_n, stage="confirm")
    else:
        ccp_v2_root_branch_summary = pd.DataFrame()
        ccp_v2_root_branch_ply_summary = pd.DataFrame()
        ccp_v2_root_branch_top_moves = pd.DataFrame()
        ccp_v2_root_branch_payoff_moves = pd.DataFrame()
        ccp_v2_root_branch_workload_rows = pd.DataFrame()

    all_metrics.to_csv(outdir / "all_metrics_3source.csv", index=False)
    metric_ratios.to_csv(outdir / "metric_ratios.csv", index=False)
    player_summary.to_csv(outdir / "player_summary.csv", index=False)
    game_summary.to_csv(outdir / "game_summary_readable.csv", index=False)
    critical_moves.to_csv(outdir / "critical_moves.csv", index=False)
    volatility_swings.to_csv(outdir / "volatility_swings.csv", index=False)
    if not hardest_positions.empty:
        hardest_positions.to_csv(outdir / "hardest_positions.csv", index=False)
    if not difficulty_critical_moves.empty:
        difficulty_critical_moves.to_csv(outdir / "difficulty_critical_moves.csv", index=False)
    if not ccp_hardest_positions.empty:
        ccp_hardest_positions.to_csv(outdir / "ccp_hardest_positions.csv", index=False)
    if not ccp_critical_moves.empty:
        ccp_critical_moves.to_csv(outdir / "ccp_critical_moves.csv", index=False)
    if not ccp_v2_hardest_positions.empty:
        ccp_v2_hardest_positions.to_csv(outdir / "ccp_v2_hardest_positions.csv", index=False)
    if not ccp_v2_log_hardest_positions.empty:
        ccp_v2_log_hardest_positions.to_csv(outdir / "ccp_v2_log_hardest_positions.csv", index=False)
    if not ccp_v2_critical_moves.empty:
        ccp_v2_critical_moves.to_csv(outdir / "ccp_v2_critical_moves.csv", index=False)
    if not ccp_v2_log_critical_moves.empty:
        ccp_v2_log_critical_moves.to_csv(outdir / "ccp_v2_log_critical_moves.csv", index=False)
    if not ccp_v2_probe_confirm_summary.empty:
        ccp_v2_probe_confirm_summary.to_csv(outdir / "ccp_v2_probe_confirm_summary.csv", index=False)
    if not ccp_v2_probe_confirm_diagnostics.empty:
        ccp_v2_probe_confirm_diagnostics.to_csv(outdir / "ccp_v2_probe_confirm_diagnostics.csv", index=False)
    if not ccp_v2_root_branch_summary.empty:
        ccp_v2_root_branch_summary.to_csv(outdir / "ccp_v2_root_branch_summary.csv", index=False)
    if not ccp_v2_root_branch_ply_summary.empty:
        ccp_v2_root_branch_ply_summary.to_csv(outdir / "ccp_v2_root_branch_ply_summary.csv", index=False)
    if not ccp_v2_root_branch_top_moves.empty:
        ccp_v2_root_branch_top_moves.to_csv(outdir / "ccp_v2_root_branch_top_moves.csv", index=False)
    if not ccp_v2_root_branch_payoff_moves.empty:
        ccp_v2_root_branch_payoff_moves.to_csv(outdir / "ccp_v2_root_branch_payoff_moves.csv", index=False)
    if not ccp_v2_root_branch_workload_rows.empty:
        ccp_v2_root_branch_workload_rows.to_csv(outdir / "ccp_v2_root_branch_workload_rows.csv", index=False)

    # Copy metadata into report folder if provided.
    if args.metadata:
        try:
            meta = pd.read_csv(metadata_path if metadata_path else args.metadata)
            meta.to_csv(outdir / (metadata_path.name if metadata_path else Path(args.metadata).name), index=False)
        except Exception as e:
            print(f"Warning: metadata copy failed: {e}")

    write_markdown_report(
        outdir / "article_report.md",
        args.match_name,
        all_metrics,
        player_summary,
        game_summary,
        critical_moves,
        volatility_swings,
        hardest_positions,
        difficulty_critical_moves,
        ccp_hardest_positions,
        ccp_critical_moves,
        ccp_v2_hardest_positions,
        ccp_v2_log_hardest_positions,
        ccp_v2_critical_moves,
        ccp_v2_log_critical_moves,
        ccp_v2_probe_confirm_summary,
        ccp_v2_probe_confirm_diagnostics,
        ccp_v2_root_branch_summary,
        ccp_v2_root_branch_ply_summary,
        ccp_v2_root_branch_top_moves,
        ccp_v2_root_branch_payoff_moves,
        ccp_v2_root_branch_workload_rows,
    )

    print("Done.")
    print(f"All metrics:                {outdir / 'all_metrics_3source.csv'}")
    print(f"Metric ratios:              {outdir / 'metric_ratios.csv'}")
    print(f"Player summary:             {outdir / 'player_summary.csv'}")
    print(f"Game summary:               {outdir / 'game_summary_readable.csv'}")
    print(f"Critical moves:             {outdir / 'critical_moves.csv'}")
    print(f"Volatility swings:          {outdir / 'volatility_swings.csv'}")
    if not hardest_positions.empty:
        print(f"Hardest positions:          {outdir / 'hardest_positions.csv'}")
    if not difficulty_critical_moves.empty:
        print(f"Difficulty critical moves:  {outdir / 'difficulty_critical_moves.csv'}")
    if not ccp_hardest_positions.empty:
        print(f"CCP hardest positions:      {outdir / 'ccp_hardest_positions.csv'}")
    if not ccp_critical_moves.empty:
        print(f"CCP critical moves:         {outdir / 'ccp_critical_moves.csv'}")
    if not ccp_v2_hardest_positions.empty:
        print(f"CCP v2 hardest positions:   {outdir / 'ccp_v2_hardest_positions.csv'}")
    if not ccp_v2_log_hardest_positions.empty:
        print(f"CCP v2 log hardest pos.:    {outdir / 'ccp_v2_log_hardest_positions.csv'}")
    if not ccp_v2_critical_moves.empty:
        print(f"CCP v2 critical moves:      {outdir / 'ccp_v2_critical_moves.csv'}")
    if not ccp_v2_log_critical_moves.empty:
        print(f"CCP v2 log critical moves:  {outdir / 'ccp_v2_log_critical_moves.csv'}")
    if not ccp_v2_probe_confirm_summary.empty:
        print(f"Probe/confirm summary:      {outdir / 'ccp_v2_probe_confirm_summary.csv'}")
    if not ccp_v2_probe_confirm_diagnostics.empty:
        print(f"Probe/confirm diagnostics:  {outdir / 'ccp_v2_probe_confirm_diagnostics.csv'}")
    if not ccp_v2_root_branch_summary.empty:
        print(f"Root-branch summary:        {outdir / 'ccp_v2_root_branch_summary.csv'}")
    if not ccp_v2_root_branch_ply_summary.empty:
        print(f"Root-branch ply summary:    {outdir / 'ccp_v2_root_branch_ply_summary.csv'}")
    if not ccp_v2_root_branch_top_moves.empty:
        print(f"Root-branch top moves:      {outdir / 'ccp_v2_root_branch_top_moves.csv'}")
    if not ccp_v2_root_branch_payoff_moves.empty:
        print(f"Root-branch payoff moves:   {outdir / 'ccp_v2_root_branch_payoff_moves.csv'}")
    if not ccp_v2_root_branch_workload_rows.empty:
        print(f"Root-branch workload rows:  {outdir / 'ccp_v2_root_branch_workload_rows.csv'}")
    print(f"Markdown report:            {outdir / 'article_report.md'}")


if __name__ == "__main__":
    main()

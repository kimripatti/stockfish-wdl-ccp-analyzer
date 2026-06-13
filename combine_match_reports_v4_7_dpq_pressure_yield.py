#!/usr/bin/env python3
"""
combine_match_reports_v4_7_dpq_pressure_yield.py

Run-level combiner for match reports produced by make_wdl_report_v4_7_ccp_v2_root_branch_summary.py, v4_5/v4_3 CCP reporters, or earlier v4 difficulty reporters.
It is also backward-compatible with v3 match reports as long as each match folder/file prefix
contains *_all_metrics_3source.csv and optionally *_game_summary_readable.csv.

Expected input files per match, using common prefix:
  01_fischer-taimanov_all_metrics_3source.csv
  01_fischer-taimanov_metric_ratios.csv
  01_fischer-taimanov_game_summary_readable.csv

Main outputs:
  - run_all_metrics.csv
  - run_metric_ratios.csv
  - run_summary_by_match.csv
  - run_summary_overall.csv
  - run_game_summary.csv
  - run_game_metric_ratios.csv
  - run_article_report.md
  - run_ccp_v2_root_branch_summary.csv              (if v4.7 root-branch summaries exist)
  - run_ccp_v2_root_branch_by_match.csv             (if v4.7 root-branch ply summaries exist)
  - run_ccp_v2_root_branch_ply_summary.csv          (if v4.7 root-branch ply summaries exist)
  - run_ccp_v2_root_branch_top_moves.csv            (if v4.7 root-branch top-move summaries exist)
  - run_ccp_v2_root_branch_payoff_moves.csv         (if v4.7 root-branch payoff summaries exist)
  - run_ccp_v2_root_branch_workload_rows.csv        (if v4.7 root-branch workload summaries exist)

Usage:
python combine_match_reports_v4_3_2_ccp_v2_vision_log.py \
  --input-dir match_reports \
  --main-player "Robert James Fischer" \
  --run-name "Fischer 1971-1972 Run" \
  --outdir combined_run_report
"""

import argparse
import re
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


SIGNED_OR_ZERO_CROSSING = {"conversion", "dominance_wdl", "conversion_game", "game_conversion_magnitude"}
LOWER_IS_BETTER = {
    "mean_es_loss", "rms_es_loss", "error_concentration", "volatility_wdl", "total_volatility_wdl",
    "game_mean_es_loss", "game_rms_es_loss", "game_error_concentration", "game_wdl_volatility",
    "game_total_wdl_volatility", "mean_es_loss_game", "rms_es_loss_game",
    "error_concentration_game", "volatility_game_wdl", "total_volatility_game_wdl",
    "difficulty_pure_weighted_es_loss", "difficulty_uncertainty_weighted_es_loss",
    "difficulty_soft_uncertainty_weighted_es_loss", "difficulty_risk_weighted_es_loss",
    "difficulty_defender_pressure_weighted_es_loss", "difficulty_swing_weighted_es_loss",
    "ccp_search_difficulty_pure_weighted_es_loss",
    "ccp_search_difficulty_soft_weighted_es_loss",
    "ccp_v2_search_difficulty_pure_weighted_es_loss",
    "ccp_v2_search_difficulty_soft_weighted_es_loss",
    "ccp_v2_log_search_difficulty_pure_weighted_es_loss",
    "ccp_v2_log_search_difficulty_soft_weighted_es_loss",
}
HIGHER_IS_BETTER = {
    "score", "expected_score", "accuracy_wdl", "pq_wdl", "hard_rap", "soft_rap",
    "game_accuracy_wdl", "mutual_accuracy_wdl", "game_hardrap", "game_softrap",
    "difficulty_pure_weighted_accuracy", "difficulty_uncertainty_weighted_accuracy",
    "difficulty_soft_uncertainty_weighted_accuracy", "difficulty_risk_weighted_accuracy",
    "difficulty_defender_pressure_weighted_accuracy", "difficulty_swing_weighted_accuracy",
    "ccp_search_difficulty_pure_weighted_accuracy",
    "ccp_search_difficulty_soft_weighted_accuracy",
    "ccp_v2_search_difficulty_pure_weighted_accuracy",
    "ccp_v2_search_difficulty_soft_weighted_accuracy",
    "ccp_v2_log_search_difficulty_pure_weighted_accuracy",
    "ccp_v2_log_search_difficulty_soft_weighted_accuracy",
}
HIGHER_IS_HARDER = {
    "difficulty_pure", "difficulty_uncertainty", "difficulty_soft_uncertainty", "difficulty_risk",
    "difficulty_defender_pressure", "difficulty_swing", "legal_rms_loss", "narrowness",
    "legal_loss_swing", "best_second_gap", "best_third_gap",
    "position_difficulty_pure", "position_difficulty_uncertainty", "position_difficulty_soft_uncertainty",
    "position_difficulty_risk", "position_difficulty_defender_pressure", "position_difficulty_swing",
    "ccp_search_difficulty_pure", "ccp_search_difficulty_soft",
    "ccp_immediate_burden", "ccp_quiet_to_ccp_burden", "ccp_total_burden",
    "ccp_candidate_effective_count", "ccp_candidate_ambiguity",
    "ccp_legal_check_count", "ccp_legal_capture_count", "ccp_legal_promotion_count",
    "ccp_legal_immediate_count", "ccp_attacked_material_value",
    "ccp_highest_attacked_piece_value", "ccp_attacked_material_count",
    "ccp_v2_search_difficulty_pure", "ccp_v2_search_difficulty_soft",
    "ccp_v2_log_search_difficulty_pure", "ccp_v2_log_search_difficulty_soft", "ccp_v2_log_branch_total",
    "ccp_v2_nodes_searched", "ccp_v2_leaf_count",
    "ccp_v2_max_chain_length", "ccp_v2_total_chain_length", "ccp_v2_mean_chain_length",
    "ccp_v2_quiet_pause_count", "ccp_v2_quiet_pause_burden",
    "ccp_v2_branch_total", "ccp_v2_branch_max", "ccp_v2_branch_mean",
    "ccp_v2_branch_effective_count", "ccp_v2_branch_ambiguity",
}
LOWER_IS_BROADER = {"effective_good_moves", "effective_good_moves_entropy", "ccp_candidate_effective_count", "ccp_v2_branch_effective_count"}
SUM_METRICS = {
    "score", "expected_score", "conversion", "total_volatility_wdl", "hard_rap", "soft_rap",
    "total_difficulty_pure", "total_difficulty_uncertainty", "total_difficulty_soft_uncertainty",
    "total_difficulty_risk", "total_difficulty_defender_pressure", "total_difficulty_swing",
    "total_ccp_search_difficulty_pure", "total_ccp_search_difficulty_soft",
    "total_ccp_v2_search_difficulty_pure", "total_ccp_v2_search_difficulty_soft",
    "total_ccp_v2_log_search_difficulty_pure", "total_ccp_v2_log_search_difficulty_soft", "total_ccp_v2_log_branch_total",
}
HEADLINE_METRICS = [
    "score", "expected_score", "conversion", "accuracy_wdl", "pq_wdl", "dominance_wdl",
    "mean_es_loss", "rms_es_loss", "error_concentration", "volatility_wdl",
    "total_volatility_wdl", "hard_rap", "soft_rap", "game_accuracy_wdl", "mutual_accuracy_wdl",
    # Difficulty performance: faced by the mover.
    "difficulty_pure_weighted_accuracy", "difficulty_soft_uncertainty_weighted_accuracy",
    # Difficulty exposure: faced by player vs caused for opponent.
    "difficulty_pure_faced", "difficulty_pure_caused",
    "difficulty_soft_uncertainty_faced", "difficulty_soft_uncertainty_caused",
    "legal_rms_loss_faced", "legal_rms_loss_caused",
    "narrowness_faced", "narrowness_caused",
    "effective_good_moves_faced", "effective_good_moves_caused",
    # CCP Search Difficulty: forcing-candidate search burden.
    "ccp_search_difficulty_pure_weighted_accuracy",
    "ccp_search_difficulty_soft_weighted_accuracy",
    "ccp_search_difficulty_pure_faced", "ccp_search_difficulty_pure_caused",
    "ccp_search_difficulty_soft_faced", "ccp_search_difficulty_soft_caused",
    "ccp_immediate_burden_faced", "ccp_immediate_burden_caused",
    "ccp_quiet_to_ccp_burden_faced", "ccp_quiet_to_ccp_burden_caused",
    "ccp_candidate_effective_count_faced", "ccp_candidate_effective_count_caused",
    # CCP v2 recursive candidate-tree burden.
    "ccp_v2_search_difficulty_pure_weighted_accuracy",
    "ccp_v2_search_difficulty_soft_weighted_accuracy",
    "ccp_v2_log_search_difficulty_pure_weighted_accuracy",
    "ccp_v2_log_search_difficulty_soft_weighted_accuracy",
    "ccp_v2_search_difficulty_pure_faced", "ccp_v2_search_difficulty_pure_caused",
    "ccp_v2_search_difficulty_soft_faced", "ccp_v2_search_difficulty_soft_caused",
    "ccp_v2_log_search_difficulty_pure_faced", "ccp_v2_log_search_difficulty_pure_caused",
    "ccp_v2_log_search_difficulty_soft_faced", "ccp_v2_log_search_difficulty_soft_caused",
    "ccp_v2_log_search_difficulty_soft_weighted_accuracy",
    "ccp_v2_max_chain_length_faced", "ccp_v2_max_chain_length_caused",
    "ccp_v2_quiet_pause_burden_faced", "ccp_v2_quiet_pause_burden_caused",
    "ccp_v2_branch_total_faced", "ccp_v2_branch_total_caused",
    "ccp_v2_branch_effective_count_faced", "ccp_v2_branch_effective_count_caused",
    "ccp_v2_nodes_searched_faced", "ccp_v2_nodes_searched_caused",
    "ccp_v2_leaf_count_faced", "ccp_v2_leaf_count_caused",
    "ccp_v2_probe_eval_attempts_faced", "ccp_v2_probe_eval_attempts_caused",
    "ccp_v2_eval_attempts_faced", "ccp_v2_eval_attempts_caused",
    "ccp_v2_total_two_stage_eval_attempts_faced", "ccp_v2_total_two_stage_eval_attempts_caused",
    "ccp_v2_probe_root_branch_count_faced", "ccp_v2_probe_root_branch_count_caused",
    "ccp_v2_confirm_root_moves_selected_faced", "ccp_v2_confirm_root_moves_selected_caused",
    "ccp_v2_confirm_share_of_probe_branches_faced", "ccp_v2_confirm_share_of_probe_branches_caused",
    # DPQ / Pressure Yield headline metrics.
    "difficulty_soft_uncertainty_caused_share",
    "difficulty_soft_uncertainty_dpq",
    "difficulty_soft_uncertainty_pressure_yield_suffered",
    "difficulty_soft_uncertainty_pressure_yield_caused",
    "ccp_search_difficulty_pure_caused_share",
    "ccp_search_difficulty_pure_dpq",
    "ccp_search_difficulty_pure_pressure_yield_suffered",
    "ccp_search_difficulty_pure_pressure_yield_caused",
    "ccp_search_difficulty_soft_caused_share",
    "ccp_search_difficulty_soft_dpq",
    "ccp_search_difficulty_soft_pressure_yield_suffered",
    "ccp_search_difficulty_soft_pressure_yield_caused",
    "ccp_v2_log_search_difficulty_soft_caused_share",
    "ccp_v2_log_search_difficulty_soft_dpq",
    "ccp_v2_log_search_difficulty_soft_pressure_yield_suffered",
    "ccp_v2_log_search_difficulty_soft_pressure_yield_caused",
]

ROOT_BRANCH_FILE_STEMS = {
    "root_branch_summary": "ccp_v2_root_branch_summary",
    "root_branch_ply_summary": "ccp_v2_root_branch_ply_summary",
    "root_branch_top_moves": "ccp_v2_root_branch_top_moves",
    "root_branch_payoff_moves": "ccp_v2_root_branch_payoff_moves",
    "root_branch_workload_rows": "ccp_v2_root_branch_workload_rows",
}


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
            out.append(float(v))
        except Exception:
            pass
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


def safe_float(x: Any) -> Optional[float]:
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def safe_ratio(a: Any, b: Any) -> Optional[float]:
    a = safe_float(a)
    b = safe_float(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def safe_diff(a: Any, b: Any) -> Optional[float]:
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
        if base in {"effective_good_moves", "effective_good_moves_entropy", "ccp_v2_branch_effective_count"}:
            return "lower_means_narrower_or_more_selective"
        if base.startswith("total_difficulty_") or base.startswith("total_ccp_"):
            return "higher_is_more_exposure"
        # v4.7 reporters now include many CCP-v2 faced/caused exposure and workload metrics.
        # Treat these as difficulty/workload exposure, not playing-strength metrics.
        if base in HIGHER_IS_HARDER or base.startswith("ccp_v2_") or base.startswith("ccp_"):
            return "higher_is_harder"
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


def better_player_by_direction(metric_key: str, main_name: str, main_value: Any, opponent_name: str, opponent_value: Any) -> str:
    mv = safe_float(main_value)
    ov = safe_float(opponent_value)
    if mv is None or ov is None:
        return ""
    d = metric_direction(metric_key)
    if d == "higher_is_better":
        if mv > ov:
            return main_name
        if ov > mv:
            return opponent_name
        return "equal"
    if d == "lower_is_better":
        if mv < ov:
            return main_name
        if ov < mv:
            return opponent_name
        return "equal"
    return ""


def interpretation_warning(metric_key: str, main_value: Any, opponent_value: Any) -> str:
    warnings: List[str] = []
    key = str(metric_key)
    if key.endswith("_pressure_yield_suffered"):
        warnings.append("Pressure Yield Suffered is difficulty/pressure-weighted ES loss on the player's own moves; lower is better.")
    if key.endswith("_pressure_yield_caused"):
        warnings.append("Pressure Yield Caused is opponent ES loss weighted by pressure attributed to this player; higher means more pressure converted into opponent loss.")
    if key.endswith("_dpq"):
        warnings.append("DPQ = player's mean caused pressure × match mean caused pressure; use as pressure/style quality, not direct accuracy.")
    if key.endswith("_caused_share"):
        warnings.append("Caused share is proportion of match pressure caused; it is a style/asymmetry metric, not automatically better play.")
    mv = safe_float(main_value)
    ov = safe_float(opponent_value)
    if key in SIGNED_OR_ZERO_CROSSING:
        warnings.append("Signed or zero-crossing metric; differences are usually more meaningful than ratios.")
    if mv == 0 or ov == 0:
        warnings.append("One value is zero; one directional ratio is undefined.")
    if mv is not None and ov is not None and (mv < 0 or ov < 0):
        warnings.append("Negative value present; ratio interpretation is unstable.")
    if key in HIGHER_IS_HARDER or (key.endswith("_faced") and key.rsplit("_", 1)[0] in HIGHER_IS_HARDER) or (key.endswith("_caused") and key.rsplit("_", 1)[0] in HIGHER_IS_HARDER):
        warnings.append("Higher means harder/more complex, not necessarily better play.")
    if key in LOWER_IS_BROADER:
        warnings.append("Lower usually means narrower / fewer effective good moves, not necessarily worse play.")
    return " ".join(warnings)


def find_match_file_groups(input_dir: str) -> List[Dict[str, Any]]:
    input_dir_p = Path(input_dir)
    all_files = sorted(input_dir_p.glob("*_all_metrics_3source.csv"))
    groups: List[Dict[str, Any]] = []
    for all_path in all_files:
        prefix = all_path.name.replace("_all_metrics_3source.csv", "")
        ratio_path = input_dir_p / f"{prefix}_metric_ratios.csv"
        game_path = input_dir_p / f"{prefix}_game_summary_readable.csv"
        m = re.match(r"^(\d+)_([^_]+)", prefix)
        if m:
            match_no = int(m.group(1))
            match_slug = m.group(2)
        else:
            match_no = len(groups) + 1
            match_slug = prefix
        group = {
            "match_no": match_no,
            "match_slug": match_slug,
            "match_name": match_slug.replace("-", " ").title(),
            "prefix": prefix,
            "all_metrics": all_path,
            "metric_ratios": ratio_path if ratio_path.exists() else None,
            "game_summary": game_path if game_path.exists() else None,
        }
        # Optional v4.7 root-branch summary outputs. These are diagnostic
        # search-shape tables, not match/player strength metrics.
        for key, stem in ROOT_BRANCH_FILE_STEMS.items():
            p = input_dir_p / f"{prefix}_{stem}.csv"
            group[key] = p if p.exists() else None
        groups.append(group)
    groups.sort(key=lambda x: x["match_no"])
    return groups


def normalize_all_metrics(df: pd.DataFrame, main_player: str, match_info: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        metric_key = r.get("metric_key")
        metric = r.get("metric")
        definition = r.get("definition", "")
        aggregation = r.get("aggregation", "")
        direction = r.get("direction", metric_direction(metric_key))
        a_name = r.get("player_A_name")
        b_name = r.get("player_B_name")
        a_value = r.get("player_A_value")
        a_sd = r.get("player_A_sd")
        b_value = r.get("player_B_value")
        b_sd = r.get("player_B_sd")
        both_value = r.get("both_players_value")
        both_sd = r.get("both_players_sd")
        if pd.notna(a_name) and str(a_name) == main_player:
            main_value, main_sd = a_value, a_sd
            opponent_name, opponent_value, opponent_sd = b_name, b_value, b_sd
        elif pd.notna(b_name) and str(b_name) == main_player:
            main_value, main_sd = b_value, b_sd
            opponent_name, opponent_value, opponent_sd = a_name, a_value, a_sd
        else:
            main_value, main_sd = None, None
            opponent_name, opponent_value, opponent_sd = None, None, None
        rows.append({
            **match_info,
            "metric_key": metric_key,
            "metric": metric,
            "definition": definition,
            "aggregation": aggregation,
            "direction": direction,
            "main_player_name": main_player,
            "main_player_value": main_value,
            "main_player_sd": main_sd,
            "opponent_name": opponent_name,
            "opponent_value": opponent_value,
            "opponent_sd": opponent_sd,
            "both_players_value": both_value,
            "both_players_sd": both_sd,
        })
    return pd.DataFrame(rows)


def make_metric_ratios_from_run_all(run_all: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, r in run_all.iterrows():
        key = r.get("metric_key")
        main_name = r.get("main_player_name")
        opponent_name = r.get("opponent_name")
        mv = r.get("main_player_value")
        ov = r.get("opponent_value")
        msd = r.get("main_player_sd")
        osd = r.get("opponent_sd")
        rows.append({
            "run_name": r.get("run_name"), "match_no": r.get("match_no"),
            "match_slug": r.get("match_slug"), "match_name": r.get("match_name"),
            "metric_key": key, "metric": r.get("metric"), "aggregation": r.get("aggregation"),
            "direction": metric_direction(key), "main_player_name": main_name,
            "main_player_value": mv, "main_player_sd": msd,
            "opponent_name": opponent_name, "opponent_value": ov, "opponent_sd": osd,
            "both_players_value": r.get("both_players_value"), "both_players_sd": r.get("both_players_sd"),
            "main_over_opponent": safe_ratio(mv, ov), "opponent_over_main": safe_ratio(ov, mv),
            "difference_main_minus_opponent": safe_diff(mv, ov),
            "difference_opponent_minus_main": safe_diff(ov, mv),
            "percent_advantage_main_vs_opponent": pct_advantage(mv, ov),
            "percent_advantage_opponent_vs_main": pct_advantage(ov, mv),
            "sd_main_over_opponent": safe_ratio(msd, osd), "sd_opponent_over_main": safe_ratio(osd, msd),
            "sd_difference_main_minus_opponent": safe_diff(msd, osd),
            "sd_difference_opponent_minus_main": safe_diff(osd, msd),
            "better_player_by_direction": better_player_by_direction(key, main_name, mv, opponent_name, ov),
            "interpretation_warning": interpretation_warning(key, mv, ov),
        })
    return pd.DataFrame(rows)


def build_run_summary_by_match(run_all: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for match_no, g in run_all.groupby("match_no"):
        first = g.iloc[0]
        row: Dict[str, Any] = {
            "run_name": first.get("run_name"), "match_no": match_no,
            "match_slug": first.get("match_slug"), "match_name": first.get("match_name"),
            "main_player_name": first.get("main_player_name"),
        }
        opp_names = [x for x in g["opponent_name"].dropna().unique().tolist() if str(x).strip()]
        row["opponent_name"] = opp_names[0] if opp_names else None
        for key in HEADLINE_METRICS:
            sub = g[g["metric_key"] == key]
            if sub.empty:
                continue
            r = sub.iloc[0]
            row[f"{key}_main"] = r.get("main_player_value")
            row[f"{key}_main_sd"] = r.get("main_player_sd")
            row[f"{key}_opponent"] = r.get("opponent_value")
            row[f"{key}_opponent_sd"] = r.get("opponent_sd")
            row[f"{key}_both"] = r.get("both_players_value")
            row[f"{key}_both_sd"] = r.get("both_players_sd")
            row[f"{key}_main_over_opponent"] = safe_ratio(r.get("main_player_value"), r.get("opponent_value"))
            row[f"{key}_sd_main_over_opponent"] = safe_ratio(r.get("main_player_sd"), r.get("opponent_sd"))
            row[f"{key}_difference_main_minus_opponent"] = safe_diff(r.get("main_player_value"), r.get("opponent_value"))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("match_no")


def build_run_summary_overall(run_all: pd.DataFrame, run_name: str, main_player: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for key, g in run_all.groupby("metric_key"):
        metric = g.iloc[0].get("metric")
        aggregation = g.iloc[0].get("aggregation")
        direction = metric_direction(key)
        main_vals = g["main_player_value"].tolist()
        opp_vals = g["opponent_value"].tolist()
        both_vals = g["both_players_value"].tolist()
        main_sds = g["main_player_sd"].tolist()
        opp_sds = g["opponent_sd"].tolist()
        both_sds = g["both_players_sd"].tolist()
        if key in SUM_METRICS or aggregation == "sum":
            main_overall = sum(clean_values(main_vals)) if clean_values(main_vals) else None
            opp_overall = sum(clean_values(opp_vals)) if clean_values(opp_vals) else None
            both_overall = sum(clean_values(both_vals)) if clean_values(both_vals) else None
            aggregation_across = "sum"
        else:
            main_overall = mean(main_vals)
            opp_overall = mean(opp_vals)
            both_overall = mean(both_vals)
            aggregation_across = "mean"
        rows.append({
            "run_name": run_name, "metric_key": key, "metric": metric,
            "aggregation_across_matches": aggregation_across, "direction": direction,
            "main_player_name": main_player, "main_player_overall_value": main_overall,
            "main_player_match_to_match_sd": pstdev(main_vals),
            "main_player_mean_of_match_sds": mean(main_sds),
            "opponent_overall_value": opp_overall,
            "opponent_match_to_match_sd": pstdev(opp_vals),
            "opponent_mean_of_match_sds": mean(opp_sds),
            "both_players_overall_value": both_overall,
            "both_players_match_to_match_sd": pstdev(both_vals),
            "both_players_mean_of_match_sds": mean(both_sds),
            "main_over_opponent": safe_ratio(main_overall, opp_overall),
            "opponent_over_main": safe_ratio(opp_overall, main_overall),
            "difference_main_minus_opponent": safe_diff(main_overall, opp_overall),
            "sd_mean_main_over_opponent": safe_ratio(mean(main_sds), mean(opp_sds)),
            "sd_mean_difference_main_minus_opponent": safe_diff(mean(main_sds), mean(opp_sds)),
            "better_player_by_direction": better_player_by_direction(key, main_player, main_overall, "Opponents", opp_overall),
            "interpretation_warning": interpretation_warning(key, main_overall, opp_overall),
        })
    return pd.DataFrame(rows)


def normalize_game_summary(df: pd.DataFrame, main_player: str, match_info: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        white = r.get("white")
        black = r.get("black")
        main_is_white = str(white) == main_player
        main_is_black = str(black) == main_player
        if main_is_white:
            opponent, main_side, opponent_side = black, "White", "Black"
            main_suffix, opp_suffix = "white", "black"
        elif main_is_black:
            opponent, main_side, opponent_side = white, "Black", "White"
            main_suffix, opp_suffix = "black", "white"
        else:
            opponent, main_side, opponent_side = None, None, None
            main_suffix, opp_suffix = None, None
        row: Dict[str, Any] = {
            **match_info, "game_id": r.get("game_id"), "white": white, "black": black,
            "result": r.get("result"), "plies": r.get("plies"),
            "main_player_name": main_player, "main_side": main_side,
            "opponent_name": opponent, "opponent_side": opponent_side,
        }
        for col in df.columns:
            if main_suffix and col.endswith(f"_{main_suffix}"):
                base = col[:-(len(main_suffix) + 1)]
                row[f"main_{base}"] = r.get(col)
            elif opp_suffix and col.endswith(f"_{opp_suffix}"):
                base = col[:-(len(opp_suffix) + 1)]
                row[f"opponent_{base}"] = r.get(col)
            elif col.endswith("_game") or col.startswith("game_") or col in {"game_accuracy", "mutual_accuracy", "mean_es_loss_game", "rms_es_loss_game", "conversion_game", "volatility_game", "total_volatility_game"}:
                row[col] = r.get(col)
        rows.append(row)
    return pd.DataFrame(rows)


def make_per_game_ratios(run_game: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    # Dynamic: any main_X with a matching opponent_X becomes comparable.
    main_cols = [c for c in run_game.columns if c.startswith("main_") and c not in {"main_player_name", "main_side"}]
    for _, r in run_game.iterrows():
        for mcol in main_cols:
            base = mcol.replace("main_", "", 1)
            ocol = f"opponent_{base}"
            if ocol not in run_game.columns:
                continue
            mv = r.get(mcol)
            ov = r.get(ocol)
            if safe_float(mv) is None and safe_float(ov) is None:
                continue
            rows.append({
                "run_name": r.get("run_name"), "match_no": r.get("match_no"),
                "match_slug": r.get("match_slug"), "match_name": r.get("match_name"),
                "game_id": r.get("game_id"), "metric": base, "direction": metric_direction(base),
                "main_player_name": r.get("main_player_name"), "opponent_name": r.get("opponent_name"),
                "main_value": mv, "opponent_value": ov,
                "main_over_opponent": safe_ratio(mv, ov), "opponent_over_main": safe_ratio(ov, mv),
                "difference_main_minus_opponent": safe_diff(mv, ov),
                "percent_advantage_main_vs_opponent": pct_advantage(mv, ov),
                "interpretation_warning": interpretation_warning(base, mv, ov),
            })
    return pd.DataFrame(rows)



def add_match_info(df: pd.DataFrame, match_info: Dict[str, Any]) -> pd.DataFrame:
    """Return a copy of a per-match diagnostic table with run/match columns prepended."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for key in ["run_name", "match_no", "match_slug", "match_name"]:
        out.insert(0, key, match_info.get(key))
    return out


def combine_optional_match_tables(groups: List[Dict[str, Any]], table_key: str, run_name: str) -> pd.DataFrame:
    """Combine optional v4.7 root-branch report tables when present."""
    parts: List[pd.DataFrame] = []
    for g in groups:
        path = g.get(table_key)
        if path is None:
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        match_info = {
            "run_name": run_name,
            "match_no": g.get("match_no"),
            "match_slug": g.get("match_slug"),
            "match_name": g.get("match_name"),
        }
        parts.append(add_match_info(df, match_info))
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def build_root_branch_by_match(root_ply: pd.DataFrame) -> pd.DataFrame:
    """Summarize run-level v4.7 root-branch ply summary by match.

    This uses the reporter's one-row-per-ply root-branch summary, so it avoids
    recomputing branch internals while still giving a compact across-match view.
    """
    if root_ply is None or root_ply.empty or "match_no" not in root_ply.columns:
        return pd.DataFrame()

    def sum_clean(s: Iterable[Any]) -> Optional[float]:
        vals = clean_values(s)
        return sum(vals) if vals else None

    rows: List[Dict[str, Any]] = []
    for match_no, g in root_ply.groupby("match_no", dropna=True):
        first = g.iloc[0]
        rows.append({
            "run_name": first.get("run_name"),
            "match_no": match_no,
            "match_slug": first.get("match_slug"),
            "match_name": first.get("match_name"),
            "plies": len(g),
            "mean_probe_branch_count": mean(g.get("probe_branch_count", [])),
            "mean_confirm_branch_count": mean(g.get("confirm_branch_count", [])),
            "mean_confirm_share_of_probe": mean(g.get("confirm_share_of_probe", [])),
            "mean_probe_positive_payoff_count": mean(g.get("probe_positive_payoff_count", [])),
            "mean_confirm_positive_payoff_count": mean(g.get("confirm_positive_payoff_count", [])),
            "mean_confirm_ccp_count": mean(g.get("confirm_ccp_count", [])),
            "mean_confirm_quiet_count": mean(g.get("confirm_quiet_count", [])),
            "mean_confirm_total_child_nodes_searched": mean(g.get("confirm_total_child_nodes_searched", [])),
            "mean_confirm_total_child_leaf_count": mean(g.get("confirm_total_child_leaf_count", [])),
            "total_confirm_child_nodes_searched": sum_clean(g.get("confirm_total_child_nodes_searched", [])),
            "total_confirm_child_leaf_count": sum_clean(g.get("confirm_total_child_leaf_count", [])),
            "mean_confirm_max_child_chain_length": mean(g.get("confirm_max_child_chain_length", [])),
            "max_confirm_max_child_chain_length": max(clean_values(g.get("confirm_max_child_chain_length", []))) if clean_values(g.get("confirm_max_child_chain_length", [])) else None,
            "mean_confirm_branch_score_log": mean(g.get("confirm_mean_branch_score_log", [])),
            "mean_confirm_max_branch_score_log": mean(g.get("confirm_max_branch_score_log", [])),
            "mean_played_probe_rank": mean(g.get("played_probe_rank", [])),
            "mean_played_confirm_rank": mean(g.get("played_confirm_rank", [])),
            "played_selected_for_confirm_rate": mean(g.get("played_selected_for_confirm", [])),
            "mean_wdl_es_loss": mean(g.get("wdl_es_loss", [])),
            "mean_wdl_move_accuracy": mean(g.get("wdl_move_accuracy", [])),
        })
    return pd.DataFrame(rows).sort_values("match_no")


def sort_root_branch_table(df: pd.DataFrame, kind: str, top_n: Optional[int] = None) -> pd.DataFrame:
    """Sort combined root-branch diagnostic tables using their natural priority."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if kind == "top_moves":
        sort_cols = [c for c in ["branch_score_log", "branch_score"] if c in out.columns]
    elif kind == "payoff_moves":
        sort_cols = [c for c in ["delayed_payoff", "branch_score_log", "payoff_depth"] if c in out.columns]
    elif kind == "workload_rows":
        sort_cols = [c for c in ["child_leaf_count", "child_nodes_searched", "branch_score_log"] if c in out.columns]
    else:
        sort_cols = []
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")
    if top_n:
        out = out.head(top_n)
    return out.reset_index(drop=True)


def md_table(df: pd.DataFrame, cols: List[str], max_rows: Optional[int] = None, digits: int = 3) -> str:
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return "_No data._"
    x = df[cols].copy()
    if max_rows:
        x = x.head(max_rows)
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]):
            x[c] = x[c].map(lambda v: "" if pd.isna(v) else f"{float(v):.{digits}f}")
    return x.to_markdown(index=False)


def write_markdown(outpath: Path, run_name: str, by_match: pd.DataFrame, overall: pd.DataFrame,
                   root_branch_by_match: Optional[pd.DataFrame] = None,
                   root_branch_top_moves: Optional[pd.DataFrame] = None,
                   root_branch_payoff_moves: Optional[pd.DataFrame] = None,
                   root_branch_workload_rows: Optional[pd.DataFrame] = None) -> None:
    lines: List[str] = []
    lines.append(f"# {run_name} — Combined WDL + Difficulty Run Report")
    lines.append("")
    lines.append("This report combines match-level Stockfish WDL, all-legal-move difficulty, and CCP Search Difficulty reports into one run-level package.")
    lines.append("")
    lines.append("## Match Headline Summary")
    lines.append("")
    headline_cols = [
        "match_no", "match_name", "opponent_name", "score_main", "score_opponent",
        "accuracy_wdl_main", "accuracy_wdl_opponent", "mean_es_loss_main", "mean_es_loss_opponent",
        "rms_es_loss_main", "rms_es_loss_opponent",
        "difficulty_pure_faced_main", "difficulty_pure_faced_opponent",
        "difficulty_pure_caused_main", "difficulty_pure_caused_opponent",
        "difficulty_soft_uncertainty_faced_main", "difficulty_soft_uncertainty_faced_opponent",
        "difficulty_soft_uncertainty_caused_main", "difficulty_soft_uncertainty_caused_opponent",
        "difficulty_soft_uncertainty_weighted_accuracy_main", "difficulty_soft_uncertainty_weighted_accuracy_opponent",
        "narrowness_caused_main", "narrowness_caused_opponent",
        "effective_good_moves_caused_main", "effective_good_moves_caused_opponent",
        "ccp_search_difficulty_pure_faced_main", "ccp_search_difficulty_pure_faced_opponent",
        "ccp_search_difficulty_pure_caused_main", "ccp_search_difficulty_pure_caused_opponent",
        "ccp_search_difficulty_soft_faced_main", "ccp_search_difficulty_soft_faced_opponent",
        "ccp_search_difficulty_soft_caused_main", "ccp_search_difficulty_soft_caused_opponent",
        "ccp_search_difficulty_soft_weighted_accuracy_main", "ccp_search_difficulty_soft_weighted_accuracy_opponent",
        "ccp_immediate_burden_faced_main", "ccp_immediate_burden_faced_opponent",
        "ccp_quiet_to_ccp_burden_faced_main", "ccp_quiet_to_ccp_burden_faced_opponent",
        "ccp_v2_search_difficulty_pure_faced_main", "ccp_v2_search_difficulty_pure_faced_opponent",
        "ccp_v2_search_difficulty_pure_caused_main", "ccp_v2_search_difficulty_pure_caused_opponent",
        "ccp_v2_search_difficulty_soft_faced_main", "ccp_v2_search_difficulty_soft_faced_opponent",
        "ccp_v2_search_difficulty_soft_caused_main", "ccp_v2_search_difficulty_soft_caused_opponent",
        "ccp_v2_search_difficulty_soft_weighted_accuracy_main", "ccp_v2_search_difficulty_soft_weighted_accuracy_opponent",
        "ccp_v2_log_search_difficulty_pure_faced_main", "ccp_v2_log_search_difficulty_pure_faced_opponent",
        "ccp_v2_log_search_difficulty_soft_faced_main", "ccp_v2_log_search_difficulty_soft_faced_opponent",
        "ccp_v2_log_search_difficulty_soft_weighted_accuracy_main", "ccp_v2_log_search_difficulty_soft_weighted_accuracy_opponent",
        "ccp_v2_max_chain_length_faced_main", "ccp_v2_max_chain_length_faced_opponent",
        "ccp_v2_quiet_pause_burden_faced_main", "ccp_v2_quiet_pause_burden_faced_opponent",
        "ccp_v2_branch_total_faced_main", "ccp_v2_branch_total_faced_opponent",
        "difficulty_soft_uncertainty_caused_share_main", "difficulty_soft_uncertainty_caused_share_opponent",
        "difficulty_soft_uncertainty_dpq_main", "difficulty_soft_uncertainty_dpq_opponent",
        "difficulty_soft_uncertainty_pressure_yield_suffered_main", "difficulty_soft_uncertainty_pressure_yield_suffered_opponent",
        "difficulty_soft_uncertainty_pressure_yield_caused_main", "difficulty_soft_uncertainty_pressure_yield_caused_opponent",
        "ccp_search_difficulty_pure_caused_share_main", "ccp_search_difficulty_pure_caused_share_opponent",
        "ccp_search_difficulty_pure_dpq_main", "ccp_search_difficulty_pure_dpq_opponent",
        "ccp_search_difficulty_pure_pressure_yield_suffered_main", "ccp_search_difficulty_pure_pressure_yield_suffered_opponent",
        "ccp_search_difficulty_pure_pressure_yield_caused_main", "ccp_search_difficulty_pure_pressure_yield_caused_opponent",
        "ccp_v2_log_search_difficulty_soft_caused_share_main", "ccp_v2_log_search_difficulty_soft_caused_share_opponent",
        "ccp_v2_log_search_difficulty_soft_dpq_main", "ccp_v2_log_search_difficulty_soft_dpq_opponent",
        "ccp_v2_log_search_difficulty_soft_pressure_yield_suffered_main", "ccp_v2_log_search_difficulty_soft_pressure_yield_suffered_opponent",
        "ccp_v2_log_search_difficulty_soft_pressure_yield_caused_main", "ccp_v2_log_search_difficulty_soft_pressure_yield_caused_opponent",
        "conversion_main", "conversion_opponent",
    ]
    lines.append(md_table(by_match, headline_cols, digits=3))
    lines.append("")
    lines.append("## Overall Run Metrics")
    lines.append("")
    overall_cols = [
        "metric", "aggregation_across_matches", "direction",
        "main_player_overall_value", "main_player_match_to_match_sd", "main_player_mean_of_match_sds",
        "opponent_overall_value", "opponent_match_to_match_sd", "opponent_mean_of_match_sds",
        "both_players_overall_value", "both_players_match_to_match_sd", "both_players_mean_of_match_sds",
        "main_over_opponent", "difference_main_minus_opponent", "better_player_by_direction", "interpretation_warning",
    ]
    lines.append(md_table(overall, overall_cols, digits=3))
    lines.append("")
    if root_branch_by_match is not None and not root_branch_by_match.empty:
        lines.append("## CCP v2 Root-Branch Diagnostics by Match")
        lines.append("")
        lines.append("These rows summarize the v4.7 root-branch diagnostic tables. They describe probe/confirm search coverage and workload, not direct playing strength.")
        lines.append("")
        rb_cols = [
            "match_no", "match_name", "plies",
            "mean_probe_branch_count", "mean_confirm_branch_count", "mean_confirm_share_of_probe",
            "mean_confirm_positive_payoff_count", "mean_confirm_ccp_count", "mean_confirm_quiet_count",
            "mean_confirm_total_child_leaf_count", "mean_confirm_max_child_chain_length",
            "mean_confirm_branch_score_log", "mean_played_confirm_rank", "played_selected_for_confirm_rate",
        ]
        lines.append(md_table(root_branch_by_match, rb_cols, digits=3))
        lines.append("")

    if root_branch_top_moves is not None and not root_branch_top_moves.empty:
        lines.append("## Highest Confirmed CCP v2 Root Branches Across Run")
        lines.append("")
        top_cols = [
            "match_no", "match_name", "game_id", "ply", "move_no", "player",
            "move_uci", "move_san", "root_played_move", "is_ccp",
            "branch_score_log", "child_leaf_count", "child_max_chain_length",
            "local_loss_vs_best", "delayed_payoff", "wdl_es_loss", "wdl_move_accuracy",
        ]
        lines.append(md_table(root_branch_top_moves, top_cols, max_rows=20, digits=4))
        lines.append("")

    if root_branch_payoff_moves is not None and not root_branch_payoff_moves.empty:
        lines.append("## Confirmed CCP v2 Positive/Delayed-Payoff Root Branches Across Run")
        lines.append("")
        payoff_cols = [
            "match_no", "match_name", "game_id", "ply", "move_no", "player",
            "move_uci", "move_san", "root_played_move", "is_ccp",
            "delayed_payoff", "payoff_depth", "branch_score_log",
            "child_leaf_count", "child_max_chain_length", "wdl_es_loss",
        ]
        lines.append(md_table(root_branch_payoff_moves, payoff_cols, max_rows=20, digits=4))
        lines.append("")

    if root_branch_workload_rows is not None and not root_branch_workload_rows.empty:
        lines.append("## Highest CCP v2 Root-Branch Workload Rows Across Run")
        lines.append("")
        workload_cols = [
            "match_no", "match_name", "game_id", "ply", "move_no", "player",
            "move_uci", "move_san", "root_played_move", "is_ccp",
            "child_leaf_count", "child_nodes_searched", "child_max_chain_length",
            "child_quiet_pause_burden", "branch_score_log", "wdl_es_loss",
        ]
        lines.append(md_table(root_branch_workload_rows, workload_cols, max_rows=20, digits=4))
        lines.append("")

    lines.append("## Ratio Reading Guide")
    lines.append("")
    lines.append("- Ratio columns compare the main player to the opponent or opponent pool.")
    lines.append("- SD ratios are included where both SDs are numeric and non-zero.")
    lines.append("- For signed metrics such as Dominance and Conversion, differences are usually more meaningful than ratios.")
    lines.append("- Faced difficulty is measured before a player's own move. Caused difficulty is attributed one ply backward to the previous mover, meaning immediate opponent difficulty caused. Higher difficulty is harder/narrower exposure, not automatically better play.")
    lines.append("- CCP Search Difficulty measures Checks/Captures/Promotions forcing-candidate search burden. CCP weighted accuracy is a performance-under-CCP-pressure metric; CCP faced/caused rows are exposure/style metrics.")
    lines.append("- CCP v2 Search Difficulty adds recursive candidate-tree measures: chain length, quiet-pause burden, branch total, branch ambiguity, and branch effective count.")
    lines.append("- CCP v2 Log Search Difficulty uses log1p(raw CCP-v2 difficulty) to compress outliers and is the preferred human-readable stability check across high-depth/high-call settings.")
    lines.append("- Root-branch summary tables come from reporter v4.7. They show probe/confirm coverage, top confirmed root branches, positive/delayed-payoff branches, and the largest subtree workload rows across the run.")
    lines.append("- Difficulty Caused Share shows the proportion of total match pressure caused by each player; it is a style/asymmetry metric.")
    lines.append("- Difficulty Pressure Quality (DPQ) = player mean caused pressure × match mean caused pressure. Use it as a match-length-neutral pressure-quality analogue to PQ.")
    lines.append("- Pressure Yield Suffered is pressure-weighted ES loss on the player's own moves; lower is better. Pressure Yield Caused is opponent ES loss weighted by pressure attributed to the player; higher means the caused pressure produced more opponent loss.")
    lines.append("")
    outpath.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine multiple WDL + difficulty match reports into a run-level report.")
    parser.add_argument("--input-dir", required=True, help="Directory containing *_all_metrics_3source.csv, *_metric_ratios.csv, and *_game_summary_readable.csv files.")
    parser.add_argument("--main-player", required=True, help="Exact main player name as it appears in the CSV files.")
    parser.add_argument("--run-name", default="Combined WDL + Difficulty Run", help="Run name for output files.")
    parser.add_argument("--outdir", default="combined_run_report_v4", help="Output directory.")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    groups = find_match_file_groups(args.input_dir)
    if not groups:
        raise SystemExit("No *_all_metrics_3source.csv files found.")

    run_all_parts: List[pd.DataFrame] = []
    run_game_parts: List[pd.DataFrame] = []
    for g in groups:
        match_info = {"run_name": args.run_name, "match_no": g["match_no"], "match_slug": g["match_slug"], "match_name": g["match_name"]}
        all_df = pd.read_csv(g["all_metrics"])
        run_all_parts.append(normalize_all_metrics(all_df, args.main_player, match_info))
        if g["game_summary"] is not None and Path(g["game_summary"]).exists():
            game_df = pd.read_csv(g["game_summary"])
            run_game_parts.append(normalize_game_summary(game_df, args.main_player, match_info))

    run_all = pd.concat(run_all_parts, ignore_index=True)
    run_metric_ratios = make_metric_ratios_from_run_all(run_all)
    run_summary_by_match = build_run_summary_by_match(run_all)
    run_summary_overall = build_run_summary_overall(run_all, args.run_name, args.main_player)

    if run_game_parts:
        run_game_summary = pd.concat(run_game_parts, ignore_index=True)
        run_game_metric_ratios = make_per_game_ratios(run_game_summary)
    else:
        run_game_summary = pd.DataFrame()
        run_game_metric_ratios = pd.DataFrame()

    # Optional reporter v4.7 root-branch diagnostic summary tables.
    run_root_branch_summary = combine_optional_match_tables(groups, "root_branch_summary", args.run_name)
    run_root_branch_ply_summary = combine_optional_match_tables(groups, "root_branch_ply_summary", args.run_name)
    run_root_branch_by_match = build_root_branch_by_match(run_root_branch_ply_summary)
    run_root_branch_top_moves = sort_root_branch_table(
        combine_optional_match_tables(groups, "root_branch_top_moves", args.run_name),
        "top_moves",
    )
    run_root_branch_payoff_moves = sort_root_branch_table(
        combine_optional_match_tables(groups, "root_branch_payoff_moves", args.run_name),
        "payoff_moves",
    )
    run_root_branch_workload_rows = sort_root_branch_table(
        combine_optional_match_tables(groups, "root_branch_workload_rows", args.run_name),
        "workload_rows",
    )

    run_all.to_csv(outdir / "run_all_metrics.csv", index=False)
    run_metric_ratios.to_csv(outdir / "run_metric_ratios.csv", index=False)
    run_summary_by_match.to_csv(outdir / "run_summary_by_match.csv", index=False)
    run_summary_overall.to_csv(outdir / "run_summary_overall.csv", index=False)
    run_game_summary.to_csv(outdir / "run_game_summary.csv", index=False)
    run_game_metric_ratios.to_csv(outdir / "run_game_metric_ratios.csv", index=False)
    if not run_root_branch_summary.empty:
        run_root_branch_summary.to_csv(outdir / "run_ccp_v2_root_branch_summary.csv", index=False)
    if not run_root_branch_ply_summary.empty:
        run_root_branch_ply_summary.to_csv(outdir / "run_ccp_v2_root_branch_ply_summary.csv", index=False)
    if not run_root_branch_by_match.empty:
        run_root_branch_by_match.to_csv(outdir / "run_ccp_v2_root_branch_by_match.csv", index=False)
    if not run_root_branch_top_moves.empty:
        run_root_branch_top_moves.to_csv(outdir / "run_ccp_v2_root_branch_top_moves.csv", index=False)
    if not run_root_branch_payoff_moves.empty:
        run_root_branch_payoff_moves.to_csv(outdir / "run_ccp_v2_root_branch_payoff_moves.csv", index=False)
    if not run_root_branch_workload_rows.empty:
        run_root_branch_workload_rows.to_csv(outdir / "run_ccp_v2_root_branch_workload_rows.csv", index=False)
    write_markdown(
        outdir / "run_article_report.md",
        args.run_name,
        run_summary_by_match,
        run_summary_overall,
        run_root_branch_by_match,
        run_root_branch_top_moves,
        run_root_branch_payoff_moves,
        run_root_branch_workload_rows,
    )

    print("Done.")
    print(f"Run all metrics:          {outdir / 'run_all_metrics.csv'}")
    print(f"Run metric ratios:        {outdir / 'run_metric_ratios.csv'}")
    print(f"Summary by match:         {outdir / 'run_summary_by_match.csv'}")
    print(f"Overall summary:          {outdir / 'run_summary_overall.csv'}")
    print(f"Run game summary:         {outdir / 'run_game_summary.csv'}")
    print(f"Per-game metric ratios:   {outdir / 'run_game_metric_ratios.csv'}")
    if not run_root_branch_summary.empty:
        print(f"Root branch summary:      {outdir / 'run_ccp_v2_root_branch_summary.csv'}")
    if not run_root_branch_ply_summary.empty:
        print(f"Root branch ply summary:  {outdir / 'run_ccp_v2_root_branch_ply_summary.csv'}")
    if not run_root_branch_by_match.empty:
        print(f"Root branch by match:     {outdir / 'run_ccp_v2_root_branch_by_match.csv'}")
    if not run_root_branch_top_moves.empty:
        print(f"Root branch top moves:    {outdir / 'run_ccp_v2_root_branch_top_moves.csv'}")
    if not run_root_branch_payoff_moves.empty:
        print(f"Root branch payoff moves: {outdir / 'run_ccp_v2_root_branch_payoff_moves.csv'}")
    if not run_root_branch_workload_rows.empty:
        print(f"Root branch workloads:    {outdir / 'run_ccp_v2_root_branch_workload_rows.csv'}")
    print(f"Markdown report:          {outdir / 'run_article_report.md'}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Download, split, compare, and package the local activity proxy model."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import platform
try:
    import resource
except ImportError:
    resource = None
import statistics
import sys
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/models"
URL = "https://archive.ics.uci.edu/static/public/357/occupancy+detection.zip"
FEATURES = ["temperature_c", "humidity_pct", "co2_ppm", "humidity_ratio"]
GROUPS = {"train": set(range(2, 9)), "validation": {9, 10, 11}, "test": set(range(12, 19))}


def rows_from_zip(raw: bytes):
    rows = {}
    for name in ("datatraining.txt", "datatest.txt", "datatest2.txt"):
        for row in csv.reader(io.StringIO(zipfile.ZipFile(io.BytesIO(raw)).read(name).decode("utf-8-sig"))):
            if not row or row[0] == "date":
                continue
            # UCI files contain an initial record ID omitted from the header.
            ts = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            x = [float(row[i]) for i in (2, 3, 5, 6)]
            y = int(row[7])
            rows[(ts, tuple(x), y)] = (ts, x, y)
    return sorted(rows.values(), key=lambda r: r[0])


def metrics(y, pred):
    y, pred = np.asarray(y, dtype=int), np.asarray(pred)
    p = np.where(pred == "UNKNOWN", -1, pred).astype(int)
    covered = p >= 0
    occupied = y == 1
    false_inactive = int(np.sum((pred == 0) & occupied))
    cm = confusion_matrix(y, p, labels=[0, 1, -1]).tolist()
    return {
        "n": int(len(y)), "occupied": int(occupied.sum()), "unoccupied": int((y == 0).sum()),
        "confusion_matrix_rows_true_cols_pred_labels_0_1_unknown": cm,
        "macro_f1_covered": float(f1_score(y[covered], p[covered], average="macro", zero_division=0)) if covered.any() else None,
        "macro_f1_all_rows_unknown_as_error": float(f1_score(y, np.where(p < 0, 2, p), labels=[0, 1], average="macro", zero_division=0)),
        "accuracy_covered": float(np.mean(y[covered] == p[covered])) if covered.any() else None,
        "occupancy_recall_all_rows_unknown_counts_as_miss": float(np.sum((pred == 1) & occupied) / occupied.sum()) if occupied.any() else None,
        "false_inactive_count": false_inactive,
        "false_inactive_rate_of_occupied": float(false_inactive / occupied.sum()) if occupied.any() else None,
        "unknown_count": int((~covered).sum()), "unknown_rate": float((~covered).mean()),
        "coverage": float(covered.mean()),
    }


def apply_operating_point(proba, point):
    score = proba[:, 1]
    uncertain = np.abs(score - point["decision_threshold"]) < point["abstain_margin"]
    return np.where(uncertain, -1, (score >= point["decision_threshold"]).astype(int))


def choose_operating_point(proba, y):
    # Tune the ACTIVE boundary and abstention band on validation only; constrain coverage to >=90%.
    candidates = []
    for threshold in np.arange(0.10, 0.901, 0.01):
        for margin in (0.0, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20):
            point = {"decision_threshold": round(float(threshold), 3), "abstain_margin": margin}
            pred = apply_operating_point(proba, point)
            result = metrics(y, pred)
            key = (result["macro_f1_all_rows_unknown_as_error"], result["occupancy_recall_all_rows_unknown_counts_as_miss"], result["coverage"])
            if result["coverage"] >= 0.90:
                candidates.append((key, point, result))
    best_f1 = max(item[0][0] for item in candidates)
    # A measured abstention band is kept if it stays within one F1 point of the best validated point.
    eligible = [item for item in candidates if item[1]["abstain_margin"] > 0 and item[0][0] >= best_f1 - 0.01]
    best = max(eligible, key=lambda item: (item[1]["abstain_margin"], item[0])) if eligible else max(candidates, key=lambda item: item[0])
    return best[1], best[2]


def latency_ms(fn, n=100):
    samples = []
    for _ in range(5):
        fn()
    for _ in range(n):
        t = time.perf_counter_ns(); fn(); samples.append((time.perf_counter_ns() - t) / 1e6)
    return {"n": n, "median_ms": statistics.median(samples), "p95_ms": float(np.percentile(samples, 95))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="optional local UCI archive (otherwise downloaded)")
    parser.add_argument("--sample-limit", type=int, default=1500, help="TabICL held-out rows per partition")
    parser.add_argument("--skip-tabicl", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    raw = Path(args.data).read_bytes() if args.data else urllib.request.urlopen(URL, timeout=60).read()
    all_rows = rows_from_zip(raw)
    partitions = {name: [r for r in all_rows if r[0].month == 2 and r[0].day in days] for name, days in GROUPS.items()}
    dates = {k: sorted({r[0].date().isoformat() for r in v}) for k, v in partitions.items()}
    assert not (set(dates["train"]) & set(dates["validation"]) or set(dates["train"]) & set(dates["test"]) or set(dates["validation"]) & set(dates["test"]))
    X = {k: np.asarray([r[1] for r in v], dtype=np.float64) for k, v in partitions.items()}
    y = {k: np.asarray([r[2] for r in v], dtype=np.int64) for k, v in partitions.items()}
    models = {
        "random_forest": RandomForestClassifier(n_estimators=250, min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=1),
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
    }
    reports, operating_points = {}, {}
    for name, candidate in models.items():
        started = time.perf_counter(); candidate.fit(X["train"], y["train"]); train_s = time.perf_counter() - started
        point, val_metrics = choose_operating_point(candidate.predict_proba(X["validation"]), y["validation"])
        operating_points[name] = point
        reports[name] = {"train_seconds": train_s, "validation": {**val_metrics, "operating_point_tuned_on_validation": point}}
        reports[name]["warm_batch_1_latency"] = latency_ms(lambda: candidate.predict_proba(X["validation"][:1]))
        reports[name]["warm_batch_128_latency"] = latency_ms(lambda: candidate.predict_proba(X["validation"][:128]))
    # Selection uses validation scores only; held-out days are evaluated after this choice is frozen.
    selected_name = max(models, key=lambda name: (
        reports[name]["validation"]["macro_f1_all_rows_unknown_as_error"],
        reports[name]["validation"]["occupancy_recall_all_rows_unknown_counts_as_miss"],
    ))
    selected_model = models[selected_name]
    selected_point = operating_points[selected_name]
    reports["selection"] = {"selected_model": selected_name, "criterion": "highest validation macro-F1 (unknown counted as error), then occupancy recall; no test results used", "operating_point_criterion": "widest positive abstention band within 0.01 validation macro-F1 of the maximum among >=90% coverage points; then macro-F1, occupancy recall, coverage", "chosen_operating_point": selected_point}
    for name, candidate in models.items():
        pred = apply_operating_point(candidate.predict_proba(X["test"]), operating_points[name])
        reports[name]["test_exploratory"] = metrics(y["test"], pred)
        reports[name]["test_exploratory"]["operating_point_tuned_on_validation"] = operating_points[name]
    reports["co2_rule_1000ppm_test_exploratory"] = metrics(y["test"], (X["test"][:, 2] >= 1000).astype(int))

    tabicl = {"evaluated": False, "reason": "not requested" if args.skip_tabicl else None}
    if not args.skip_tabicl:
        try:
            import torch
            from huggingface_hub import hf_hub_download
            from tabicl import TabICLClassifier
            tab_start = time.perf_counter()
            checkpoint = hf_hub_download(repo_id="jingang/TabICL", filename="tabicl-classifier-v2-20260212.ckpt", revision="4dcd344ece2c00be9e831fdd35bed57b5ad83e19")
            # TabICL conditions on bounded labeled context; all context comes from training days.
            rng = np.random.default_rng(42)
            ctx_ix = rng.choice(len(X["train"]), min(512, len(X["train"])), replace=False)
            clf = TabICLClassifier(model_path=checkpoint, device="cpu", n_estimators=1, n_jobs=1,
                                   use_amp=False, use_fa3=False, random_state=42)
            clf.fit(X["train"][ctx_ix], y["train"][ctx_ix])
            tabicl["checkpoint_fetch_and_context_setup_seconds"] = time.perf_counter() - tab_start
            val_ix = np.linspace(0, len(X["validation"]) - 1, min(args.sample_limit, len(X["validation"])), dtype=int)
            first_inference_start = time.perf_counter_ns()
            clf.predict_proba(X["validation"][val_ix[:1]])
            tabicl["first_single_prediction_ms"] = (time.perf_counter_ns() - first_inference_start) / 1e6
            val_proba = clf.predict_proba(X["validation"][val_ix])
            tabicl_point, tabicl_val = choose_operating_point(val_proba, y["validation"][val_ix])
            tabicl["validation"] = {**tabicl_val, "sampled_rows": len(val_ix), "operating_point_tuned_on_validation": tabicl_point}
            tabicl["warm_latency_batch_1"] = latency_ms(lambda: clf.predict_proba(X["validation"][val_ix[:1]]), n=10)
            for split in ("validation", "test"):
                ix = val_ix if split == "validation" else np.linspace(0, len(X[split]) - 1, min(args.sample_limit, len(X[split])), dtype=int)
                pr = clf.predict_proba(X[split][ix])
                tabicl[split] = metrics(y[split][ix], apply_operating_point(pr, tabicl_point))
                tabicl[split]["sampled_rows"] = len(ix)
                reports[f"random_forest_{split}_same_tabicl_rows"] = metrics(y[split][ix], apply_operating_point(models["random_forest"].predict_proba(X[split][ix]), operating_points["random_forest"]))
                reports[f"logistic_{split}_same_tabicl_rows"] = metrics(y[split][ix], apply_operating_point(models["logistic"].predict_proba(X[split][ix]), operating_points["logistic"]))
                if split == "test":
                    tabicl["warm_latency_batch_32"] = latency_ms(lambda: clf.predict_proba(X[split][ix[:32]]), n=10)
            tabicl["validation"]["operating_point_tuned_on_validation"] = tabicl_point
            tabicl.update({"evaluated": True, "version": "official TabICL @ c91f00df184a5097e584cb376f7e699e9f3444c4", "weights_revision": "4dcd344ece2c00be9e831fdd35bed57b5ad83e19", "checkpoint_sha256": hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest(), "checkpoint_size_bytes": Path(checkpoint).stat().st_size, "checkpoint_license": "BSD-3-Clause (weight card)", "source_license": "BSD-3-Clause", "torch_version": torch.__version__, "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024})
        except Exception as exc:
            tabicl["reason"] = f"{type(exc).__name__}: {exc}"
    reports["tabicl"] = tabicl
    if tabicl.get("evaluated"):
        matched_logistic = reports["logistic_validation_same_tabicl_rows"]["macro_f1_all_rows_unknown_as_error"]
        reports["selection"]["tabicl_matched_validation_macro_f1"] = tabicl["validation"]["macro_f1_all_rows_unknown_as_error"]
        reports["selection"]["logistic_matched_validation_macro_f1"] = matched_logistic
        reports["selection"]["tabicl_adopted"] = bool(
            tabicl["validation"]["macro_f1_all_rows_unknown_as_error"] >= matched_logistic + 0.01
            and tabicl["warm_latency_batch_1"]["p95_ms"] <= 50
            and tabicl["peak_rss_mib"] <= 2048
        )
        reports["selection"]["tabicl_reason"] = "selected candidate did not meet validation quality/CPU latency/resource gate" if not reports["selection"]["tabicl_adopted"] else "meets validation quality/CPU latency/resource gate; RF/logistic artifact retained by current runtime"
    report = {
        "benchmark": "UCI Occupancy Detection, office occupancy proxy; labels are not campus lab activity",
        "data_source": {"url": URL, "doi": "10.24432/C5X01N", "license": "CC BY 4.0", "sha256": hashlib.sha256(raw).hexdigest()},
        "feature_schema": FEATURES,
        "excluded_inputs": ["Light", "record ID", "timestamp", "Occupancy truth outside fit/evaluation", "room/card/scenario/mask/served power"],
        "deduplication": "duplicate records across archive files collapsed by (timestamp, features, label)",
        "partition_method": "sort by actual source timestamp, then keep entire calendar days disjoint; no random adjacent-row split",
        "training": {"random_forest": {"n_estimators": 250, "min_samples_leaf": 2, "class_weight": "balanced", "random_state": 42, "n_jobs": 1}, "logistic": {"scaler": "StandardScaler", "max_iter": 1000, "class_weight": "balanced", "random_state": 42}, "operating_point": "Validation-only ACTIVE threshold and abstention-band grid; require >=90% coverage, maximize macro-F1 with UNKNOWN as error, then choose the widest positive band within 0.01 macro-F1 of the best; remaining ties by macro-F1, occupancy recall, coverage."},
        "tabicl_protocol": {"context_rows": 512, "context_source": "training partition only, deterministic seed 42", "evaluation_rows_per_partition": args.sample_limit, "sample_method": "deterministically evenly spaced by sorted timestamp", "device": "CPU", "n_estimators": 1, "n_jobs": 1},
        "replay_selection": "40 validation rows per classroom: 20 sampled from each truth class with seed 42, then timestamp-sorted; labels used only for offline stratified demo selection and are not included in replay.json or inference",
        "split": {k: {"dates": dates[k], "rows": len(v), "class_counts_0_1": np.bincount(y[k], minlength=2).tolist()} for k, v in partitions.items()},
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scikit_learn": sklearn.__version__, "tabicl": tabicl.get("version", "not evaluated"), "torch": tabicl.get("torch_version", "not installed")},
        "tabicl_weights": {"repo": "jingang/TabICL", "revision": tabicl.get("weights_revision"), "filename": "tabicl-classifier-v2-20260212.ckpt", "sha256": tabicl.get("checkpoint_sha256"), "size_bytes": tabicl.get("checkpoint_size_bytes"), "license": tabicl.get("checkpoint_license")},
        "test_status": "time-disjoint dates, but exploratory draft metrics were inspected before this final model selection; do not describe as untouched final test",
        "models": reports,
        "resource": {"peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024},
        "attribution": "Candanedo, L. M. and Feldheim, V. (2016), Accurate occupancy detection of an office room from light, temperature, humidity and CO2 measurements using statistical learning models, Energy and Buildings 112, 28-39. UCI dataset DOI 10.24432/C5X01N, CC BY 4.0.",
    }
    model_path = OUT / f"activity-{selected_name}.joblib"; joblib.dump(selected_model, model_path)
    artifact_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    model_type = "StandardScaler + LogisticRegression" if selected_name == "logistic" else type(selected_model).__name__
    manifest = {"model_version": f"uci-occ-{selected_name}-2026-10-09", "model_type": model_type, "artifact": model_path.name, "sha256": artifact_hash, "features": FEATURES, "data_source": "UCI Occupancy Detection (office occupancy proxy; CC BY 4.0)", **selected_point, "evaluation": {"validation": reports[selected_name]["validation"], "test_exploratory": reports[selected_name]["test_exploratory"], "scope": report["benchmark"]}}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # Validation labels may select illustrative examples offline; only features/timestamps are published.
    replay = {k: [] for k in ("CR1", "CR2", "CR3")}
    validation = partitions["validation"]
    rng = np.random.default_rng(42)
    for room_ix, room in enumerate(replay):
        chosen = sorted(
            int(i) for label in (0, 1)
            for i in rng.choice([i for i, row in enumerate(validation) if row[2] == label], 20, replace=False)
        )
        for i in chosen:
            ts, x, _label = validation[i]
            replay[room].append({"classroom_id": room, **dict(zip(FEATURES, x)), "observed_at": ts.isoformat(), "source": "RECORDED_REPLAY"})
    (OUT / "replay.json").write_text(json.dumps(replay, indent=2) + "\n")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.activity.model import ActivityModel
    init_start = time.perf_counter(); runtime_model = ActivityModel(); model_init_s = time.perf_counter() - init_start
    if not runtime_model.status()["ready"]:
        raise RuntimeError(f"runtime model failed to load: {runtime_model.status()['fallback_reason']}")
    first_features = {key: replay["CR1"][0][key] for key in FEATURES}
    first_start = time.perf_counter_ns(); runtime_model.predict(first_features)
    first_prediction_ms = (time.perf_counter_ns() - first_start) / 1e6
    runtime_latency = latency_ms(lambda: runtime_model.predict(first_features))
    runtime_eval = {"model_init_seconds_includes_hash_and_artifact_load": model_init_s, "first_prediction_ms": first_prediction_ms, "warm_single_prediction_ms": runtime_latency}
    report["runtime_inference"] = runtime_eval
    manifest["runtime_inference"] = runtime_eval
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (OUT / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"artifact": str(model_path), "sha256": artifact_hash, "selected_model": selected_name, "manifest": str(OUT / "manifest.json"), "report": str(OUT / "evaluation.json"), "tabicl_evaluated": tabicl["evaluated"], "tabicl_reason": tabicl.get("reason")}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generic data analysis for tabular data.

USAGE: python analyze.py --input data.csv --output analysis.json [--top N]

Reads CSV, auto-detects column types, computes statistics,
extracts insights. Outputs structured JSON. Zero dependencies
(python standard library only).
"""

import argparse
import csv
import json
import math
import os
import re
import sys
import warnings
from collections import Counter
from datetime import datetime

DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
    "%m/%d/%Y", "%d/%m/%Y",
    "%Y年%m月%d日", "%Y年%m月",
    "%m月%d日", "%m-%d",
    "%Y%m%d", "%Y%m",
    "%b %d, %Y", "%B %d, %Y",
    "%d %b %Y", "%d %B %Y",
    "%Y-%m", "%Y/%m",
]


def is_numeric(s):
    if s is None:
        return False
    s = str(s).strip().replace(",", "").replace("，", "")
    if not s or s in ("-", "--", "N/A", "n/a", "NA", "null", "None"):
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def to_float(s):
    s = str(s).strip().replace(",", "").replace("，", "")
    return float(s)


def is_time(s):
    if s is None:
        return False
    s = str(s).strip()
    if not s:
        return False
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    # unix timestamp
    try:
        ts = float(s)
        return 1e9 < ts < 2e10
    except ValueError:
        return False


def detect_type(values):
    non_empty = [v for v in values if v is not None and str(v).strip()]
    if not non_empty:
        return "empty"

    numeric_count = sum(1 for v in non_empty if is_numeric(v))
    time_count = sum(1 for v in non_empty if is_time(v))
    n = len(non_empty)

    if time_count / n > 0.8:
        return "time"
    if numeric_count / n > 0.8:
        return "numeric"

    unique_ratio = len(set(str(v).strip() for v in non_empty)) / n
    if unique_ratio < 0.5 or len(set(str(v).strip() for v in non_empty)) <= 20:
        return "categorical"

    return "text"


def compute_percentile(sorted_vals, p):
    if not sorted_vals:
        return 0
    n = len(sorted_vals)
    k = (n - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def compute_stats(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    clean.sort()
    n = len(clean)
    total = sum(clean)
    mean = total / n
    variance = sum((x - mean) ** 2 for x in clean) / n if n > 1 else 0
    std = math.sqrt(variance)
    median = compute_percentile(clean, 50)
    p25 = compute_percentile(clean, 25)
    p75 = compute_percentile(clean, 75)
    iqr = p75 - p25

    skewness = 0
    if std > 0 and n > 2:
        skewness = sum((x - mean) ** 3 for x in clean) / (n * std ** 3)

    return {
        "count": n,
        "sum": round(total, 2),
        "mean": round(mean, 2),
        "median": round(median, 2),
        "std": round(std, 2),
        "min": round(clean[0], 2),
        "max": round(clean[-1], 2),
        "p25": round(p25, 2),
        "p75": round(p75, 2),
        "iqr": round(iqr, 2),
        "skewness": round(skewness, 2),
    }


def detect_trend(values):
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return {"direction": "insufficient_data", "change_pct": None}

    first_third = clean[: len(clean) // 3]
    last_third = clean[-(len(clean) // 3):]
    avg_first = sum(first_third) / len(first_third) if first_third else 0
    avg_last = sum(last_third) / len(last_third) if last_third else 0

    change_pct = round((avg_last - avg_first) / abs(avg_first) * 100, 1) if avg_first != 0 else None

    if change_pct is None:
        direction = "flat"
    elif change_pct > 10:
        direction = "up"
    elif change_pct < -10:
        direction = "down"
    else:
        direction = "flat"

    return {"direction": direction, "change_pct": change_pct}


def analyze_by_category(rows, cat_col, numeric_cols):
    groups = {}
    for row in rows:
        key = str(row.get(cat_col, "")).strip() or "(empty)"
        groups.setdefault(key, []).append(row)

    results = {}
    for key, group_rows in sorted(groups.items(), key=lambda x: -len(x[1])):
        stats = {}
        for nc in numeric_cols:
            vals = []
            for r in group_rows:
                v = r.get(nc)
                if v is not None:
                    vals.append(v)
            if vals:
                stats[nc] = {
                    "count": len(vals),
                    "sum": round(sum(vals), 2),
                    "mean": round(sum(vals) / len(vals), 2),
                    "min": round(min(vals), 2),
                    "max": round(max(vals), 2),
                }
        results[key] = {"row_count": len(group_rows), "stats": stats}

    significant_diffs = []
    if len(results) > 1:
        for nc in numeric_cols:
            means = [
                v["stats"][nc]["mean"] for v in results.values() if nc in v["stats"]
            ]
            if len(means) >= 2:
                overall_range = max(means) - min(means)
                overall_mean = sum(means) / len(means)
                if overall_mean != 0 and overall_range / abs(overall_mean) > 0.2:
                    significant_diffs.append(nc)

    return {"groups": dict(list(results.items())[:15]), "significant_columns": significant_diffs}


def pearson_corr(x_vals, y_vals):
    pairs = [(x, y) for x, y in zip(x_vals, y_vals) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    n = len(pairs)
    sx = sum(p[0] for p in pairs)
    sy = sum(p[1] for p in pairs)
    sxx = sum(p[0] ** 2 for p in pairs)
    syy = sum(p[1] ** 2 for p in pairs)
    sxy = sum(p[0] * p[1] for p in pairs)
    denom = math.sqrt((n * sxx - sx ** 2) * (n * syy - sy ** 2))
    if denom == 0:
        return 0
    return (n * sxy - sx * sy) / denom


def extract_insights(meta, columns, stats_data, category_data, correlation_data, rows):
    insights = []

    for col, st in stats_data.items():
        if st is None:
            continue
        insights.append({
            "type": "summary",
            "text": f"{col}: total={st['sum']}, mean={st['mean']}, range=[{st['min']}, {st['max']}]",
            "priority": 1,
        })

        if st["std"] > 0:
            lower = st["mean"] - 1.5 * st["std"]
            upper = st["mean"] + 1.5 * st["std"]
            outliers = []
            for i, row in enumerate(rows):
                v = row.get(col)
                if v is not None and (v < lower or v > upper):
                    outliers.append({"row": i + 2, "value": round(v, 2)})
            if outliers:
                insights.append({
                    "type": "outlier",
                    "text": f"{col}: {len(outliers)} outliers outside 1.5*std",
                    "detail": outliers[:5],
                    "priority": 3,
                })

        trend = st.get("trend")
        if trend and trend["direction"] != "insufficient_data":
            pct_str = f"{trend['change_pct']}%" if trend["change_pct"] is not None else "N/A"
            insights.append({
                "type": "trend",
                "text": f"{col}: trending {trend['direction']} ({pct_str})",
                "priority": 4,
            })

    for cat_col, cat_result in category_data.items():
        groups = cat_result.get("groups", {})
        if len(groups) < 2:
            continue

        for nc in cat_result.get("significant_columns", []):
            cat_means = {k: v["stats"][nc]["mean"] for k, v in groups.items() if nc in v["stats"]}
            if cat_means:
                best = max(cat_means, key=cat_means.get)
                worst = min(cat_means, key=cat_means.get)
                diff = cat_means[best] - cat_means[worst]
                insights.append({
                    "type": "comparison",
                    "text": f"By {cat_col}, '{best}' leads {nc} (mean={round(cat_means[best], 2)}), '{worst}' trails (mean={round(cat_means[worst], 2)}), gap={round(diff, 2)}",
                    "priority": 4,
                })

    if len(category_data) == 0:
        text_cols = [c["name"] for c in columns if c["type"] == "text" and c["unique_ratio"] > 0.9]
        for col in text_cols[:2]:
            insights.append({
                "type": "note",
                "text": f"{col}: {columns[0]['unique_count']} unique values out of {meta['total_rows']} - likely an ID, excluded from analysis",
                "priority": 1,
            })

    insights.sort(key=lambda x: -x["priority"])
    return insights


def main():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    parser = argparse.ArgumentParser(description="Generic data analysis for tabular data")
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--top", type=int, default=10, help="Max insights")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print(json.dumps({"error": "no headers"}))
            sys.exit(1)
        rows = []
        for row in reader:
            rows.append(row)

    if not rows:
        print(json.dumps({"error": "no data rows"}))
        sys.exit(1)

    headers = list(reader.fieldnames)

    # Filter out completely empty columns
    active_headers = [
        h for h in headers
        if any(str(row.get(h, "")).strip() for row in rows)
    ]

    # Detect column types and parse values
    columns = []
    for col in active_headers:
        raw_values = [row.get(col, "") for row in rows]
        col_type = detect_type(raw_values)

        parsed = []
        for v in raw_values:
            v = str(v).strip() if v else None
            if col_type == "numeric" and is_numeric(v):
                parsed.append(to_float(v))
            elif col_type == "numeric":
                parsed.append(None)
            else:
                parsed.append(v)

        non_null = [p for p in parsed if p is not None]
        unique_vals = set(str(p) for p in non_null) if col_type != "numeric" else set()

        columns.append({
            "name": col,
            "type": col_type,
            "unique_count": len(unique_vals),
            "null_count": len(parsed) - len(non_null),
            "unique_ratio": round(len(unique_vals) / len(non_null), 3) if non_null else 0,
            "parsed": parsed,
        })

    # Build enriched rows dict
    enriched_rows = []
    for i, row in enumerate(rows):
        enriched = {}
        for col_info in columns:
            enriched[col_info["name"]] = col_info["parsed"][i]
        enriched_rows.append(enriched)

    # Classify columns
    numeric_cols = [c for c in columns if c["type"] == "numeric"]
    time_cols = [c for c in columns if c["type"] == "time"]
    categorical_cols = [
        c for c in columns if c["type"] == "categorical" and 1 < c["unique_count"] <= 30
    ]
    text_cols = [c for c in columns if c["type"] == "text"]

    # Output structure
    analysis = {
        "meta": {
            "total_rows": len(rows),
            "columns": [
                {"name": c["name"], "type": c["type"], "unique_count": c["unique_count"], "null_count": c["null_count"]}
                for c in columns
            ],
            "numeric_columns": [c["name"] for c in numeric_cols],
            "time_columns": [c["name"] for c in time_cols],
            "categorical_columns": [c["name"] for c in categorical_cols],
            "text_columns": [c["name"] for c in text_cols],
        },
        "statistics": {},
        "category_analysis": {},
        "correlations": [],
        "insights": [],
    }

    # Statistics for numeric columns
    has_time = len(time_cols) > 0
    for col_info in numeric_cols:
        try:
            st = compute_stats(col_info["parsed"])
            if st is None:
                continue
            if has_time:
                st["trend"] = detect_trend(col_info["parsed"])
            analysis["statistics"][col_info["name"]] = st
        except Exception:
            continue

    # Category analysis
    cat_by_card = sorted(categorical_cols, key=lambda c: c["unique_count"])
    for col_info in cat_by_card[:5]:
        try:
            num_names = [c["name"] for c in numeric_cols]
            result = analyze_by_category(enriched_rows, col_info["name"], num_names)
            analysis["category_analysis"][col_info["name"]] = result
        except Exception:
            continue

    # Correlation analysis (top 6 pairs)
    if len(numeric_cols) >= 2:
        pairs_checked = 0
        for i in range(len(numeric_cols)):
            for j in range(i + 1, len(numeric_cols)):
                if pairs_checked >= 15:
                    break
                try:
                    r = pearson_corr(numeric_cols[i]["parsed"], numeric_cols[j]["parsed"])
                    if r is not None:
                        analysis["correlations"].append({
                            "columns": [numeric_cols[i]["name"], numeric_cols[j]["name"]],
                            "correlation": round(r, 3),
                        })
                        if abs(r) > 0.7:
                            direction = "positive" if r > 0 else "negative"
                            analysis["insights"].append({
                                "type": "correlation",
                                "text": f"Strong {direction} correlation ({round(r, 2)}) between {numeric_cols[i]['name']} and {numeric_cols[j]['name']}",
                                "priority": 3,
                            })
                    pairs_checked += 1
                except Exception:
                    continue

    # Extract insights
    all_insights = extract_insights(
        analysis["meta"],
        [c for c in columns],
        analysis["statistics"],
        analysis["category_analysis"],
        analysis["correlations"],
        enriched_rows,
    )
    analysis["insights"] = all_insights[: args.top]

    # Write output
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    print(f"Done: {len(rows)} rows, {len(columns)} cols, {len(analysis['insights'])} insights -> {args.output}")


if __name__ == "__main__":
    main()

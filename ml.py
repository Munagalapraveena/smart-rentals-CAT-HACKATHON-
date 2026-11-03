"""
The Machine Learning Core (Slide 6):
1. Demand Forecasting -> Random Forest Regressor
   predicts next-period equipment demand per site & type.
2. Anomaly Detection -> Isolation Forest on idle/engine-hour ratio + operating days,
   plus a rule-based layer (unassigned operator, idle hours far above site average).
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.preprocessing import LabelEncoder

from models import db, Equipment, UsageLog, Rental


def _season_of(d: date) -> str:
    m = d.month
    if m in (12, 1, 2):
        return "Winter"
    if m in (3, 4, 5):
        return "Summer"
    if m in (6, 7, 8, 9):
        return "Monsoon"
    return "Autumn"


def forecast_demand(top_n=8):
    """Aggregate rentals by site, equipment type & week, then train a
    Random Forest Regressor to predict next-period demand per site/type."""
    rows = (
        db.session.query(UsageLog, Equipment)
        .join(Equipment, UsageLog.equipment_id == Equipment.id)
        .all()
    )
    if not rows:
        return []

    data = pd.DataFrame([{
        "site": u.site,
        "type": e.type,
        "date": u.date,
        "engine_hours": u.engine_hours,
    } for u, e in rows])

    data["week"] = data["date"].apply(lambda d: d.isocalendar()[1])
    data["season"] = data["date"].apply(_season_of)

    grouped = (
        data.groupby(["site", "type", "week", "season"])["engine_hours"]
        .agg(total_hours="sum", utilization_rate="mean")
        .reset_index()
    )
    grouped = grouped.sort_values(["site", "type", "week"])
    grouped["past_utilization"] = grouped.groupby(["site", "type"])["utilization_rate"].shift(1).fillna(
        grouped["utilization_rate"].mean())
    grouped["operating_day_trend"] = grouped.groupby(["site", "type"])["total_hours"].diff().fillna(0)

    site_enc, type_enc, season_enc = LabelEncoder(), LabelEncoder(), LabelEncoder()
    grouped["site_enc"] = site_enc.fit_transform(grouped["site"])
    grouped["type_enc"] = type_enc.fit_transform(grouped["type"])
    grouped["season_enc"] = season_enc.fit_transform(grouped["season"])

    features = ["site_enc", "type_enc", "season_enc", "past_utilization", "operating_day_trend"]
    X = grouped[features]
    y = grouped["total_hours"]

    model = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
    model.fit(X, y)

    # Build a next-week prediction row for every (site, type) combo we've seen
    latest = grouped.sort_values("week").groupby(["site", "type"]).tail(1).copy()
    latest["predicted_next_period_hours"] = model.predict(latest[features])

    results = latest.sort_values("predicted_next_period_hours", ascending=False).head(top_n)
    return [{
        "site": r.site,
        "type": r.type,
        "predicted_hours": round(float(r.predicted_next_period_hours), 1),
        "recent_utilization": round(float(r.utilization_rate), 2),
    } for r in results.itertuples()]


def detect_anomalies(window_days=3):
    """Isolation Forest (trained on the full day-level history) on idle/
    engine-hour ratio & operating days, plus a rule-based layer (unassigned
    operator, idle hours far above site average, near-zero engine hours with
    high idle). Each asset is judged on its most recent few days so a single
    bad day surfaces, while thresholds combine relative + absolute checks so
    ordinary day-to-day variance doesn't swamp the list.
    """
    rows = (
        db.session.query(UsageLog, Equipment)
        .join(Equipment, UsageLog.equipment_id == Equipment.id)
        .all()
    )
    if not rows:
        return []

    df = pd.DataFrame([{
        "usage_id": u.id,
        "equipment_id": e.id,
        "asset_tag": e.asset_tag,
        "name": e.name,
        "type": e.type,
        "site": u.site,
        "date": u.date,
        "engine_hours": u.engine_hours,
        "idle_hours": u.idle_hours,
        "last_operator_id": e.last_operator_id,
        "eq_status": e.status,
    } for u, e in rows])

    df["idle_engine_ratio"] = df["idle_hours"] / df["engine_hours"].replace(0, 0.01)
    site_avg_idle = df.groupby("site")["idle_hours"].transform("mean")

    # ---- ML layer: Isolation Forest trained on the full day-level history ----
    iso = IsolationForest(contamination=0.05, random_state=42)
    feats = df[["idle_engine_ratio", "engine_hours", "idle_hours"]]
    df["ml_flag"] = iso.fit_predict(feats) == -1

    # ---- Rule-based layer (relative AND absolute, to avoid noise) ----
    df["rule_unassigned"] = (df["eq_status"].isin(["rented", "overdue"])) & (df["last_operator_id"].isna())
    df["rule_high_idle"] = (df["idle_hours"] > site_avg_idle * 2.2) & (df["idle_hours"] > 5)
    df["rule_zero_engine"] = (df["engine_hours"] < 0.3) & (df["idle_hours"] > 3)

    df["is_anomaly"] = df["ml_flag"] | df["rule_unassigned"] | df["rule_high_idle"] | df["rule_zero_engine"]

    # only look at each asset's most recent window
    cutoff = df["date"].max() - timedelta(days=window_days)
    recent = df[df["date"] >= cutoff]
    flagged = recent[recent["is_anomaly"]].sort_values("date", ascending=False)
    flagged = flagged.drop_duplicates("equipment_id")

    out = []
    for r in flagged.itertuples():
        reasons = []
        if r.rule_zero_engine:
            reasons.append("Near-zero engine hours with high idle")
        if r.rule_unassigned:
            reasons.append("Unassigned operator")
        if r.rule_high_idle and not r.rule_zero_engine:
            reasons.append("Idle hours far above site average")
        if r.ml_flag and not reasons:
            reasons.append("Unusual idle/engine-hour pattern (ML)")
        elif r.ml_flag:
            reasons.append("Confirmed by anomaly model")

        out.append({
            "asset_tag": r.asset_tag,
            "name": r.name,
            "type": r.type,
            "site": r.site,
            "date": r.date.isoformat(),
            "engine_hours": round(float(r.engine_hours), 2),
            "idle_hours": round(float(r.idle_hours), 2),
            "reasons": reasons,
        })
    return sorted(out, key=lambda x: len(x["reasons"]), reverse=True)


def refresh_overdue_status():
    """Flip any equipment/rental whose due date has passed into 'overdue'."""
    now = pd_now = __import__("datetime").datetime.utcnow()
    active_rentals = Rental.query.filter(Rental.status == "active").all()
    changed = False
    for r in active_rentals:
        if r.due_date < now:
            r.status = "overdue"
            if r.equipment:
                r.equipment.status = "overdue"
            changed = True
    if changed:
        db.session.commit()

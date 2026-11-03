import os
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, render_template

from models import db, Equipment, Rental, UsageLog, EQUIPMENT_TYPES, SITES
import ml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'rental_tracking.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


# ---------------------------------------------------------------- pages ----
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# --------------------------------------------------------------- helpers ---
def _serialize_equipment_list(items):
    return [e.to_dict() for e in items]


# ------------------------------------------------------------ equipment ----
@app.route("/api/equipment", methods=["GET"])
def list_equipment():
    ml.refresh_overdue_status()
    site = request.args.get("site")
    status = request.args.get("status")
    q = Equipment.query
    if site:
        q = q.filter_by(site=site)
    if status:
        q = q.filter_by(status=status)
    items = q.order_by(Equipment.id).all()
    return jsonify({
        "count": len(items),
        "sites": SITES,
        "types": EQUIPMENT_TYPES,
        "equipment": _serialize_equipment_list(items),
    })


@app.route("/api/equipment/<int:eq_id>", methods=["GET"])
def get_equipment(eq_id):
    eq = Equipment.query.get_or_404(eq_id)
    return jsonify(eq.to_dict())


# ------------------------------------------------------ check-in / out -----
@app.route("/api/equipment/<int:eq_id>/checkout", methods=["POST"])
def checkout_equipment(eq_id):
    eq = Equipment.query.get_or_404(eq_id)
    if eq.status in ("rented", "overdue"):
        return jsonify({"error": "Equipment is already checked out."}), 400

    payload = request.get_json(silent=True) or {}
    operator_id = payload.get("operator_id") or "OP-UNKNOWN"
    rental_days = int(payload.get("rental_days", 7))
    site = payload.get("site") or eq.site

    now = datetime.utcnow()
    rental = Rental(
        equipment_id=eq.id,
        site=site,
        operator_id=operator_id,
        checkout_date=now,
        due_date=now + timedelta(days=rental_days),
        status="active",
    )
    eq.status = "rented"
    eq.site = site
    eq.last_operator_id = operator_id
    db.session.add(rental)
    db.session.commit()
    return jsonify({"message": f"{eq.name} checked out to {operator_id}.", "equipment": eq.to_dict()})


@app.route("/api/equipment/<int:eq_id>/checkin", methods=["POST"])
def checkin_equipment(eq_id):
    eq = Equipment.query.get_or_404(eq_id)
    active_rental = next((r for r in eq.rentals if r.status in ("active", "overdue")), None)
    if not active_rental:
        return jsonify({"error": "Equipment is not currently checked out."}), 400

    active_rental.return_date = datetime.utcnow()
    active_rental.status = "returned"
    eq.status = "available"
    eq.last_operator_id = None
    db.session.commit()
    return jsonify({"message": f"{eq.name} checked in.", "equipment": eq.to_dict()})


# -------------------------------------------------------------- rentals ----
@app.route("/api/rentals", methods=["GET"])
def list_rentals():
    ml.refresh_overdue_status()
    status = request.args.get("status")
    q = Rental.query
    if status:
        q = q.filter_by(status=status)
    items = q.order_by(Rental.checkout_date.desc()).all()
    return jsonify([r.to_dict() for r in items])


@app.route("/api/alerts/overdue", methods=["GET"])
def overdue_alerts():
    ml.refresh_overdue_status()
    items = Rental.query.filter_by(status="overdue").order_by(Rental.due_date).all()
    alerts = []
    now = datetime.utcnow()
    for r in items:
        days_overdue = (now - r.due_date).days
        alerts.append({**r.to_dict(), "days_overdue": max(days_overdue, 0)})
    return jsonify(alerts)


# ---------------------------------------------------------------- usage ----
@app.route("/api/usage", methods=["GET"])
def usage_summary():
    site = request.args.get("site")
    q = UsageLog.query
    if site:
        q = q.filter_by(site=site)
    logs = q.order_by(UsageLog.date.desc()).limit(500).all()

    # per-site daily totals for the last 14 days (for chart)
    from collections import defaultdict
    daily = defaultdict(lambda: {"engine_hours": 0.0, "idle_hours": 0.0})
    for log in logs:
        key = log.date.isoformat()
        daily[key]["engine_hours"] += log.engine_hours
        daily[key]["idle_hours"] += log.idle_hours

    trend = [{"date": d, **v} for d, v in sorted(daily.items())][-14:]

    return jsonify({
        "logs": [l.to_dict() for l in logs[:50]],
        "trend": trend,
    })


# ------------------------------------------------------------ ML layer -----
@app.route("/api/forecast/demand", methods=["GET"])
def demand_forecast():
    top_n = int(request.args.get("top_n", 8))
    return jsonify(ml.forecast_demand(top_n=top_n))


@app.route("/api/anomalies", methods=["GET"])
def anomalies():
    return jsonify(ml.detect_anomalies())


# -------------------------------------------------------------- summary ----
@app.route("/api/summary", methods=["GET"])
def summary():
    ml.refresh_overdue_status()
    total = Equipment.query.count()
    available = Equipment.query.filter_by(status="available").count()
    rented = Equipment.query.filter_by(status="rented").count()
    overdue = Equipment.query.filter_by(status="overdue").count()
    anomaly_count = len(ml.detect_anomalies())
    return jsonify({
        "total_equipment": total,
        "available": available,
        "rented": rented,
        "overdue": overdue,
        "anomalies": anomaly_count,
    })


@app.route("/api/reseed", methods=["POST"])
def reseed():
    """Regenerate synthetic demo data on demand."""
    import seed_data
    seed_data.seed(app)
    return jsonify({"message": "Demo data regenerated."})


if __name__ == "__main__":
    with app.app_context():
        db_path = os.path.join(BASE_DIR, "rental_tracking.db")
        if not os.path.exists(db_path):
            import seed_data
            seed_data.seed(app)
        else:
            db.create_all()
    app.run(debug=False, port=5000)

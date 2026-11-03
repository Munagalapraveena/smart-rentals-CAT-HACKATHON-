# Smart Rental Tracking System

A working prototype for the Caterpillar hackathon brief: real-time tracking,
demand forecasting, and anomaly detection for rented construction & mining
equipment.

Matches the deck's architecture (Slide 4):
- **Data layer** — simulated QR/RFID check-in/out + telemetry (`seed_data.py`, `Faker`)
- **Backend / API** — Flask REST API over SQLite (`app.py`, `models.py`)
- **ML layer** — Random Forest demand forecasting + Isolation Forest anomaly
  detection, with a rule-based layer on top (`ml.py`)
- **Dashboard** — live asset status, check-in/out, overdue alerts, forecast
  and anomaly views (`templates/`, `static/`)

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** — the database seeds itself with 42 pieces of
equipment, 60 days of usage telemetry, and a mix of active/overdue rentals on
first run.

Click **"↻ Resim"** in the top bar any time to regenerate fresh synthetic
data for a demo run.

## Tour of the app (matches the deck's Demo Flow, Slide 8)

1. **Asset Board** — every asset's live status (available / rented /
   overdue), site, and condition.
2. **Check-in / Check-out** — pick an asset tag (simulating a QR/RFID scan),
   assign an operator + rental duration, and watch its status update
   instantly.
3. **Usage Logs** — per-site engine/idle-hour trend chart plus a raw log
   table (runtime, idle time, fuel).
4. **Overdue Alerts** — equipment past its due date, with days-overdue.
5. **Demand Forecast** — Random Forest Regressor prediction of which
   equipment type each site will need next period.
6. **Anomaly Detection** — Isolation Forest + rule-based flags (unassigned
   operator, idle hours far above site average, near-zero engine hours with
   high idle — e.g. an excavator with 0 engine hrs but 11 idle hrs).

## Project structure

```
smart-rental/
├── app.py              # Flask app & REST API
├── models.py            # SQLAlchemy models (Equipment, Rental, UsageLog)
├── ml.py                 # Random Forest + Isolation Forest
├── seed_data.py           # synthetic data generator (Faker)
├── requirements.txt
├── templates/dashboard.html
└── static/
    ├── css/style.css
    └── js/dashboard.js
```

## Swapping in real data

- Replace `seed_data.py`'s Faker calls with your real QR/RFID scan events
  and telemetry feed — the `UsageLog` / `Rental` / `Equipment` schemas
  already match what the ML layer expects.
- For production, swap SQLite for PostgreSQL by changing
  `SQLALCHEMY_DATABASE_URI` in `app.py` (no other code changes needed,
  since SQLAlchemy abstracts the dialect).
- The frontend is plain HTML/CSS/JS calling the REST API — swap in React
  later (as the deck notes as an option) without touching the backend.

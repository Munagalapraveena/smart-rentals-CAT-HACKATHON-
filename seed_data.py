"""
Generates realistic synthetic rental + telemetry data so the dashboard,
demand forecast, and anomaly detection models have something to work with
-- mirroring the deck's "simulated telemetry" approach (Slide 4 & 7).
"""
import random
from datetime import datetime, timedelta

from faker import Faker

from models import db, Equipment, Rental, UsageLog, EQUIPMENT_TYPES, SITES

fake = Faker()
random.seed(42)
Faker.seed(42)

N_EQUIPMENT = 42
DAYS_OF_HISTORY = 60


def seed(app):
    with app.app_context():
        db.drop_all()
        db.create_all()

        equipment_list = []
        for i in range(N_EQUIPMENT):
            etype = random.choice(EQUIPMENT_TYPES)
            eq = Equipment(
                asset_tag=f"CAT-{1000 + i}",
                name=f"{etype} #{i + 1}",
                type=etype,
                site=random.choice(SITES),
                status="available",
                condition=random.choices(["Good", "Fair", "Needs Service"], weights=[0.7, 0.22, 0.08])[0],
            )
            equipment_list.append(eq)
        db.session.add_all(equipment_list)
        db.session.commit()

        today = datetime.utcnow()

        # ---- Usage logs: 60 days of simulated telemetry per asset ----
        usage_rows = []
        for eq in equipment_list:
            # give each asset a "personality" so ML has real signal
            base_engine = random.uniform(2, 9)
            base_idle = random.uniform(0.2, 2.5)
            is_underused = random.random() < 0.15  # under-utilized asset

            for d in range(DAYS_OF_HISTORY, 0, -1):
                date = (today - timedelta(days=d)).date()
                # weekends lighter usage
                weekday_factor = 0.4 if date.weekday() >= 5 else 1.0
                engine_hrs = max(0, random.gauss(base_engine, 1.3)) * weekday_factor
                idle_hrs = max(0, random.gauss(base_idle, 0.8))

                if is_underused:
                    engine_hrs *= 0.25

                usage_rows.append(UsageLog(
                    equipment_id=eq.id,
                    site=eq.site,
                    date=date,
                    engine_hours=round(engine_hrs, 2),
                    idle_hours=round(idle_hrs, 2),
                    fuel_used_l=round(engine_hrs * random.uniform(8, 15), 1),
                ))

        # ---- Inject deliberate anomalies (Slide 6 example: 0 engine hrs, 11 idle hrs) ----
        anomaly_assets = random.sample(equipment_list, 5)
        for eq in anomaly_assets:
            date = (today - timedelta(days=random.randint(1, 5))).date()
            usage_rows.append(UsageLog(
                equipment_id=eq.id,
                site=eq.site,
                date=date,
                engine_hours=0.0,
                idle_hours=round(random.uniform(9, 13), 1),
                fuel_used_l=0.0,
            ))
            eq.last_operator_id = None  # unassigned -> rule-based flag

        db.session.add_all(usage_rows)
        db.session.commit()

        # ---- Rentals: check some assets out, a few overdue ----
        rentable = random.sample(equipment_list, 22)
        for i, eq in enumerate(rentable):
            checkout = today - timedelta(days=random.randint(1, 20))
            due = checkout + timedelta(days=random.randint(3, 14))
            operator_id = f"OP-{random.randint(100, 999)}" if eq.last_operator_id != None or eq not in anomaly_assets else None

            overdue = due < today and random.random() < 0.55
            status = "overdue" if overdue else "active"

            rental = Rental(
                equipment_id=eq.id,
                site=eq.site,
                operator_id=operator_id,
                checkout_date=checkout,
                due_date=due,
                status=status,
            )
            eq.status = "overdue" if overdue else "rented"
            eq.last_operator_id = operator_id
            db.session.add(rental)

        # a handful of fully-returned historical rentals for realism
        for eq in random.sample(equipment_list, 10):
            checkout = today - timedelta(days=random.randint(30, 55))
            due = checkout + timedelta(days=random.randint(3, 10))
            returned = due - timedelta(days=random.randint(0, 2))
            rental = Rental(
                equipment_id=eq.id,
                site=eq.site,
                operator_id=f"OP-{random.randint(100, 999)}",
                checkout_date=checkout,
                due_date=due,
                return_date=returned,
                status="returned",
            )
            db.session.add(rental)

        db.session.commit()
        print(f"Seeded {len(equipment_list)} equipment, {len(usage_rows)} usage logs, "
              f"{len(rentable) + 10} rentals.")

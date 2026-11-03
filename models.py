from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

EQUIPMENT_TYPES = ["Excavator", "Bulldozer", "Wheel Loader", "Backhoe Loader",
                    "Motor Grader", "Skid Steer", "Dump Truck", "Crane"]

SITES = ["Site A - Riverside Quarry", "Site B - North Highway Ext.",
          "Site C - Coastal Mine", "Site D - Metro Rail Corridor",
          "Site E - Hillview Excavation"]


class Equipment(db.Model):
    __tablename__ = "equipment"

    id = db.Column(db.Integer, primary_key=True)
    asset_tag = db.Column(db.String(20), unique=True, nullable=False)   # QR/RFID code
    name = db.Column(db.String(80), nullable=False)
    type = db.Column(db.String(40), nullable=False)
    site = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(20), default="available")  # available | rented | overdue | maintenance
    last_operator_id = db.Column(db.String(20), nullable=True)
    condition = db.Column(db.String(20), default="Good")     # Good | Fair | Needs Service

    rentals = db.relationship("Rental", backref="equipment", lazy=True)
    logs = db.relationship("UsageLog", backref="equipment", lazy=True)

    def to_dict(self):
        active_rental = next((r for r in self.rentals if r.status in ("active", "overdue")), None)
        return {
            "id": self.id,
            "asset_tag": self.asset_tag,
            "name": self.name,
            "type": self.type,
            "site": self.site,
            "status": self.status,
            "condition": self.condition,
            "last_operator_id": self.last_operator_id,
            "due_date": active_rental.due_date.isoformat() if active_rental else None,
            "checkout_date": active_rental.checkout_date.isoformat() if active_rental else None,
        }


class Rental(db.Model):
    __tablename__ = "rentals"

    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=False)
    site = db.Column(db.String(80), nullable=False)
    operator_id = db.Column(db.String(20), nullable=True)
    checkout_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=False)
    return_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="active")  # active | overdue | returned

    def to_dict(self):
        return {
            "id": self.id,
            "equipment_id": self.equipment_id,
            "equipment_name": self.equipment.name if self.equipment else None,
            "asset_tag": self.equipment.asset_tag if self.equipment else None,
            "site": self.site,
            "operator_id": self.operator_id,
            "checkout_date": self.checkout_date.isoformat() if self.checkout_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "return_date": self.return_date.isoformat() if self.return_date else None,
            "status": self.status,
        }


class UsageLog(db.Model):
    __tablename__ = "usage_logs"

    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey("equipment.id"), nullable=False)
    site = db.Column(db.String(80), nullable=False)
    date = db.Column(db.Date, nullable=False)
    engine_hours = db.Column(db.Float, default=0.0)
    idle_hours = db.Column(db.Float, default=0.0)
    fuel_used_l = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {
            "id": self.id,
            "equipment_id": self.equipment_id,
            "equipment_name": self.equipment.name if self.equipment else None,
            "type": self.equipment.type if self.equipment else None,
            "site": self.site,
            "date": self.date.isoformat(),
            "engine_hours": self.engine_hours,
            "idle_hours": self.idle_hours,
            "fuel_used_l": self.fuel_used_l,
        }

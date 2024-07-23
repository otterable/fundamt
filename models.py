from app import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=True)
    phone = db.Column(db.String(20), nullable=True)

class Item(db.Model):
    id = db.Column(db.String(5), primary_key=True)
    title = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    image = db.Column(db.String(120), nullable=False)
    reported = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    tracked_since = db.Column(db.DateTime, default=datetime.utcnow)
    reported_since = db.Column(db.DateTime, nullable=True)

class ItemImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.String(5), db.ForeignKey('item.id'), nullable=False)
    filename = db.Column(db.String(120), nullable=False)

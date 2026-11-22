from pymongo import MongoClient
from .config import settings

client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
db = client[settings.db_name]
users = db["users"]
detections = db["detections"]

# E-challan & penalty management (app/enforcement)
violations = db["violations"]
owners = db["vehicle_owners"]
vehicles = db["vehicles"]
challans = db["challans"]
fine_rules = db["fine_rules"]
counters = db["counters"]
notifications = db["notifications"]
notification_outbox = db["notification_outbox"]
payments = db["payments"]

def ping():
    client.admin.command("ping")  # raises if Atlas is unreachable

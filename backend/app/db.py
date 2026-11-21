from pymongo import MongoClient
from .config import settings

client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
db = client[settings.db_name]
users = db["users"]
detections = db["detections"]

def ping():
    client.admin.command("ping")  # raises if Atlas is unreachable

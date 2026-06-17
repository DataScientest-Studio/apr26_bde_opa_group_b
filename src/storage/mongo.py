from dotenv import load_dotenv
import os
from pymongo import MongoClient

load_dotenv()

# Read credentials from .env
mongo_host = os.getenv("MONGO_HOST")
mongo_port = os.getenv("MONGO_PORT")
mongo_user = os.getenv("MONGO_USER")
mongo_password = os.getenv("MONGO_PASSWORD")
mongo_db = os.getenv("MONGO_DB")

# Fail fast if .env is missing or any credential is absent
# (mongo_user is excluded — it defaults to "admin")
_required = {
    "MONGO_HOST": mongo_host,
    "MONGO_PORT": mongo_port,
    "MONGO_USER": mongo_user,
    "MONGO_PASSWORD": mongo_password,
    "MONGO_DB": mongo_db,
}
_missing = [name for name, value in _required.items() if not value]
if _missing:
    raise EnvironmentError(
        f"Missing MongoDB credentials in .env: {', '.join(_missing)}. "
        "Check that a .env file exists with these keys."
    )

# Connection URI.
MONGO_URI = (
    f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}:{mongo_port}/?authSource=admin"
)

# serverSelectionTimeoutMS keeps a bad connection from hanging ~30s before failing.
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = client[mongo_db]


def get_collection(name):
    """Return a collection handle from the configured database."""
    return db[name]


def test_connection():
    """Test the MongoDB connection."""
    try:
        client.admin.command("ping")
        print("✓ MongoDB connection successful!")
        return True
    except Exception as e:
        print(f"✗ MongoDB connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()

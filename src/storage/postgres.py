from dotenv import load_dotenv 
import os
from sqlalchemy import create_engine, text 

load_dotenv()

# Read credentials from .env file
postgres_host = os.getenv('POSTGRES_HOST')
postgres_port = os.getenv('POSTGRES_PORT')
postgres_user = os.getenv('POSTGRES_USER')
postgres_password = os.getenv('POSTGRES_PASSWORD')
postgres_db = os.getenv('POSTGRES_DB')

# Fail fast if .env is missing or any credential is absent
_required = {
    "POSTGRES_HOST": postgres_host,
    "POSTGRES_PORT": postgres_port,
    "POSTGRES_USER": postgres_user,
    "POSTGRES_PASSWORD": postgres_password,
    "POSTGRES_DB": postgres_db,
}
_missing = [name for name, value in _required.items() if not value]
if _missing:
    raise EnvironmentError(
        f"Missing Postgres credentials in .env: {', '.join(_missing)}. "
        "Check that a .env file exists with these keys."
    )

# Create database connection string
DATABASE_URL = f"postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL)


def test_connection():
    """Test the database connection."""
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("✓ Database connection successful!")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()
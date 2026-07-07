"""Shared pytest setup.

Set placeholder DB credentials BEFORE any `src` module is imported. The storage
modules (src/storage/postgres.py, mongo.py) validate these env vars at IMPORT
time, so without them, importing anything that touches storage would raise.

No real connection is made — the SQLAlchemy engine and Mongo client are created
lazily, and these unit tests never hit a database.
"""
import os

_PLACEHOLDERS = {
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_DB": "test",
    "MONGO_HOST": "localhost",
    "MONGO_PORT": "27017",
    "MONGO_USER": "test",
    "MONGO_PASSWORD": "test",
    "MONGO_DB": "test",
}
for _key, _val in _PLACEHOLDERS.items():
    os.environ.setdefault(_key, _val)

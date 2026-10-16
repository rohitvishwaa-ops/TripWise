"""Create TripWise tables if they don't exist. Safe to run repeatedly; never drops data.

Usage (from backend/):  python init_db.py
"""

import sys

from dotenv import load_dotenv
from sqlalchemy import inspect

load_dotenv()

from database import Base, get_engine  # noqa: E402


def main() -> int:
    engine = get_engine()
    if engine is None:
        print("DATABASE_URL is not set in backend/.env", file=sys.stderr)
        return 1
    Base.metadata.create_all(engine, checkfirst=True)
    tables = inspect(engine).get_table_names()
    print(f"Database ready. Tables: {', '.join(sorted(tables))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./road_damage.db")

# SQLite specific argument for multithreaded FastAPI requests
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def migrate_db():
    """Applies SQLite column migrations if new columns were added to models."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        # Check existing table columns
        try:
            result = conn.execute(Base.metadata.tables["road_damage_reports"].select().limit(1))
            columns = result.keys()
        except Exception:
            return

        new_cols = {
            "annotated_image_path": "VARCHAR(500)",
            "priority_level": "VARCHAR(20)",
            "priority_reason": "TEXT",
        }
        for col_name, col_type in new_cols.items():
            if col_name not in columns:
                try:
                    conn.execute(f"ALTER TABLE road_damage_reports ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

def get_db():
    """Dependency that yields a database session for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

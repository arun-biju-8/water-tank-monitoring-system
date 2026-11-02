"""
Utility script to test connectivity to the Render PostgreSQL database.
Loads DATABASE_URL from backend/.env and tests connectivity, table creation,
and CRUD operations without exposing passwords in logs.
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend directory is in path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

# Explicitly load backend/.env
env_file = backend_dir / ".env"
if env_file.is_file():
    load_dotenv(dotenv_path=env_file)
    print(f"[OK] Loaded environment configuration from: {env_file}")
else:
    print(f"[ERROR] backend/.env file not found at {env_file}")
    print("Please create backend/.env by copying backend/.env.example and adding your Render credentials.")
    sys.exit(1)

# Import models and database session
from app.database import engine, Base, SessionLocal
from app import models, crud, schemas
from sqlalchemy import text, inspect


def main():
    # Safely print connection target with masked password
    safe_target = engine.url.render_as_string(hide_password=True)
    print(f"\nTesting connection to: {safe_target}")

    try:
        # Step 1: Test basic connectivity
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            pg_version = result.scalar()
            print(f"[SUCCESS] Connected to PostgreSQL!")
            print(f"Server version: {pg_version}")

            # Step 2: Verify or create tables
            Base.metadata.create_all(bind=engine)
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            print(f"[SUCCESS] Database tables verified: {tables}")

            if "water_readings" not in tables:
                print("[ERROR] Table 'water_readings' was not created.")
                sys.exit(1)

        # Step 3: Test a live CRUD write, read, and cleanup cycle
        db = SessionLocal()
        try:
            print("\nTesting live sensor reading write and read...")
            test_reading_in = schemas.WaterReadingCreate(
                water_level=75,
                probe_25=True,
                probe_50=True,
                probe_75=True,
                probe_100=False,
                alarm=False,
                muted=False
            )
            created_record = crud.create_reading(db=db, reading_in=test_reading_in)
            print(f"[SUCCESS] Test reading inserted with ID: {created_record.id}")

            fetched = crud.get_latest_reading(db=db)
            print(f"[SUCCESS] Retrieved latest reading from database: Level {fetched.water_level}%")

            # Clean up the test row
            db.delete(created_record)
            db.commit()
            print("[SUCCESS] Test record successfully cleaned up.")
            print("\nDatabase is fully operational and ready for live production use!")

        finally:
            db.close()

    except Exception as exc:
        print(f"\n[FAILED] Database operation failed.")
        print(f"Error Type: {type(exc).__name__}")
        print(f"Error Summary: {exc}")
        print("\nTroubleshooting Tips:")
        print("1. Did you use the 'External Database URL' from Render? (Internal URLs do not resolve locally).")
        print("2. Ensure '?sslmode=require' is appended to the connection string.")
        print("3. Check if your Render database is active (free instances may take a few seconds to wake up).")
        sys.exit(1)


if __name__ == "__main__":
    main()

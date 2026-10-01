import os
import sys
from pathlib import Path
import pytest

# Add project root directory to Python path for all tests
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

@pytest.fixture(autouse=True)
def ensure_database_state():
    from web_app import app
    from database import db, create_all_tables
    from models import User
    with app.app_context():
        try:
            admin = User.query.filter_by(role='admin').first()
        except Exception:
            db.session.rollback()
            admin = None
        if not admin:
            create_all_tables(app)
            try:
                from database import ensure_default_accounts, seed_default_academic_data
                ensure_default_accounts()
                seed_default_academic_data()
            except Exception:
                pass


@pytest.fixture(scope="session", autouse=True)
def preserve_attendance_csv():
    """Ensure test runs never leave dummy test rows in production Attendance.csv."""
    import csv
    csv_file = ROOT_DIR / "Attendance.csv"

    def _strip_test_rows():
        if not csv_file.exists():
            return
        try:
            cleaned_rows = []
            with csv_file.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    cleaned_rows.append(header)
                for r in reader:
                    if not r or not any(r):
                        continue
                    roll = r[0].strip().upper() if len(r) > 0 else ""
                    name = r[1].strip().upper() if len(r) > 1 else ""
                    if roll.startswith("TEST_") or roll.startswith("AUDIT_") or "TEST" in name or "AUDIT" in name:
                        continue
                    cleaned_rows.append(r)
            with csv_file.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(cleaned_rows)
        except Exception:
            pass

    _strip_test_rows()
    yield
    _strip_test_rows()


import argparse
import getpass

from sqlalchemy import select

from app.core.enums import StaffRole
from app.core.security import hash_password
from app.db.models import StaffUser
from app.db.session import SessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision an authorized NextCare medical-staff account."
    )
    parser.add_argument("--email", required=True, help="Unique staff email address")
    parser.add_argument("--full-name", required=True, help="Staff member's display name")
    parser.add_argument(
        "--role",
        choices=[role.value for role in StaffRole],
        default=StaffRole.DOCTOR.value,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    email = args.email.strip().lower()
    full_name = args.full_name.strip()
    if "@" not in email or any(character.isspace() for character in email):
        raise SystemExit("Enter a valid email address.")
    if not full_name:
        raise SystemExit("Full name cannot be empty.")

    password = getpass.getpass("Password (8+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters.")
    if len(password) > 1024:
        raise SystemExit("Password is too long.")

    with SessionLocal() as session:
        if session.scalar(select(StaffUser.id).where(StaffUser.email == email)):
            raise SystemExit(f"A staff account already exists for {email}.")
        staff_user = StaffUser(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role=StaffRole(args.role),
            is_active=True,
        )
        session.add(staff_user)
        session.commit()
        print(f"Created active {staff_user.role.value} staff account for {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

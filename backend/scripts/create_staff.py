"""Create a staff login, or reset an existing one's password. The email is the login name.

Usage (from backend/):
    uv run python scripts/create_staff.py you@company.com "Your Name" --role SUPER_ADMIN --phone 9876543210   (the first account)
    uv run python scripts/create_staff.py admin@company.com "Admin" --role ADMIN --phone 9876543211
    uv run python scripts/create_staff.py ravi@company.com "Ravi Kumar" --phone 9876543210
    uv run python scripts/create_staff.py ravi@company.com "Ravi Kumar" --reset-password
    uv run python scripts/create_staff.py old@address.com "Ravi Kumar" --update-contact --email new@address.com --phone 9876543210

Sign-in needs the email, the 10-digit mobile and the password, so a new login must have a mobile.
Normally people are added from the Users screen; this script is for the very first account.

The password is typed at a hidden prompt (never on the command line).
"""

import argparse
import getpass
import re
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import hash_password  # noqa: E402
from app.db import get_sessionmaker  # noqa: E402
from app.models import AuditLog, Staff, StaffRole  # noqa: E402

MIN_LENGTH = 8
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def read_password() -> str:
    if not sys.stdin.isatty():  # piped input, e.g. for automated setup
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    return first


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("email", help="the login name")
    p.add_argument("full_name")
    p.add_argument("--role", choices=[r.value for r in StaffRole], default=StaffRole.SM.value)
    p.add_argument("--reset-password", action="store_true", help="change the password of an existing login")
    p.add_argument("--update-contact", action="store_true", help="only set the mobile / a new email of an existing login")
    p.add_argument("--phone", help="10-digit mobile used to sign in")
    p.add_argument("--email", dest="new_email", help="with --update-contact: the new email")
    args = p.parse_args()

    email = args.email.strip().lower()
    if not EMAIL.match(email):
        print("That is not a valid email address.", file=sys.stderr)
        return 1
    phone = None
    if args.phone:
        digits = "".join(ch for ch in args.phone if ch.isdigit())
        digits = digits[2:] if len(digits) == 12 and digits.startswith("91") else digits
        if len(digits) != 10:
            print("The mobile must be exactly 10 digits.", file=sys.stderr)
            return 1
        phone = digits
    new_email = args.new_email.strip().lower() if args.new_email else None
    if new_email and not EMAIL.match(new_email):
        print("The new email is not a valid email address.", file=sys.stderr)
        return 1

    if args.update_contact:
        with get_sessionmaker()() as db:
            staff = db.scalar(select(Staff).where(Staff.email == email))
            if staff is None:
                print(f"{email} does not exist.", file=sys.stderr)
                return 1
            if phone:
                staff.phone = phone
            if new_email:
                staff.email = new_email
            db.add(AuditLog(action="STAFF_CONTACT_UPDATED", entity_type="staff", entity_id=str(staff.id), details={"email": staff.email}))
            db.commit()
            print(f"Contact updated: {staff.email}")
        return 0
    password = read_password()
    if len(password) < MIN_LENGTH:
        print(f"Password must be at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1

    with get_sessionmaker()() as db:
        staff = db.scalar(select(Staff).where(Staff.email == email))
        if staff and not args.reset_password:
            print(f"{email} already exists. Use --reset-password to change its password.", file=sys.stderr)
            return 1
        if staff is None and args.reset_password:
            print(f"{email} does not exist.", file=sys.stderr)
            return 1
        if staff is None:
            if phone is None:
                print("A new login needs --phone (the 10-digit mobile used to sign in).", file=sys.stderr)
                return 1
            staff = Staff(
                phone=phone,
                email=email,
                full_name=args.full_name.strip(),
                role=StaffRole(args.role),
                password_hash=hash_password(password),
            )
            db.add(staff)
            db.flush()
            action = "STAFF_CREATED"
        else:
            staff.password_hash = hash_password(password)
            if phone:
                staff.phone = phone
            action = "STAFF_PASSWORD_RESET"
        db.add(AuditLog(action=action, entity_type="staff", entity_id=str(staff.id), details={"email": email}))
        db.commit()
    print(f"{action.replace('_', ' ').capitalize()}: {email} ({args.full_name}, {args.role})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

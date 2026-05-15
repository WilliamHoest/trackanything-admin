import argparse
import os
import uuid

from dotenv import load_dotenv
from supabase import create_client


def _find_user_id_by_email(supabase, email: str) -> uuid.UUID | None:
    users = supabase.auth.admin.list_users()
    for user in users:
        if user.email and user.email.lower() == email.lower():
            return uuid.UUID(user.id)
    return None


def create_or_update_customer_admin(email: str, password: str, name: str, company: str) -> None:
    load_dotenv(".env")

    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")

    supabase = create_client(supabase_url, service_role_key)

    user_id: uuid.UUID | None = None
    try:
        response = supabase.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "name": name,
                    "company_name": company,
                },
            }
        )
        auth_user = getattr(response, "user", None) or response
        user_id = uuid.UUID(auth_user.id)
        print(f"Created auth user: {user_id}")
    except Exception as exc:
        print(f"Auth user creation failed, trying existing user lookup: {exc}")
        user_id = _find_user_id_by_email(supabase, email)
        if not user_id:
            raise

        supabase.auth.admin.update_user_by_id(
            str(user_id),
            {
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "name": name,
                    "company_name": company,
                },
            },
        )
        print(f"Updated existing auth user: {user_id}")

    profile_data = {
        "id": str(user_id),
        "name": name,
        "email": email,
        "contact_email": email,
        "company_name": company,
        "role": "admin",
    }
    result = supabase.table("profiles").upsert(profile_data).execute()
    if not result.data:
        raise RuntimeError("Profile upsert returned no data")

    profile = result.data[0]
    print(f"Profile upserted: {profile['id']}")
    print(f"Role: {profile.get('role')}")
    print(f"Email: {profile.get('email')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create/update a customer admin user in Supabase Auth and profiles."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--company", required=True)
    args = parser.parse_args()

    create_or_update_customer_admin(
        email=args.email,
        password=args.password,
        name=args.name,
        company=args.company,
    )


if __name__ == "__main__":
    main()

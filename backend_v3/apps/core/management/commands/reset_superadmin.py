"""
Management command to deactivate all existing SUPER_ADMIN users and create a fresh one.

Usage:
    python manage.py reset_superadmin
"""

import secrets
import string

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Role, User


def _generate_password(length=20):
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one of each category
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%&*" for c in pwd)
        ):
            return pwd


class Command(BaseCommand):
    help = "Deactivate all existing SUPER_ADMIN users and create a new one with secure defaults."

    @transaction.atomic
    def handle(self, *args, **options):
        # Deactivate all existing SUPER_ADMINs
        existing = User.objects.filter(role=Role.SUPER_ADMIN, is_active=True)
        count = existing.count()
        if count:
            existing.update(is_active=False)
            self.stdout.write(f"Deactivated {count} existing SUPER_ADMIN user(s).")

        # Generate secure password
        password = _generate_password()

        # Create new SUPER_ADMIN
        user = User.objects.create_user(
            username="superadmin",
            email="superadmin@clinomiclabs.com",
            password=password,
            role=Role.SUPER_ADMIN,
            is_superuser=True,
            is_staff=True,
            organization=None,
        )

        self.stdout.write(self.style.SUCCESS("\nNew SUPER_ADMIN created successfully."))
        self.stdout.write(f"  Username: {user.username}")
        self.stdout.write(f"  Email:    {user.email}")
        self.stdout.write(f"  Password: {password}")
        self.stdout.write(
            self.style.WARNING(
                "\n  >>> SAVE THIS PASSWORD NOW — it will not be shown again. <<<"
            )
        )

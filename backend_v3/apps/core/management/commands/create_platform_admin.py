"""
Management command to create or update the platform super admin user.

Usage:
    python manage.py create_platform_admin --username admin --email admin@example.com --password SecurePass123!

For production bootstrap, can also read from environment variables:
    PLATFORM_ADMIN_USERNAME, PLATFORM_ADMIN_EMAIL, PLATFORM_ADMIN_PASSWORD
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import Role, User


class Command(BaseCommand):
    help = "Create or update the platform super admin (SUPER_ADMIN role + is_superuser)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.environ.get("PLATFORM_ADMIN_USERNAME", ""),
            help="Super admin username (or set PLATFORM_ADMIN_USERNAME env var)",
        )
        parser.add_argument(
            "--email",
            default=os.environ.get("PLATFORM_ADMIN_EMAIL", ""),
            help="Super admin email (or set PLATFORM_ADMIN_EMAIL env var)",
        )
        parser.add_argument(
            "--password",
            default=os.environ.get("PLATFORM_ADMIN_PASSWORD", ""),
            help="Super admin password (or set PLATFORM_ADMIN_PASSWORD env var)",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Skip confirmation prompt (for CI/CD pipelines)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"].strip()
        email = options["email"].strip()
        password = options["password"]

        if not username:
            raise CommandError(
                "Username is required. Pass --username or set PLATFORM_ADMIN_USERNAME."
            )
        if not email:
            raise CommandError(
                "Email is required. Pass --email or set PLATFORM_ADMIN_EMAIL."
            )
        if not password:
            raise CommandError(
                "Password is required. Pass --password or set PLATFORM_ADMIN_PASSWORD."
            )
        if len(password) < 12:
            raise CommandError("Password must be at least 12 characters.")

        existing = User.objects.filter(username=username).first()

        if existing:
            if not options["no_input"]:
                confirm = input(
                    f"User '{username}' already exists. Update to super admin? [y/N] "
                )
                if confirm.lower() != "y":
                    self.stdout.write("Aborted.")
                    return

            existing.role = Role.SUPER_ADMIN
            existing.is_superuser = True
            existing.is_staff = True
            existing.email = email
            existing.set_password(password)
            existing.save()
            self.stdout.write(
                self.style.SUCCESS(f"Updated '{username}' to platform super admin.")
            )
        else:
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=Role.SUPER_ADMIN,
                is_superuser=True,
                is_staff=True,
                organization=None,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Created platform super admin '{username}'.")
            )

        self.stdout.write(
            f"  Username: {username}\n"
            f"  Email:    {email}\n"
            f"  Role:     SUPER_ADMIN\n"
            f"  Access:   Platform admin endpoints + Django admin"
        )

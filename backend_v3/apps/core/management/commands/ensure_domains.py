"""
Management command to ensure required domains exist for production deployment.

Creates/verifies domain entries for:
- clinomiclabs.com (primary domain for production)
- localhost (for local development)

Does NOT modify:
- docker config
- health checks  
- deployment logic

Only ensures required tenant/domain seed exists.
"""

import uuid
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Domain, Organization


class Command(BaseCommand):
    help = "Ensure required domains exist for Clinomic platform"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        
        if dry_run:
            self.stdout.write("=== DRY RUN MODE ===")
        
        self.stdout.write("Ensuring required domains exist...")
        
        # Get or create public tenant (typically the first organization)
        try:
            public_tenant = Organization.objects.first()
            if not public_tenant:
                self.stdout.write(
                    self.style.WARNING(
                        "No organization found. Run migrations and seed_demo_data first."
                    )
                )
                return
                
            self.stdout.write(f"Using tenant: {public_tenant.name} (schema: {public_tenant.schema_name})")
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error accessing organizations: {e}")
            )
            return

        # Required domains configuration - PRODUCTION SAFE
        required_domains = [
            {
                "domain": "clinomiclabs.com",
                "is_primary": True,
                "description": "Production domain"
            },
            {
                "domain": "localhost",
                "is_primary": False,  # Must be False for localhost
                "description": "Local development"
            }
        ]

        created_count = 0
        existing_count = 0

        with transaction.atomic():
            for domain_config in required_domains:
                domain_name = domain_config["domain"]
                
                if dry_run:
                    # Check if domain exists without creating
                    try:
                        existing_domain = Domain.objects.get(domain=domain_name)
                        self.stdout.write(
                            f"  [DRY-RUN] Domain exists: {domain_name} "
                            f"(tenant: {existing_domain.tenant.name}, primary: {existing_domain.is_primary})"
                        )
                        existing_count += 1
                    except Domain.DoesNotExist:
                        self.stdout.write(
                            f"  [DRY-RUN] Would create domain: {domain_name} "
                            f"({domain_config['description']})"
                        )
                        created_count += 1
                else:
                    # Create or update domain
                    domain_obj, created = Domain.objects.get_or_create(
                        domain=domain_name,
                        defaults={
                            "tenant": public_tenant,
                            "is_primary": domain_config["is_primary"],
                        }
                    )
                    
                    if created:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  Created domain: {domain_name} ({domain_config['description']})"
                            )
                        )
                        created_count += 1
                    else:
                        # Update if needed
                        updated = False
                        if domain_obj.tenant != public_tenant:
                            domain_obj.tenant = public_tenant
                            updated = True
                        if domain_obj.is_primary != domain_config["is_primary"]:
                            domain_obj.is_primary = domain_config["is_primary"]
                            updated = True
                        
                        if updated:
                            domain_obj.save()
                            self.stdout.write(
                                f"  Updated domain: {domain_name}"
                            )
                        else:
                            self.stdout.write(
                                f"  Domain exists: {domain_name}"
                            )
                        existing_count += 1

        # Summary
        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    f"\nDRY RUN SUMMARY:\n"
                    f"  Would create: {created_count} domains\n"
                    f"  Already exist: {existing_count} domains"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nDomain setup complete!\n"
                    f"  Created: {created_count} domains\n"
                    f"  Verified: {existing_count} domains\n"
                    f"  Total required domains ensured: {len(required_domains)}"
                )
            )

            # Show current domain configuration
            self.stdout.write("\nCurrent domain configuration:")
            domains = Domain.objects.filter(tenant=public_tenant).order_by('-is_primary')
            for domain in domains:
                status = "PRIMARY" if domain.is_primary else "SECONDARY"
                self.stdout.write(f"  • {domain.domain} ({status})")

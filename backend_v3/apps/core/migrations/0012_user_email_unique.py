"""
Add a partial-unique constraint on User.email.

Historical User rows may contain duplicate emails because the column was
previously indexed but not unique. This migration is a two-step move:

1. dedupe_user_emails — RunPython step that finds rows sharing a non-empty
   email, keeps the oldest (lowest created_at / first-discovered pk) and
   rewrites the rest to `<original>+dup<short-uuid>@<domain>` so they
   remain valid email addresses but no longer collide. The renamed users
   will need a password reset on next login, which is the correct
   behaviour — those accounts should never have been allowed.

2. AddConstraint — installs a partial-unique index
      `unique_user_email_when_set`
   that enforces uniqueness only when email is both non-NULL and
   non-empty. Lab-tech accounts provisioned without an email stay
   legal.

Reverse is a no-op for the rename (we can't tell renames apart from
legitimate emails once applied) plus a RemoveConstraint. If you have to
revert, do so from a backup.
"""

import uuid

from django.db import migrations, models


def dedupe_user_emails(apps, schema_editor):
    """
    Rewrite any duplicate User.email rows to unique values before the
    partial-unique constraint lands. Safe to run repeatedly — idempotent
    because once renamed, rows are no longer duplicates of anything.
    """
    User = apps.get_model('core', 'User')

    # Pull every non-null/non-empty email and tally occurrences.
    # Doing this in Python because the dedup logic is one-time and the
    # user table is small (users, not screenings).
    from collections import defaultdict
    by_email = defaultdict(list)
    for pk, email, created_at in User.objects.exclude(
        email__isnull=True
    ).exclude(email='').values_list('pk', 'email', 'created_at'):
        by_email[email.lower()].append((created_at, pk))

    for lowered, rows in by_email.items():
        if len(rows) < 2:
            continue
        # Sort oldest first; keep the first, rename the rest.
        rows.sort(key=lambda row: (row[0] or '', str(row[1])))
        _keep = rows[0]
        for _ts, pk in rows[1:]:
            user = User.objects.get(pk=pk)
            original = user.email or ''
            if '@' in original:
                local, _, domain = original.partition('@')
                new_email = f"{local}+dup{uuid.uuid4().hex[:8]}@{domain}"
            else:
                new_email = f"{original}+dup{uuid.uuid4().hex[:8]}"
            user.email = new_email
            user.save(update_fields=['email'])


def noop_reverse(apps, schema_editor):
    """Renames are not reversible — a revert would need a DB backup."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_user_org_set_null'),
    ]

    operations = [
        migrations.RunPython(dedupe_user_emails, noop_reverse),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(
                fields=['email'],
                condition=~models.Q(email__isnull=True) & ~models.Q(email=''),
                name='unique_user_email_when_set',
            ),
        ),
    ]

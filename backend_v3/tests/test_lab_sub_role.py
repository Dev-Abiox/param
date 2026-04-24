"""Tests for User.lab_sub_role capability helpers (P1-19)."""

import pytest


class _FakeUser:
    """Lightweight fake that mimics the User model's relevant surface
    so we can test the helpers without a DB."""
    def __init__(self, role='LAB', lab_sub_role='', is_superuser=False):
        self.role = role
        self.lab_sub_role = lab_sub_role
        self.is_superuser = is_superuser

    @property
    def is_super_admin(self):
        from apps.core.models import Role
        return self.is_superuser or self.role == Role.SUPER_ADMIN

    # Bind the User helpers onto this class at import time below.


def _bind_helpers():
    """Copy the capability helpers from the real User model onto _FakeUser
    so we exercise the real logic without a database."""
    from apps.core.models import User
    for name in (
        '_lab_rank',
        'can_view_demographics',
        'can_view_cbc_values',
        'can_view_recommendation',
        'can_manage_lab_users',
    ):
        setattr(_FakeUser, name, getattr(User, name))


_bind_helpers()


class TestLabSubRoleCapabilities:
    def test_super_admin_sees_everything(self):
        u = _FakeUser(role='SUPER_ADMIN', is_superuser=True)
        assert u.can_view_demographics()
        assert u.can_view_cbc_values()
        assert u.can_view_recommendation()
        assert u.can_manage_lab_users()

    def test_doctor_sees_clinical_data(self):
        u = _FakeUser(role='DOCTOR')
        assert u.can_view_demographics()
        assert u.can_view_cbc_values()
        assert u.can_view_recommendation()
        assert not u.can_manage_lab_users()  # Doctor doesn't manage lab users

    def test_receptionist_only_sees_demographics(self):
        u = _FakeUser(role='LAB', lab_sub_role='receptionist')
        assert u.can_view_demographics()
        assert not u.can_view_cbc_values()
        assert not u.can_view_recommendation()
        assert not u.can_manage_lab_users()

    def test_technician_sees_cbc(self):
        u = _FakeUser(role='LAB', lab_sub_role='technician')
        assert u.can_view_demographics()
        assert u.can_view_cbc_values()
        assert not u.can_view_recommendation()
        assert not u.can_manage_lab_users()

    def test_pathologist_sees_recommendation(self):
        u = _FakeUser(role='LAB', lab_sub_role='pathologist')
        assert u.can_view_demographics()
        assert u.can_view_cbc_values()
        assert u.can_view_recommendation()
        assert not u.can_manage_lab_users()

    def test_lab_admin_has_everything_within_tenant(self):
        u = _FakeUser(role='LAB', lab_sub_role='lab_admin')
        assert u.can_view_demographics()
        assert u.can_view_cbc_values()
        assert u.can_view_recommendation()
        assert u.can_manage_lab_users()

    def test_unscoped_lab_user_retains_full_access(self):
        """Legacy LAB users with no sub-role keep working until assigned one."""
        u = _FakeUser(role='LAB', lab_sub_role='')
        assert u.can_view_demographics()
        assert u.can_view_cbc_values()
        assert u.can_view_recommendation()
        assert u.can_manage_lab_users()

    def test_non_lab_role_without_doctor_is_denied(self):
        u = _FakeUser(role='OTHER', lab_sub_role='')
        assert not u.can_view_demographics()
        assert not u.can_view_cbc_values()
        assert not u.can_view_recommendation()
        assert not u.can_manage_lab_users()

    def test_monotonic_ordering(self):
        """Every capability satisfied by a lower role must also be satisfied by a higher one."""
        roles = ['receptionist', 'technician', 'pathologist', 'lab_admin']
        checks = ['can_view_demographics', 'can_view_cbc_values',
                  'can_view_recommendation', 'can_manage_lab_users']
        prev = [False] * len(checks)
        for r in roles:
            u = _FakeUser(role='LAB', lab_sub_role=r)
            current = [getattr(u, c)() for c in checks]
            # anything true at the previous tier must stay true
            for i in range(len(checks)):
                assert not (prev[i] and not current[i]), f'monotonicity broken at {r}:{checks[i]}'
            prev = current

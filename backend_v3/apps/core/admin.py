"""
Django Admin configuration for Core models.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.text import slugify

from .models import AuditLogEntry, Domain, MFASettings, Organization, RefreshToken, User


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'schema_name', 'tier', 'is_active', 'created_at']
    list_filter = ['tier', 'is_active']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [DomainInline]
    fieldsets = (
        (None, {'fields': ('name', 'schema_name', 'tier')}),
        ('Status', {'fields': ('is_active',)}),
        ('Info', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:
            readonly.append('schema_name')
        return readonly

    def save_model(self, request, obj, form, change):
        if not change and not obj.schema_name:
            obj.schema_name = slugify(obj.name).replace('-', '_')
        super().save_model(request, obj, form, change)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'role', 'organization', 'is_active', 'is_staff']
    list_filter = ['role', 'is_active', 'is_staff', 'organization']
    search_fields = ['username', 'email', 'name']
    ordering = ['username']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_login']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('name', 'email')}),
        ('Organization', {'fields': ('organization', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'last_login')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'role', 'organization'),
        }),
    )


@admin.register(MFASettings)
class MFASettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_enabled', 'verified_at']
    list_filter = ['is_enabled']
    search_fields = ['user__username']
    readonly_fields = ['id', 'created_at', 'updated_at', 'verified_at']


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_revoked', 'created_at', 'expires_at']
    list_filter = ['is_revoked']
    search_fields = ['user__username']
    readonly_fields = ['id', 'token_hash', 'created_at']


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ['sequence', 'actor', 'action', 'entity_type', 'timestamp']
    list_filter = ['action', 'entity_type']
    search_fields = ['actor', 'action']
    readonly_fields = [
        'id', 'sequence', 'actor', 'action', 'entity_type', 'entity_id',
        'details', 'previous_hash', 'entry_hash', 'signature', 'timestamp'
    ]

    def has_add_permission(self, request):
        return False  # Audit logs are immutable

    def has_change_permission(self, request, obj=None):
        return False  # Audit logs are immutable

    def has_delete_permission(self, request, obj=None):
        return False  # Audit logs are immutable

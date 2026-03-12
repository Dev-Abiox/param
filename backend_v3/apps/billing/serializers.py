"""
Billing serializers.
"""

from rest_framework import serializers

from .models import SubscriptionPlan, TenantSubscription, UsageRecord


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['name', 'display_name', 'monthly_limit', 'price_monthly', 'is_active']


class TenantSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    is_over_limit = serializers.BooleanField(read_only=True)

    class Meta:
        model = TenantSubscription
        fields = [
            'id', 'plan', 'status', 'razorpay_sub_id',
            'current_period_start', 'current_period_end', 'current_period_count',
            'trial_end', 'cancelled_at', 'is_over_limit',
            'created_at', 'updated_at',
        ]


class UsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageRecord
        fields = ['period_start', 'period_end', 'screening_count']


class OnboardingStatusSerializer(serializers.Serializer):
    lab_added = serializers.BooleanField(required=False)
    doctor_added = serializers.BooleanField(required=False)
    user_invited = serializers.BooleanField(required=False)
    completed = serializers.BooleanField(required=False)

# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Register core capability flags that gate features across financial plans.

Every user-facing capability must have a FeatureFlag row registered in
apps/api/plane/billing so it can be gated per plan and configured by operators.
These rows are created inactive by default so existing installations without
configured plan feature flags are unaffected until an operator enables them.
"""

# Django imports
from django.db import migrations

CORE_FEATURE_FLAGS = [
    {
        "code": "task_blocking",
        "name": "وابستگی و قفل تسک‌ها (Task Blocking)",
        "description": "امکان مسدودسازی و تعیین پیش‌نیاز/پس‌نیاز بین تسک‌ها (روابط blocking و blocked_by).",
        "category": "issue",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "pages",
        "name": "اسناد و مستندات (Pages)",
        "description": "امکان ساخت و مدیریت اسناد، صفحات پروژه و پایگاه دانش تیمی.",
        "category": "workspace",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "ai_features",
        "name": "دستیار هوش مصنوعی (AI)",
        "description": "دسترسی به دستیار هوش مصنوعی برای نگارش، خلاصه‌سازی و تولید خودکار تسک‌ها.",
        "category": "workspace",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "cycles",
        "name": "دوره‌ها و اسپرینت‌ها (Cycles)",
        "description": "امکان تعریف چرخه‌های کاری، اسپرینت‌های زمانی و پیگیری پیشرفت دوره‌ای.",
        "category": "project",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "modules",
        "name": "ماژول‌ها و زیرپروژه‌ها (Modules)",
        "description": "امکان شکستن پروژه‌ها به ماژول‌های کوچکتر، فازبندی و مدیریت اهداف.",
        "category": "project",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "analytics",
        "name": "گزارش‌ها و تحلیل آماری (Analytics)",
        "description": "دسترسی به نمودارهای تحلیل عملکرد، سرعت تیم، Burndown و گزارش‌های پیشرفته.",
        "category": "workspace",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "views",
        "name": "نماهای سفارشی (Custom Views)",
        "description": "امکان ساخت و ذخیره فیلترها و نماهای سفارشی برای تسک‌های هر پروژه.",
        "category": "project",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "estimates",
        "name": "سیستم تخمین و امتیازدهی (Estimates)",
        "description": "امکان تخمین زمانی یا امتیازی کارها با استفاده از Story Points و سیستم‌های برآورد.",
        "category": "project",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "intake",
        "name": "صندوق ورودی و بررسی (Triage / Intake)",
        "description": "امکان دریافت درخواست‌های ورودی و غربالگری آنها قبل از تبدیل به تسک رسمی.",
        "category": "project",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "webhooks",
        "name": "وب‌هوک‌ها و ادغام‌ها (Webhooks)",
        "description": "امکان ارسال خودکار رویدادها به وب‌هوک‌های خارجی و سرویس‌های ثالث.",
        "category": "workspace",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
    {
        "code": "time_tracking",
        "name": "ثبت و ردگیری زمان (Time Tracking)",
        "description": "امکان ثبت زمان کارکرد، تایمر زنده و گزارش‌گیری پیشرفته زمان روی تسک‌ها و پروژه‌ها.",
        "category": "project",
        "limit_type": "boolean",
        "unit_label": "",
        "is_active": False,
        "is_public": True,
    },
]


def register_core_feature_flags(apps, schema_editor):
    FeatureFlag = apps.get_model("billing", "FeatureFlag")
    Plan = apps.get_model("billing", "Plan")
    PlanFeatureFlag = apps.get_model("billing", "PlanFeatureFlag")
    for flag_def in CORE_FEATURE_FLAGS:
        code = flag_def["code"]
        flag, _ = FeatureFlag.objects.get_or_create(
            code=code,
            defaults={
                "name": flag_def["name"],
                "description": flag_def["description"],
                "category": flag_def["category"],
                "limit_type": flag_def["limit_type"],
                "unit_label": flag_def["unit_label"],
                "is_active": flag_def["is_active"],
                "is_public": flag_def["is_public"],
            },
        )
        # Enable across all existing plans by default
        for plan in Plan.objects.all():
            PlanFeatureFlag.objects.get_or_create(
                plan=plan,
                feature_flag=flag,
                defaults={"is_enabled": True},
            )


def unregister_core_feature_flags(apps, schema_editor):
    FeatureFlag = apps.get_model("billing", "FeatureFlag")
    codes = [flag["code"] for flag in CORE_FEATURE_FLAGS]
    FeatureFlag.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0011_renewalnotice_invoice"),
    ]

    operations = [
        migrations.RunPython(register_core_feature_flags, unregister_core_feature_flags),
    ]

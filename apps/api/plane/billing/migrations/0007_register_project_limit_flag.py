# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Register the project-count flag that gates project creation.

AGENTS.md requires every user-facing capability to have a ``FeatureFlag`` row in
or before the change that introduces it, or the capability can never be gated per
plan and never priced per seat. This is that row, and it is created **inactive**
on purpose:

* The gate reads a missing or inactive catalogue row as "this installation does
  not use this flag" and allows project creation. Creating the row active would
  switch the capability off for every workspace on every instance that upgrades,
  because no plan grants it yet. Shipping a gate must not be a way to take away
  a capability nobody chose to remove.
* An operator turns it on deliberately: activate the row, grant it to a plan with
  a ``limit_value``, and the workspaces on that plan are bounded by it.

``get_or_create`` rather than ``update_or_create``: an instance admin who already
created a row with this code keeps whatever name, unit label and state they set.

The code is repeated as a literal instead of imported from
``plane.billing.services.entitlements`` because migrations must not depend on
application code, which is free to change under them.
"""

# Django imports
from django.db import migrations

PROJECT_LIMIT_FLAG_CODE = "projects"


def register_project_limit_flag(apps, schema_editor):
    FeatureFlag = apps.get_model("billing", "FeatureFlag")
    FeatureFlag.objects.get_or_create(
        code=PROJECT_LIMIT_FLAG_CODE,
        defaults={
            "name": "پروژه‌ها",
            "description": "سقف تعداد پروژه‌های یک ورک‌اسپیس. تا وقتی این پرچم فعال نشود، ساخت پروژه محدود نمی‌شود.",
            "category": "workspace",
            "limit_type": "number",
            "unit_label": "پروژه",
            "is_active": False,
            "is_public": True,
        },
    )


def unregister_project_limit_flag(apps, schema_editor):
    """Remove the row outright, so re-applying the migration puts it back.

    Two traps here, both worth naming because the obvious version of this
    function hits the first one and the first version of this function hit the
    second:

    * ``FeatureFlag.objects.filter(...).delete()`` in *migration state* is a
      hard delete, because a custom manager is not serialised into migration
      state. Inside the running application the same expression soft deletes,
      and ``SoftDeleteModel.delete()`` (the instance method) enqueues a Celery
      task that raises when no broker is reachable -- so this line is only safe
      as written in a migration, not as written in application code.
    * Marking the row soft deleted instead would leave the reverse apparently
      working while a re-apply did nothing: the migration-state manager is the
      plain one, so ``get_or_create`` in the forward function finds the deleted
      row, keeps it, and the flag never comes back. Verified by running this
      migration down and up again.

    Grants that reference the row cascade away with it. That is the honest
    meaning of reversing a migration that registered a capability.
    """
    FeatureFlag = apps.get_model("billing", "FeatureFlag")
    FeatureFlag.objects.filter(code=PROJECT_LIMIT_FLAG_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_feature_flag_limits"),
    ]

    operations = [
        migrations.RunPython(register_project_limit_flag, unregister_project_limit_flag),
    ]

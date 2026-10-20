# Merge the upstream security migration branch (0125_reset_project_deploy_board_identity)
# with the billing and notification branch (0128_merge_20261016_1639)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0125_reset_project_deploy_board_identity'),
        ('db', '0128_merge_20261016_1639'),
    ]

    operations = [
    ]

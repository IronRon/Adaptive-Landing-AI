# Custom migration: delete old BanditArm (section/pulls/reward prototype)
# and rename CtxBanditArm → BanditArm.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("landing", "0010_ctxbanditarm_banditdecision_banditarmstat_and_more"),
    ]

    operations = [
        # 1. Drop the old prototype BanditArm table (section / pulls / reward)
        migrations.DeleteModel(
            name="BanditArm",
        ),
        # 2. Rename CtxBanditArm → BanditArm
        migrations.RenameModel(
            old_name="CtxBanditArm",
            new_name="BanditArm",
        ),
    ]

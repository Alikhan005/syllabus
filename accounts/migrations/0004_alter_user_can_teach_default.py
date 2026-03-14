from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_add_can_teach_to_user"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="can_teach",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Если выключить, пользователь с ролью декана "
                    "не будет иметь доступа к разделам курсов "
                    "и созданию/редактированию силлабусов "
                    "как преподаватель."
                ),
                verbose_name="Может преподавать/работать с курсами",
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="is_manual",
            field=models.BooleanField(
                default=False,
                help_text="Личная дисциплина, созданная из ручного ввода при загрузке силлабуса.",
            ),
        ),
    ]

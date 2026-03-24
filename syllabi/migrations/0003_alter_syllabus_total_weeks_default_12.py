from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("syllabi", "0002_alter_syllabus_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="syllabus",
            name="total_weeks",
            field=models.PositiveIntegerField(default=12, verbose_name="Количество недель"),
        ),
    ]

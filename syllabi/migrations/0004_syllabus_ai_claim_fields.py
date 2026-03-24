from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("syllabi", "0003_alter_syllabus_total_weeks_default_12"),
    ]

    operations = [
        migrations.AddField(
            model_name="syllabus",
            name="ai_claimed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Забрано в AI-обработку"),
        ),
        migrations.AddField(
            model_name="syllabus",
            name="ai_claimed_by",
            field=models.CharField(blank=True, max_length=128, verbose_name="AI-воркер"),
        ),
    ]

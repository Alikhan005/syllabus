from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_alter_user_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="can_teach",
            field=models.BooleanField(
                default=True,
                help_text="Teacher mode: allow working with courses and syllabi.",
                verbose_name="Can teach/manage course content",
            ),
        ),
    ]


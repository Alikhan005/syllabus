from django.db import migrations, models


def migrate_program_leaders_to_teachers(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="program_leader").update(role="teacher")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_alter_user_can_teach"),
    ]

    operations = [
        migrations.RunPython(migrate_program_leaders_to_teachers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("teacher", "Преподаватель"),
                    ("dean", "Деканат"),
                    ("umu", "УМУ"),
                    ("admin", "Админ"),
                ],
                default="teacher",
                max_length=32,
            ),
        ),
    ]

# Generated by Django 3.2.16 on 2023-02-03 21:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cart', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='cart',
            old_name='user_id',
            new_name='user',
        ),
    ]

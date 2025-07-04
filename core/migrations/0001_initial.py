# Generated by Django 5.2.3 on 2025-06-10 15:08

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='GHLAuthCredentials',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id', models.CharField(blank=True, max_length=255, null=True)),
                ('access_token', models.TextField()),
                ('refresh_token', models.TextField()),
                ('expires_in', models.IntegerField()),
                ('scope', models.TextField(blank=True, null=True)),
                ('user_type', models.CharField(blank=True, max_length=50, null=True)),
                ('company_id', models.CharField(blank=True, max_length=255, null=True)),
                ('location_id', models.CharField(blank=True, max_length=255, null=True)),
                ('location_name', models.CharField(blank=True, max_length=255, null=True)),
                ('company_name', models.CharField(blank=True, max_length=255, null=True)),
            ],
        ),
    ]

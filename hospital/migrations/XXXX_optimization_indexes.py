from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('hospital', 'XXXX_previous_migration'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='appointment',
            index=models.Index(fields=['patient', '-booked_at'], name='appointment_patient_id_6b0e1b_idx'),
        ),
        migrations.AddIndex(
            model_name='appointment',
            index=models.Index(fields=['doctor', '-booked_at'], name='appointment_doctor_i_11a647_idx'),
        ),
        migrations.AddIndex(
            model_name='testrequest',
            index=models.Index(fields=['appointment', '-created_at'], name='test_request_appointm_8e0397_idx'),
        ),
        migrations.AddIndex(
            model_name='vitalrequest',
            index=models.Index(fields=['appointment', '-created_at'], name='vital_reque_appointm_5e69f2_idx'),
        ),
        migrations.AddIndex(
            model_name='blogpost',
            index=models.Index(fields=['title'], name='blog_post_title_6b8d7e_idx'),
        ),
    ]
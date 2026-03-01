from django.contrib import admin
from .models import Appointment, Vitals, LabResult, MedicalReport, BlogPost


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'doctor', 'status', 'booked_at')
    list_filter = ('status', 'booked_at')
    search_fields = ('patient__user__username', 'doctor__user__username')
    ordering = ('-booked_at',)

@admin.register(MedicalReport)
class MedicalReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'appointment', 'doctor', 'medical_condition', 'next_appointment', 'created_at')
    search_fields = ('appointment__patient__user__username', 'doctor__user__username', 'medical_condition')
    list_filter = ('created_at', 'next_appointment')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    
# ---------------- LabResultAdmin ----------------
@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'test_request', 'lab_scientist', 'test_name', 'result', 'units', 'reference_range', 'recorded_at')
    list_filter = ('test_request', 'lab_scientist', 'test_name', 'recorded_at')
    search_fields = ('test_name', 'result', 'lab_scientist__fullname')


# ---------------- VitalsAdmin ----------------
@admin.register(Vitals)
class VitalsAdmin(admin.ModelAdmin):
    list_display = ('id', 'vital_request', 'nurse', 'blood_pressure', 'respiration_rate', 'pulse_rate', 'body_temperature', 'height_cm', 'weight_kg', 'recorded_at')
    list_filter = ('nurse', 'recorded_at')
    search_fields = ('nurse__fullname',)


# ---------------- BlogPostAdmin ----------------
@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'published', 'has_toc', 'published_date', 'created_at')
    list_filter = ('published', 'author', 'enable_toc')
    search_fields = ('title', 'content', 'author__fullname')
    readonly_fields = ('table_of_contents_preview',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'description', 'content', 'author', 'featured_image')
        }),
        ('Publication', {
            'fields': ('published', 'published_date')
        }),
        ('Table of Contents', {
            'fields': ('enable_toc', 'table_of_contents_preview', 'table_of_contents')
        }),
    )

    def has_toc(self, obj):
        return bool(obj.table_of_contents)
    has_toc.boolean = True
    has_toc.short_description = 'Has TOC'

    def table_of_contents_preview(self, obj):
        if obj.table_of_contents:
            toc_html = "<ul style='margin-left: 20px;'>"
            for item in obj.table_of_contents[:5]:  # Show first 5 items
                toc_html += f"<li>Level {item['level']}: {item['title']}</li>"
            toc_html += "</ul>"
            if len(obj.table_of_contents) > 5:
                toc_html += f"<p>... and {len(obj.table_of_contents) - 5} more items</p>"
            return toc_html
        return "No table of contents generated"
    table_of_contents_preview.short_description = 'TOC Preview'
    table_of_contents_preview.allow_tags = True
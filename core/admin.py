from django.contrib import admin
from .models import (
    User, Department, ClassSection, Subject, Allocation,
    AcademicRecord, NonAcademicRecord,
    TeacherFeedback, PerformancePrediction, SystemAlert, AttendanceRecord
)

admin.site.register(User)
admin.site.register(Department)
admin.site.register(ClassSection)
admin.site.register(Subject)
admin.site.register(Allocation)
admin.site.register(AcademicRecord)
admin.site.register(NonAcademicRecord)

# New Models
admin.site.register(TeacherFeedback)
admin.site.register(PerformancePrediction)
admin.site.register(SystemAlert)
admin.site.register(AttendanceRecord)

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser

class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return self.name

class ClassSection(models.Model):
    name = models.CharField(max_length=50) # e.g. S5-CSE-A
    department = models.ForeignKey(Department, on_delete=models.CASCADE)

    def __str__(self):
        return self.name

class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    class_section = models.ForeignKey(ClassSection, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        STAFF = "DEPT_STAFF", "Department Staff"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    class_section = models.ForeignKey(ClassSection, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    profile_pic = models.ImageField(upload_to="profiles/", blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

class Allocation(models.Model):
    """
    Links a Teacher -> Subject -> ClassSection.
    """
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': User.Role.TEACHER})
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    class_section = models.ForeignKey(ClassSection, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('teacher', 'subject', 'class_section')

    def __str__(self):
        return f"{self.teacher.username} - {self.subject.code} ({self.class_section.name})"

class AcademicRecord(models.Model):
    """
    Marks allocated by TEACHER.
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='academic_records', limit_choices_to={'role': User.Role.STUDENT})
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, help_text="The teacher who awarded the marks")
    internal_marks = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    assignment_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)

    def __str__(self):
        return f"{self.student.username} - {self.subject.code}"

class NonAcademicRecord(models.Model):
    """
    Performance data allocated by DEPT STAFF.
    one per student per semester/period (simplified as one entry here).
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='non_academic_records', limit_choices_to={'role': User.Role.STUDENT})
    attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    lab_performance = models.DecimalField(max_digits=5, decimal_places=2)
    disciplinary_score = models.IntegerField(default=100) # Assuming 100 base score

    def __str__(self):
        return f"NonAcademic - {self.student.username}"


class TeacherFeedback(models.Model):
    """
    Student-submitted (or staff-submitted) qualitative rating for a teacher on a subject.
    """
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='given_feedback',
        limit_choices_to={'role': 'STUDENT'}
    )
    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='received_feedback',
        limit_choices_to={'role': 'TEACHER'}
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    score = models.IntegerField(
        choices=[(i, str(i)) for i in range(1, 6)],
        help_text="Rating from 1 (Poor) to 5 (Excellent)"
    )
    comments = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'teacher', 'subject')

    def __str__(self):
        return f"{self.student.username} -> {self.teacher.username} [{self.subject.code}] ({self.score}/5)"


class PerformancePrediction(models.Model):
    """
    AI Prediction cache — one record per user. Updated by get_ai_prediction().
    """
    class Category(models.TextChoices):
        EXCELLENT = 'Excellent', 'Excellent'
        AVERAGE = 'Average', 'Average'
        AT_RISK = 'At-Risk', 'At-Risk'

    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='prediction'
    )
    predicted_category = models.CharField(
        max_length=20, choices=Category.choices,
        default=Category.AVERAGE
    )
    confidence_score = models.DecimalField(
        max_digits=4, decimal_places=1, default=0.0
    )
    # Stores explainable-AI factor list: [{"name": str, "value": float, "impact": str}, ...]
    insights = models.JSONField(default=dict)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}: {self.predicted_category} ({self.confidence_score}%)"


class SystemAlert(models.Model):
    """
    In-app notification / alert for a specific user.
    """
    class Severity(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        CRITICAL = 'CRITICAL', 'Critical'

    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='alerts'
    )
    message = models.CharField(max_length=500)
    severity = models.CharField(
        max_length=10, choices=Severity.choices,
        default=Severity.INFO
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.severity}] {self.user.username}: {self.message[:50]}"


class AttendanceRecord(models.Model):
    """
    Per-session attendance logged by a Teacher for each student in an Allocation.
    """
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='attendance_records',
        limit_choices_to={'role': 'STUDENT'}
    )
    allocation = models.ForeignKey(
        Allocation, on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    date = models.DateField()
    is_present = models.BooleanField(default=True)

    class Meta:
        unique_together = ('student', 'allocation', 'date')

    def __str__(self):
        status = 'Present' if self.is_present else 'Absent'
        return f"{self.student.username} - {self.allocation} - {self.date} [{status}]"

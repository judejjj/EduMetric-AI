from django.db import models
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

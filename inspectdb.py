import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edumetric_project.settings')
django.setup()

from core.models import User, Department, ClassSection, Subject, Allocation, AcademicRecord, NonAcademicRecord, TeacherFeedback

def inspect_database():
    print("\n" + "="*50)
    print("🏫 EDUMETRIC DATABASE INSPECTOR 🏫")
    print("="*50)

    print("\n🏢 DEPARTMENTS:")
    for d in Department.objects.all():
        print(f"  - [{d.code}] {d.name}")

    print("\n🏫 CLASSES & ENROLLMENT:")
    for c in ClassSection.objects.all():
        student_count = User.objects.filter(role=User.Role.STUDENT, class_section=c).count()
        print(f"  - {c.name} ({c.department.code}) -> {student_count} Students Enrolled")

    print("\n📚 SUBJECTS:")
    for s in Subject.objects.all():
        cls_name = s.class_section.name if s.class_section else 'No Class'
        print(f"  - [{s.code}] {s.name} (Taught in: {cls_name})")

    print("\n👨‍🏫 TEACHERS & WORKLOAD (ALLOCATIONS):")
    teachers = User.objects.filter(role=User.Role.TEACHER)
    for t in teachers:
        allocs = Allocation.objects.filter(teacher=t)
        print(f"  - {t.username} (Dept: {t.department.code if t.department else 'None'}) -> {allocs.count()} Subjects:")
        for a in allocs:
            print(f"      > Teaches: {a.subject.name} to {a.class_section.name}")

    print("\n📊 GENERATED AI DATA (TOTAL RECORDS):")
    print(f"  - Academic Records (Marks): {AcademicRecord.objects.count()}")
    print(f"  - Non-Academic Records (Attendance/Discipline): {NonAcademicRecord.objects.count()}")
    print(f"  - Teacher Feedback Entries: {TeacherFeedback.objects.count()}")

    print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    inspect_database()
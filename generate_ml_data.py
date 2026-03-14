import os
import django
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edumetric_project.settings')
django.setup()

from core.models import User, Department, ClassSection, Subject, Allocation, AcademicRecord, NonAcademicRecord, TeacherFeedback, PerformancePrediction, AttendanceRecord

def rebuild_database():
    print("🧹 1. Cleaning up old generated data safely...")
    # Only deletes generated users, keeping your manual admin/staff safe
    User.objects.filter(username__startswith='student_').delete()
    User.objects.filter(username__startswith='teacher_').delete()
    PerformancePrediction.objects.all().delete()

    print("🏗️ 2. Building Departments and Classes (Constraint-Safe)...")
    # Using update_or_create by 'code' prevents IntegrityErrors forever
    mca_dept, _ = Department.objects.update_or_create(code="MCA", defaults={"name": "Computer Applications"})
    imca_dept, _ = Department.objects.update_or_create(code="IMCA", defaults={"name": "Integrated MCA"})

    s1_mca, _ = ClassSection.objects.get_or_create(name="S1-MCA", department=mca_dept)
    s4_mca, _ = ClassSection.objects.get_or_create(name="S4-MCA", department=mca_dept)
    s4_imca, _ = ClassSection.objects.get_or_create(name="S4-IMCA", department=imca_dept)
    s9_imca, _ = ClassSection.objects.get_or_create(name="S9-IMCA", department=imca_dept)

    print("📚 3. Creating Subjects...")
    # Using specific codes so they don't clash with any you made manually
    sub_web, _ = Subject.objects.update_or_create(code="MCA111", defaults={"name": "Web Design", "class_section": s1_mca})
    sub_py, _  = Subject.objects.update_or_create(code="MCA112", defaults={"name": "Python Programming", "class_section": s1_mca})
    
    sub_adb, _ = Subject.objects.update_or_create(code="MCA411", defaults={"name": "Advanced Database", "class_section": s4_mca})
    sub_ml, _  = Subject.objects.update_or_create(code="MCA412", defaults={"name": "Machine Learning", "class_section": s4_mca})
    
    sub_os, _  = Subject.objects.update_or_create(code="IMCA411", defaults={"name": "Operating Systems", "class_section": s4_imca})
    sub_ds, _  = Subject.objects.update_or_create(code="IMCA412", defaults={"name": "Data Structures", "class_section": s4_imca})
    
    sub_java, _= Subject.objects.update_or_create(code="IMCA911", defaults={"name": "Java Programming", "class_section": s9_imca})
    sub_daa, _ = Subject.objects.update_or_create(code="IMCA912", defaults={"name": "DAA", "class_section": s9_imca})

    print("👨‍🏫 4. Creating Teachers & Workload Allocations...")
    teachers = []
    for i in range(1, 6):
        t = User.objects.create_user(username=f"teacher_{i}", password="password123", role=User.Role.TEACHER, department=mca_dept if i <=3 else imca_dept)
        teachers.append(t)
    t1, t2, t3, t4, t5 = teachers

    # Enforce Blueprint Workloads
    allocs = [
        # Teacher 1 (Heavy - 3 Subjects across 2 Departments)
        Allocation.objects.create(teacher=t1, subject=sub_py, class_section=s1_mca),
        Allocation.objects.create(teacher=t1, subject=sub_java, class_section=s9_imca),
        Allocation.objects.create(teacher=t1, subject=sub_os, class_section=s4_imca),
        
        # Teacher 2 (Medium - 2 Subjects) -> Will be the "Strict but Effective" AI pattern
        Allocation.objects.create(teacher=t2, subject=sub_daa, class_section=s9_imca),
        Allocation.objects.create(teacher=t2, subject=sub_web, class_section=s1_mca),
        
        # Teacher 3 (Medium - 2 Subjects)
        Allocation.objects.create(teacher=t3, subject=sub_adb, class_section=s4_mca),
        Allocation.objects.create(teacher=t3, subject=sub_ds, class_section=s4_imca),
        
        # Teacher 4 (Light - 1 Subject) -> Will be the "Popular but Ineffective" AI pattern
        Allocation.objects.create(teacher=t4, subject=sub_ml, class_section=s4_mca)
        
        # Teacher 5 has NO allocations (Reserve)
    ]

    print("🎓 5. Enrolling 80 Students & Generating AI Intelligence Patterns...")
    
    def populate_class(cls_section, dept, student_count, prefix):
        class_allocations = [a for a in allocs if a.class_section == cls_section]
        
        for i in range(student_count):
            student = User.objects.create_user(username=f"student_{prefix}_{i+1}", password="password123", role=User.Role.STUDENT, department=dept, class_section=cls_section)
            
            attendance = random.uniform(50, 98)
            is_good_student = attendance > 75
            
            NonAcademicRecord.objects.create(
                student=student, attendance_percentage=attendance,
                lab_performance=random.uniform(60, 100) if is_good_student else random.uniform(30, 60),
                disciplinary_score=random.randint(70, 100) if is_good_student else random.randint(40, 69)
            )

            for alloc in class_allocations:
                # --- HYBRID AI DATA INJECTION ---
                if alloc.teacher == t2:
                    # STRICT: Hard grading, terrible feedback, but good actual knowledge
                    internal_marks = random.uniform(25, 45) # Lower internals
                    feedback = random.randint(1, 2)         # Students hate it
                elif alloc.teacher == t4:
                    # POPULAR: Easy grading, amazing feedback, but students actually fail
                    internal_marks = random.uniform(40, 50) # Everyone gets an A
                    feedback = random.randint(4, 5)         # Students love it
                else:
                    # NORMAL: Marks match effort
                    internal_marks = random.uniform(30, 50) if is_good_student else random.uniform(10, 29)
                    feedback = random.randint(4, 5) if internal_marks > 30 else random.randint(2, 3)

                AcademicRecord.objects.create(
                    student=student, subject=alloc.subject, teacher=alloc.teacher,
                    internal_marks=internal_marks, 
                    assignment_score=random.uniform(10, 20) if is_good_student else random.uniform(2, 9)
                )
                
                TeacherFeedback.objects.create(
                    student=student, teacher=alloc.teacher, subject=alloc.subject,
                    score=feedback, comments=f"Feedback for {alloc.subject.name}"
                )

    populate_class(s1_mca, mca_dept, 20, "s1mca")
    populate_class(s4_mca, mca_dept, 20, "s4mca")
    populate_class(s4_imca, imca_dept, 20, "s4imca")
    populate_class(s9_imca, imca_dept, 20, "s9imca")

    print("✅ Success! Database is perfectly structured and constraint-safe.")

if __name__ == "__main__":
    rebuild_database()
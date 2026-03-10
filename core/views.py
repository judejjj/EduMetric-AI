import csv
import io
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Avg, Q
from django.contrib import messages
from django.utils import timezone

from .models import (
    User, Department, ClassSection, Subject, Allocation,
    AcademicRecord, NonAcademicRecord,
    TeacherFeedback, PerformancePrediction, SystemAlert, AttendanceRecord,
)

# ---------------------------------------------------------------------------
# Helper: Role predicate functions (UNCHANGED)
# ---------------------------------------------------------------------------

def is_admin(user):
    return user.role == User.Role.ADMIN

def is_staff(user):
    return user.role == User.Role.STAFF

def is_teacher(user):
    return user.role == User.Role.TEACHER

def is_student(user):
    return user.role == User.Role.STUDENT


# ---------------------------------------------------------------------------
# Helper: AI Prediction Engine (Rule-Based Placeholder)
# ---------------------------------------------------------------------------

def get_ai_prediction(user):
    """
    Rule-based placeholder for future Scikit-Learn model.
    Reads AcademicRecord and NonAcademicRecord for a Student user,
    applies threshold rules, and upserts a PerformancePrediction row.
    Returns the PerformancePrediction instance (or None if no data).
    """
    if user.role != User.Role.STUDENT:
        return None

    # --- 1. Gather raw metrics ---
    academic_qs = AcademicRecord.objects.filter(student=user)
    avg_internal  = academic_qs.aggregate(v=Avg('internal_marks'))['v'] or 0.0
    avg_assign    = academic_qs.aggregate(v=Avg('assignment_score'))['v'] or 0.0
    avg_marks     = (float(avg_internal) + float(avg_assign)) / 2

    non_academic  = NonAcademicRecord.objects.filter(student=user).last()
    attendance    = float(non_academic.attendance_percentage) if non_academic else 0.0
    lab_perf      = float(non_academic.lab_performance)       if non_academic else 0.0
    discipline    = float(non_academic.disciplinary_score)    if non_academic else 100.0

    # --- 2. Classify ---
    if avg_marks >= 80 and attendance >= 85:
        category   = PerformancePrediction.Category.EXCELLENT
        confidence = 90.0
    elif avg_marks >= 55 and attendance >= 75:
        category   = PerformancePrediction.Category.AVERAGE
        confidence = 75.0
    else:
        category   = PerformancePrediction.Category.AT_RISK
        confidence = 85.0

    # --- 3. Build Explainable AI insights ---
    insights = {
        "factors": [
            {
                "name":   "Average Academic Marks",
                "value":  round(avg_marks, 1),
                "impact": "High" if avg_marks >= 80 else ("Medium" if avg_marks >= 55 else "Low"),
                "tip":    "Keep up consistent assignment submissions." if avg_marks >= 70
                          else "Focus on improving internal exam scores.",
            },
            {
                "name":   "Attendance Rate",
                "value":  attendance,
                "impact": "High" if attendance >= 85 else ("Medium" if attendance >= 75 else "Low"),
                "tip":    "Maintain punctuality." if attendance >= 75
                          else "Low attendance is the primary risk factor — attend all sessions.",
            },
            {
                "name":   "Lab Performance",
                "value":  lab_perf,
                "impact": "High" if lab_perf >= 80 else ("Medium" if lab_perf >= 60 else "Low"),
                "tip":    "Lab scores are strong." if lab_perf >= 80
                          else "Spend more time on practicals to boost lab scores.",
            },
            {
                "name":   "Discipline Score",
                "value":  discipline,
                "impact": "High" if discipline >= 90 else ("Medium" if discipline >= 70 else "Low"),
                "tip":    "Discipline score is excellent." if discipline >= 90
                          else "Address disciplinary deductions with your department staff.",
            },
        ],
        "summary_text": (
            "You are performing excellently. Keep it up!" if category == PerformancePrediction.Category.EXCELLENT
            else "Performance is average. Targeted effort in weak areas will improve your grade."
            if category == PerformancePrediction.Category.AVERAGE
            else "You are at risk of underperforming. Immediate action is recommended."
        ),
    }

    # Build per-subject improvement suggestions
    suggestions = []
    for rec in academic_qs.select_related('subject'):
        total = float(rec.internal_marks) + float(rec.assignment_score)
        if float(rec.assignment_score) < 10:
            suggestions.append(f"Complete all assignments in {rec.subject.name} to recover {10 - float(rec.assignment_score):.1f} points.")
        if float(rec.internal_marks) < 30:
            suggestions.append(f"Revise {rec.subject.name} theory — internal marks are critically low.")

    insights["improvement_suggestions"] = suggestions

    # --- 4. Upsert into DB ---
    prediction, _ = PerformancePrediction.objects.update_or_create(
        user=user,
        defaults={
            'predicted_category': category,
            'confidence_score':   confidence,
            'insights':           insights,
        }
    )

    # --- 5. Auto-create SystemAlert if At-Risk ---
    if category == PerformancePrediction.Category.AT_RISK:
        SystemAlert.objects.get_or_create(
            user=user,
            message="Your performance is classified as At-Risk. Please contact your advisor.",
            defaults={'severity': SystemAlert.Severity.CRITICAL, 'is_read': False}
        )

    return prediction


# ---------------------------------------------------------------------------
# Auth Views (UNCHANGED)
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect_role(request.user)

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect_role(user)
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

def redirect_role(user):
    if user.role == User.Role.ADMIN:
        return redirect('admin_dashboard')
    elif user.role == User.Role.STAFF:
        return redirect('staff_dashboard')
    elif user.role == User.Role.TEACHER:
        return redirect('teacher_dashboard')
    elif user.role == User.Role.STUDENT:
        return redirect('student_dashboard')
    return redirect('login')


# ---------------------------------------------------------------------------
# Admin Dashboard (UPDATED: at-risk, underperforming, counters)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    # Base counts
    all_students = User.objects.filter(role=User.Role.STUDENT)
    all_teachers = User.objects.filter(role=User.Role.TEACHER)

    # --- At-Risk Detection ---
    # Students with attendance < 75% (from NonAcademicRecord)
    low_attendance_ids = NonAcademicRecord.objects.filter(
        attendance_percentage__lt=75
    ).values_list('student_id', flat=True)

    # Students with average internal marks < 40
    low_marks_ids = AcademicRecord.objects.values('student').annotate(
        avg_internal=Avg('internal_marks')
    ).filter(avg_internal__lt=40).values_list('student', flat=True)

    at_risk_ids = set(list(low_attendance_ids) + list(low_marks_ids))
    at_risk_students = all_students.filter(id__in=at_risk_ids).select_related('department', 'class_section')

    # Annotate with their attendance & marks
    at_risk_display = []
    for s in at_risk_students:
        nar = NonAcademicRecord.objects.filter(student=s).last()
        avg_m = AcademicRecord.objects.filter(student=s).aggregate(v=Avg('internal_marks'))['v']
        at_risk_display.append({
            'user': s,
            'attendance': float(nar.attendance_percentage) if nar else None,
            'avg_marks':  round(float(avg_m), 1) if avg_m else None,
        })

    # --- Underperforming Teachers ---
    # Teachers with avg feedback score < 3.0 (or no feedback yet shows 'N/A')
    teacher_feedback = TeacherFeedback.objects.values('teacher').annotate(
        avg_score=Avg('score')
    ).filter(avg_score__lt=3.0)

    underperforming_ids = [t['teacher'] for t in teacher_feedback]
    underperforming_teachers = all_teachers.filter(
        id__in=underperforming_ids
    ).select_related('department')

    underperforming_display = []
    for t in underperforming_teachers:
        avg_fb = TeacherFeedback.objects.filter(teacher=t).aggregate(v=Avg('score'))['v']
        underperforming_display.append({
            'user': t,
            'avg_feedback': round(float(avg_fb), 1) if avg_fb else None,
        })

    context = {
        'total_students':          all_students.count(),
        'total_teachers':          all_teachers.count(),
        'total_depts':             Department.objects.count(),
        'users':                   User.objects.all().select_related('department'),
        'departments':             Department.objects.all(),
        'at_risk_students':        at_risk_display,
        'underperforming_teachers':underperforming_display,
    }
    return render(request, 'admin_dashboard.html', context)


# ---------------------------------------------------------------------------
# Admin: Bulk Upload (CSV)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_admin)
def admin_bulk_upload(request):
    """
    POST: accept a .csv file with columns: username,email,role,department_code
    Bulk-creates users (skipping existing usernames).
    """
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, "No file uploaded.")
            return redirect('admin_bulk_upload')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Only .csv files are supported.")
            return redirect('admin_bulk_upload')

        try:
            decoded = csv_file.read().decode('utf-8-sig')  # handle BOM
            reader  = csv.DictReader(io.StringIO(decoded))

            created_count = 0
            skipped_count = 0
            errors        = []

            for i, row in enumerate(reader, start=2):  # row 1 = header
                username   = (row.get('username') or '').strip()
                email      = (row.get('email') or '').strip()
                role_raw   = (row.get('role') or 'STUDENT').strip().upper()
                dept_code  = (row.get('department_code') or '').strip()

                if not username:
                    errors.append(f"Row {i}: Missing username — skipped.")
                    continue

                if User.objects.filter(username=username).exists():
                    skipped_count += 1
                    continue

                # Map role string to Role choice
                role_map = {
                    'ADMIN':       User.Role.ADMIN,
                    'DEPT_STAFF':  User.Role.STAFF,
                    'STAFF':       User.Role.STAFF,
                    'TEACHER':     User.Role.TEACHER,
                    'STUDENT':     User.Role.STUDENT,
                }
                role_val = role_map.get(role_raw, User.Role.STUDENT)

                dept = None
                if dept_code:
                    dept = Department.objects.filter(code=dept_code).first()

                try:
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=username,   # default password = username
                        role=role_val,
                    )
                    if dept:
                        user.department = dept
                        user.save()
                    created_count += 1
                except Exception as e:
                    errors.append(f"Row {i} ({username}): {str(e)}")

            msg = f"Upload complete: {created_count} created, {skipped_count} skipped."
            if errors:
                msg += f" {len(errors)} error(s)."
                for err in errors[:5]:
                    messages.warning(request, err)
            messages.success(request, msg)

        except Exception as e:
            messages.error(request, f"Failed to process file: {str(e)}")

        return redirect('admin_bulk_upload')

    return render(request, 'admin_bulk_upload.html')


# ---------------------------------------------------------------------------
# Admin: Export Users as CSV
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_admin)
def admin_export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="edumetric_users.csv"'

    writer = csv.writer(response)
    writer.writerow(['Username', 'Email', 'Role', 'Department', 'Class Section', 'Phone'])

    for user in User.objects.all().select_related('department', 'class_section').order_by('role', 'username'):
        writer.writerow([
            user.username,
            user.email,
            user.get_role_display(),
            user.department.name if user.department else '',
            user.class_section.name if user.class_section else '',
            user.phone or '',
        ])

    return response


# ---------------------------------------------------------------------------
# Staff Dashboard (UPDATED: dept counters)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_staff)
def staff_dashboard(request):
    dept = request.user.department
    if not dept:
        messages.error(request, "You are not assigned to a department.")
        return redirect('login')

    teachers = User.objects.filter(role=User.Role.TEACHER, department=dept)
    students = User.objects.filter(role=User.Role.STUDENT, department=dept)

    # Attach allocations to each teacher for display
    for t in teachers:
        t.allocations_list = Allocation.objects.filter(teacher=t)

    context = {
        'dept':           dept,
        'students':       students,
        'teachers':       teachers,
        'total_students': students.count(),
        'total_teachers': teachers.count(),
    }
    return render(request, 'staff_dashboard.html', context)


# ---------------------------------------------------------------------------
# Staff: Class Performance Report
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_staff)
def staff_class_report(request, class_id):
    dept     = request.user.department
    cls      = get_object_or_404(ClassSection, id=class_id, department=dept)
    students = User.objects.filter(role=User.Role.STUDENT, class_section=cls)

    # Compute avg attendance (from NonAcademicRecord) per student
    student_data = []
    total_attendance = 0
    total_marks      = 0
    total_assign     = 0
    count            = 0

    for s in students:
        nar      = NonAcademicRecord.objects.filter(student=s).last()
        avg_i    = AcademicRecord.objects.filter(student=s).aggregate(v=Avg('internal_marks'))['v']
        avg_a    = AcademicRecord.objects.filter(student=s).aggregate(v=Avg('assignment_score'))['v']
        att      = float(nar.attendance_percentage) if nar else None
        marks    = round(float(avg_i), 1) if avg_i else None
        assign   = round(float(avg_a), 1) if avg_a else None
        if att is not None:  total_attendance += att; count += 1
        if marks is not None: total_marks += marks
        if assign is not None: total_assign += assign
        student_data.append({
            'user':       s,
            'attendance': att,
            'avg_marks':  marks,
            'avg_assign': assign,
        })

    n = max(count, 1)
    context = {
        'cls':              cls,
        'student_data':     student_data,
        'avg_attendance':   round(total_attendance / n, 1),
        'avg_marks':        round(total_marks / n, 1) if count else None,
        'avg_assign':       round(total_assign / n, 1) if count else None,
        'student_count':    students.count(),
    }
    return render(request, 'staff_class_report.html', context)


# ---------------------------------------------------------------------------
# Teacher Dashboard (UPDATED: effectiveness score + AI card)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_teacher)
def teacher_dashboard(request):
    allocations = Allocation.objects.filter(teacher=request.user).select_related('subject', 'class_section')

    # Teaching Effectiveness Score = avg of all internal_marks recorded by this teacher
    effectiveness_agg = AcademicRecord.objects.filter(
        teacher=request.user
    ).aggregate(avg_marks=Avg('internal_marks'), avg_assign=Avg('assignment_score'))

    avg_internal = effectiveness_agg['avg_marks'] or 0.0
    avg_assign   = effectiveness_agg['avg_assign'] or 0.0
    # Scale to 100: internal max ~50, assignment max ~20 → combined max ~70; normalise to 100
    raw_score    = (float(avg_internal) / 50.0 * 70) + (float(avg_assign) / 20.0 * 30)
    effectiveness_score = round(min(raw_score, 100), 1)

    # Per-allocation stats for the AI card
    allocation_insights = []
    for alloc in allocations:
        students_in_class = User.objects.filter(
            role=User.Role.STUDENT, class_section=alloc.class_section
        ).count()
        records = AcademicRecord.objects.filter(
            teacher=request.user, subject=alloc.subject
        )
        avg_i = records.aggregate(v=Avg('internal_marks'))['v']
        pass_count = records.filter(internal_marks__gte=35).count()
        allocation_insights.append({
            'allocation':       alloc,
            'student_count':    students_in_class,
            'avg_internal':     round(float(avg_i), 1) if avg_i else 'N/A',
            'pass_count':       pass_count,
            'records_entered':  records.count(),
        })

    # Build AI explanation text
    if effectiveness_score >= 80:
        ai_text = "Excellent teaching effectiveness! Your students show strong performance across all subjects."
    elif effectiveness_score >= 55:
        ai_text = "Good teaching effectiveness. Some subjects have lower average marks — consider revision sessions for struggling students."
    elif allocations.exists():
        ai_text = "Teaching effectiveness needs attention. Enter student marks to see a more accurate score."
    else:
        ai_text = "No allocations yet. Your score will be calculated once student marks are entered."

    # Avg feedback from students
    avg_feedback = TeacherFeedback.objects.filter(teacher=request.user).aggregate(v=Avg('score'))['v']

    context = {
        'allocations':          allocations,
        'effectiveness_score':  effectiveness_score,
        'ai_text':              ai_text,
        'avg_feedback':         round(float(avg_feedback), 1) if avg_feedback else None,
        'allocation_insights':  allocation_insights,
    }
    return render(request, 'teacher_dashboard.html', context)


# ---------------------------------------------------------------------------
# Teacher: Attendance Entry
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_teacher)
def teacher_attendance(request, allocation_id):
    allocation = get_object_or_404(Allocation, id=allocation_id, teacher=request.user)
    students   = User.objects.filter(
        role=User.Role.STUDENT,
        class_section=allocation.class_section
    ).order_by('username')

    today = timezone.now().date()

    if request.method == 'POST':
        # present_ids is a list of student IDs who were marked present via checkbox
        present_ids = set(map(int, request.POST.getlist('present_ids')))
        saved_count = 0
        for student in students:
            is_present = student.id in present_ids
            _, created = AttendanceRecord.objects.update_or_create(
                student=student,
                allocation=allocation,
                date=today,
                defaults={'is_present': is_present}
            )
            saved_count += 1
        messages.success(request, f"Attendance recorded for {today} — {len(present_ids)}/{saved_count} present.")
        return redirect('teacher_attendance', allocation_id=allocation.id)

    # Fetch today's existing records (if editing same day)
    existing = {
        r.student_id: r.is_present
        for r in AttendanceRecord.objects.filter(allocation=allocation, date=today)
    }

    student_data = [
        {'user': s, 'is_present': existing.get(s.id, True)}
        for s in students
    ]

    context = {
        'allocation':   allocation,
        'student_data': student_data,
        'today':        today,
    }
    return render(request, 'teacher_attendance.html', context)


# ---------------------------------------------------------------------------
# Student Dashboard (UPDATED: AI prediction, warnings, suggestions)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_student)
def student_dashboard(request):
    academic_records = AcademicRecord.objects.filter(student=request.user).select_related('subject', 'teacher')
    non_academic     = NonAcademicRecord.objects.filter(student=request.user).last()

    # Run AI prediction (rule engine)
    prediction = get_ai_prediction(request.user)

    # Low-attendance warning
    low_attendance_warning = (
        non_academic and float(non_academic.attendance_percentage) < 75
    )

    # Improvement suggestions from prediction insights
    suggestions = []
    if prediction and isinstance(prediction.insights, dict):
        suggestions = prediction.insights.get('improvement_suggestions', [])

    context = {
        'academic_records':       academic_records,
        'non_academic':           non_academic,
        'prediction':             prediction,
        'low_attendance_warning': low_attendance_warning,
        'suggestions':            suggestions,
    }
    return render(request, 'student_dashboard.html', context)


# ---------------------------------------------------------------------------
# Existing Action Views (UNCHANGED)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_teacher)
def manage_marks(request, allocation_id):
    allocation = get_object_or_404(Allocation, id=allocation_id, teacher=request.user)
    students = User.objects.filter(
        role=User.Role.STUDENT,
        class_section=allocation.class_section
    )

    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        internal   = request.POST.get('internal')
        assignment = request.POST.get('assignment')

        student = get_object_or_404(User, id=student_id)

        AcademicRecord.objects.update_or_create(
            student=student,
            subject=allocation.subject,
            teacher=request.user,
            defaults={'internal_marks': internal, 'assignment_score': assignment}
        )
        messages.success(request, f"Marks updated for {student.username}")
        return redirect('manage_marks', allocation_id=allocation.id)

    # Attach existing record for each student (for pre-fill)
    for s in students:
        s.existing_record = AcademicRecord.objects.filter(
            student=s, subject=allocation.subject, teacher=request.user
        ).first()

    return render(request, 'manage_marks.html', {'allocation': allocation, 'students': students})


@login_required
@user_passes_test(is_admin)
def create_allocation(request):
    if request.method == 'POST':
        teacher_id       = request.POST.get('teacher_id')
        subject_id       = request.POST.get('subject_id')
        class_section_id = request.POST.get('class_section_id')

        try:
            teacher       = User.objects.get(id=teacher_id, role=User.Role.TEACHER)
            subject       = Subject.objects.get(id=subject_id)
            class_section = ClassSection.objects.get(id=class_section_id)

            Allocation.objects.create(teacher=teacher, subject=subject, class_section=class_section)
            messages.success(request, "Allocation created successfully!")
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Error creating allocation: {str(e)}")

    context = {
        'teachers':      User.objects.filter(role=User.Role.TEACHER),
        'subjects':      Subject.objects.all(),
        'class_sections':ClassSection.objects.all(),
    }
    return render(request, 'create_allocation.html', context)


@login_required
@user_passes_test(is_admin)
def add_user(request):
    if request.method == 'POST':
        username      = request.POST.get('username')
        email         = request.POST.get('email')
        password      = request.POST.get('password')
        if not password:
            password = username
        role          = request.POST.get('role')
        department_id = request.POST.get('department_id')

        try:
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists.")
                return redirect('add_user')

            user = User.objects.create_user(username=username, email=email, password=password, role=role)

            if department_id:
                user.department = Department.objects.get(id=department_id)
                user.save()

            messages.success(request, f"User {username} created successfully as {role}.")
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Error creating user: {str(e)}")

    context = {
        'roles':       User.Role.choices,
        'departments': Department.objects.all(),
    }
    return render(request, 'add_user.html', context)


@login_required
@user_passes_test(is_admin)
def create_department(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')

        try:
            if Department.objects.filter(code=code).exists():
                messages.error(request, f"Department code '{code}' already exists.")
            else:
                Department.objects.create(name=name, code=code)
                messages.success(request, f"Department '{name}' created successfully.")
                return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Error creating department: {str(e)}")

    return render(request, 'create_department.html')


@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        user_obj.username = request.POST.get('username')
        user_obj.email    = request.POST.get('email')

        password = request.POST.get('password')
        if password:
            user_obj.set_password(password)

        user_obj.role = request.POST.get('role')
        dept_id = request.POST.get('department_id')
        if dept_id:
            user_obj.department = Department.objects.get(id=dept_id)
        else:
            user_obj.department = None

        try:
            user_obj.save()
            messages.success(request, f"User {user_obj.username} updated successfully.")
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Error updating user: {str(e)}")

    context = {
        'edit_user':   user_obj,
        'roles':       User.Role.choices,
        'departments': Department.objects.all(),
    }
    return render(request, 'edit_user.html', context)


@login_required
@user_passes_test(is_admin)
def edit_department(request, dept_id):
    dept = get_object_or_404(Department, id=dept_id)
    if request.method == 'POST':
        dept.name = request.POST.get('name')
        dept.code = request.POST.get('code')
        try:
            dept.save()
            messages.success(request, f"Department {dept.name} updated successfully.")
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Error updating department: {str(e)}")

    return render(request, 'edit_department.html', {'dept': dept})


@login_required
@user_passes_test(is_staff)
def staff_add_user(request):
    dept        = request.user.department
    target_role = request.GET.get('role', 'student').lower()

    if request.method == 'POST':
        username         = request.POST.get('username')
        email            = request.POST.get('email')
        password         = request.POST.get('password')
        if not password:
            password = username
        role_input       = request.POST.get('role')
        class_section_id = request.POST.get('class_section_id') or request.POST.get('class_id')

        department_id    = request.POST.get('department_id')

        try:
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists.")
            else:
                role_val = User.Role.TEACHER if role_input and role_input.upper() == 'TEACHER' else User.Role.STUDENT
                user     = User.objects.create_user(username=username, email=email, password=password, role=role_val)
                
                selected_dept = dept
                if department_id:
                    selected_dept = Department.objects.get(id=department_id)
                user.department = selected_dept

                if role_val == User.Role.STUDENT and class_section_id:
                    try:
                        user.class_section = ClassSection.objects.get(id=class_section_id)
                    except ClassSection.DoesNotExist:
                        pass

                user.save()
                messages.success(request, f"{role_input.title()} {username} added to {dept.name}.")
                return redirect('staff_dashboard')
        except Exception as e:
            messages.error(request, f"Error creating user: {str(e)}")

    classes = ClassSection.objects.all()
    departments = Department.objects.all()
    return render(request, 'staff_add_user.html', {'classes': classes, 'departments': departments, 'target_role': target_role})


@login_required
@user_passes_test(is_staff)
def staff_delete_user(request, user_id):
    user_obj = get_object_or_404(User, id=user_id, department=request.user.department, role=User.Role.STUDENT)

    if request.method == 'POST':
        username = user_obj.username
        user_obj.delete()
        messages.success(request, f"Student {username} deleted successfully.")
        return redirect('staff_dashboard')

    return render(request, 'staff_delete_user.html', {'student': user_obj})


@login_required
@user_passes_test(is_staff)
def staff_edit_user(request, user_id):
    user_obj = get_object_or_404(User, id=user_id, department=request.user.department)

    if user_obj.role == User.Role.ADMIN:
        messages.error(request, "Cannot edit Admin users.")
        return redirect('staff_dashboard')

    if request.method == 'POST':
        user_obj.username = request.POST.get('username')
        user_obj.email    = request.POST.get('email')

        password = request.POST.get('password')
        if password:
            user_obj.set_password(password)

        try:
            user_obj.save()
            messages.success(request, f"User {user_obj.username} updated.")
            return redirect('staff_dashboard')
        except Exception as e:
            messages.error(request, f"Error updating: {str(e)}")

    return render(request, 'staff_edit_user.html', {'edit_user': user_obj})


@login_required
@user_passes_test(is_staff)
def staff_manage_classes(request):
    dept = request.user.department
    if request.method == 'POST':
        name = request.POST.get('name')
        try:
            if ClassSection.objects.filter(name=name, department=dept).exists():
                messages.error(request, f"Class '{name}' already exists in this department.")
            else:
                ClassSection.objects.create(name=name, department=dept)
                messages.success(request, f"Class '{name}' created successfully.")
                return redirect('staff_manage_classes')
        except Exception as e:
            messages.error(request, f"Error creating class: {str(e)}")

    classes = ClassSection.objects.filter(department=dept)
    return render(request, 'staff_manage_classes.html', {'classes': classes, 'dept': dept})


@login_required
@user_passes_test(is_staff)
def staff_manage_subjects(request):
    dept = request.user.department

    if request.method == 'POST':
        name             = request.POST.get('name')
        code             = request.POST.get('code')
        class_section_id = request.POST.get('class_section_id')

        try:
            if Subject.objects.filter(code=code).exists():
                messages.error(request, f"Subject code '{code}' already exists.")
            else:
                subject = Subject.objects.create(name=name, code=code)
                if class_section_id:
                    subject.class_section = ClassSection.objects.get(id=class_section_id, department=dept)
                subject.save()
                messages.success(request, f"Subject '{name}' created successfully.")
                return redirect('staff_manage_subjects')
        except Exception as e:
            messages.error(request, f"Error creating subject: {str(e)}")

    classes      = ClassSection.objects.filter(department=dept)
    class_filter = request.GET.get('class_filter')
    subjects     = Subject.objects.filter(class_section__department=dept) | Subject.objects.filter(class_section__isnull=True)

    if class_filter:
        subjects = subjects.filter(class_section_id=class_filter)

    subjects = subjects.distinct()

    return render(request, 'staff_manage_subjects.html', {
        'subjects':       subjects,
        'classes':        classes,
        'current_filter': class_filter,
    })


@login_required
@user_passes_test(is_staff)
def staff_create_allocation(request):
    dept = request.user.department
    if request.method == 'POST':
        teacher_id       = request.POST.get('teacher_id')
        subject_id       = request.POST.get('subject_id')
        class_section_id = request.POST.get('class_section_id')

        try:
            teacher       = User.objects.get(id=teacher_id, role=User.Role.TEACHER)
            subject       = Subject.objects.get(id=subject_id)
            class_section = ClassSection.objects.get(id=class_section_id)

            if class_section.department != dept:
                messages.error(request, "You can only allocate for your department's classes.")
                return redirect('staff_create_allocation')

            Allocation.objects.create(teacher=teacher, subject=subject, class_section=class_section)
            messages.success(request, "Allocation created successfully!")
            return redirect('staff_dashboard')
        except Exception as e:
            messages.error(request, f"Error creating allocation: {str(e)}")

    teachers = User.objects.filter(role=User.Role.TEACHER, department=dept)
    classes  = ClassSection.objects.filter(department=dept)
    subjects = Subject.objects.all()

    context = {
        'teachers': teachers,
        'classes':  classes,
        'subjects': subjects,
    }
    return render(request, 'staff_create_allocation.html', context)


@login_required
def get_subjects_by_class(request):
    class_id = request.GET.get('class_id')
    subjects = Subject.objects.filter(class_section_id=class_id).values('id', 'name', 'code')
    return JsonResponse({'subjects': list(subjects)})


@login_required
@user_passes_test(is_staff)
def staff_delete_class(request, class_id):
    dept      = request.user.department
    class_obj = get_object_or_404(ClassSection, id=class_id, department=dept)

    if request.method == 'POST':
        name = class_obj.name
        class_obj.delete()
        messages.success(request, f"Class '{name}' deleted successfully.")
        return redirect('staff_manage_classes')

    return render(request, 'confirm_delete.html', {
        'item': f"Class: {class_obj.name}", 'back_url': 'staff_manage_classes'
    })


@login_required
@user_passes_test(is_staff)
def staff_delete_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)

    if request.method == 'POST':
        name = subject.name
        subject.delete()
        messages.success(request, f"Subject '{name}' deleted successfully.")
        return redirect('staff_manage_subjects')

    return render(request, 'confirm_delete.html', {
        'item': f"Subject: {subject.name} ({subject.code})", 'back_url': 'staff_manage_subjects'
    })


@login_required
@user_passes_test(is_staff)
def staff_manage_non_academic(request, student_id):
    student = get_object_or_404(User, id=student_id, department=request.user.department)
    record, created = NonAcademicRecord.objects.get_or_create(
        student=student,
        defaults={
            'attendance_percentage': 0.00,
            'lab_performance':       0.00,
            'disciplinary_score':    100,
        }
    )

    if request.method == 'POST':
        attendance = request.POST.get('attendance')
        lab        = request.POST.get('lab')
        discipline = request.POST.get('discipline')

        try:
            record.attendance_percentage = attendance
            record.lab_performance       = lab
            record.disciplinary_score    = discipline
            record.save()
            messages.success(request, f"Records updated for {student.username}")
            return redirect('staff_dashboard')
        except Exception as e:
            messages.error(request, f"Error updating records: {str(e)}")

    return render(request, 'staff_manage_non_academic.html', {'student': student, 'record': record})

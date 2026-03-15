import csv
import re
import io
from datetime import datetime, timedelta
import joblib
import pandas as pd
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Avg, Q
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse

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

def get_ai_prediction(student):
    """Predicts student category using the trained ML model and updates PerformancePrediction."""
    try:
        # Load the saved brain
        model = joblib.load('student_model.pkl')
        
        # Get latest data for this specific student
        academic = AcademicRecord.objects.filter(student=student).first()
        non_academic = NonAcademicRecord.objects.filter(student=student).first()
        
        if not academic or not non_academic:
            return None

        # Prepare data for the model (must match the training features)
        features = pd.DataFrame([{
            'internal_marks': float(academic.internal_marks),
            'assignment_score': float(academic.assignment_score),
            'attendance_percentage': float(non_academic.attendance_percentage),
            'disciplinary_score': float(non_academic.disciplinary_score)
        }])

        # Get the prediction (Excellent/Average/At-Risk)
        category = model.predict(features)[0]
        
        # Explainable AI (XAI) Logic
        insight = ""
        suggestions = []
        if category == 'At-Risk':
            if float(non_academic.attendance_percentage) < 75:
                insight = "Low attendance is the primary risk factor."
                suggestions.append("Improve attendance to at least 75%.")
            else:
                insight = "Improve internal marks to boost performance."
                suggestions.append("Focus on upcoming internal assessments.")
        else:
            insight = "Keep up the consistent effort across all metrics!"

        # Create/Update PerformancePrediction row
        prediction, _ = PerformancePrediction.objects.update_or_create(
            user=student,
            defaults={
                'predicted_category': category,
                'confidence_score': 85.0, # Placeholder confidence
                'insights': {
                    'summary_text': insight,
                    'improvement_suggestions': suggestions
                },
            }
        )

        # Auto-create SystemAlert if At-Risk
        if category == 'At-Risk':
            SystemAlert.objects.get_or_create(
                user=student,
                message="Your performance is classified as At-Risk. Please contact your advisor.",
                defaults={'severity': SystemAlert.Severity.CRITICAL, 'is_read': False}
            )

        return prediction
    except Exception as e:
        print(f"ML Prediction Error: {e}")
        return None


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
    
@login_required
@user_passes_test(is_admin)
def admin_send_alert(request, user_id):
    """Allows admin to send a system alert to a specific teacher or student."""
    recipient = get_object_or_404(User, id=user_id)
    message = request.POST.get('message', 'Administrator has flagged your performance for review.')
    severity = request.POST.get('severity', SystemAlert.Severity.WARNING)
    
    SystemAlert.objects.create(
        user=recipient,
        message=message,
        severity=severity,
        is_read=False
    )
    
    messages.success(request, f"Alert sent to {recipient.username}.")
    return redirect('admin_dashboard')

@login_required
@user_passes_test(is_admin)
def admin_export_at_risk_csv(request):
    """Exports At-Risk students as CSV using the same logic as the dashboard."""
    low_attendance_ids = NonAcademicRecord.objects.filter(attendance_percentage__lt=75).values_list('student_id', flat=True)
    low_marks_ids = AcademicRecord.objects.values('student').annotate(avg_internal=Avg('internal_marks')).filter(avg_internal__lt=40).values_list('student', flat=True)
    at_risk_ids = set(list(low_attendance_ids) + list(low_marks_ids))
    students = User.objects.filter(id__in=at_risk_ids).select_related('department', 'class_section')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="at_risk_students.csv"'
    writer = csv.writer(response)
    writer.writerow(['Username', 'Department', 'Class', 'Attendance %', 'Avg Internal Marks'])

    for s in students:
        nar = NonAcademicRecord.objects.filter(student=s).last()
        avg_m = AcademicRecord.objects.filter(student=s).aggregate(v=Avg('internal_marks'))['v']
        writer.writerow([
            s.username,
            s.department.name if s.department else '-',
            s.class_section.name if s.class_section else '-',
            float(nar.attendance_percentage) if nar else 'N/A',
            round(float(avg_m), 1) if avg_m else 'N/A'
        ])
    return response

@login_required
@user_passes_test(is_admin)
def admin_export_underperforming_teachers_csv(request):
    """Exports Underperforming Teachers as CSV using the same logic as the dashboard."""
    teacher_feedback = TeacherFeedback.objects.values('teacher').annotate(avg_score=Avg('score')).filter(avg_score__lt=3.0)
    underperforming_ids = [t['teacher'] for t in teacher_feedback]
    teachers = User.objects.filter(id__in=underperforming_ids).select_related('department')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="underperforming_teachers.csv"'
    writer = csv.writer(response)
    writer.writerow(['Username', 'Department', 'Avg Rating'])

    for t in teachers:
        avg_fb = TeacherFeedback.objects.filter(teacher=t).aggregate(v=Avg('score'))['v']
        writer.writerow([
            t.username,
            t.department.name if t.department else '-',
            round(float(avg_fb), 1) if avg_fb else 'N/A'
        ])
    return response


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
    classes  = ClassSection.objects.filter(department=dept).order_by('name')

    # Attach allocations to each teacher for display
    for t in teachers:
        t.allocations_list = Allocation.objects.filter(teacher=t)

    context = {
        'dept':           dept,
        'students':       students,
        'teachers':       teachers,
        'classes':        classes,
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
    cls      = get_object_or_404(ClassSection, id=class_id)
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

    # 1. SAFETY NET: If the teacher has no classes (like teacher_5), skip the AI
    if not allocations.exists():
        context = {
            'allocations': allocations,
            'effectiveness_score': 0.0,
            'ai_text': "No classes assigned yet. The AI requires student data to generate insights.",
            'avg_feedback': 0.0,
        }
        return render(request, 'teacher_dashboard.html', context)

    # 2. GATHER HYBRID DATA: Get the 4 pillars for the new AI
    workload = allocations.count()
    records = AcademicRecord.objects.filter(teacher=request.user)
    
    avg_marks = float(records.aggregate(v=Avg('internal_marks'))['v'] or 0.0)
    total_students = records.count()
    passed_students = records.filter(internal_marks__gte=15).count()
    pass_rate = float((passed_students / total_students * 100) if total_students > 0 else 0.0)
    avg_fb = float(TeacherFeedback.objects.filter(teacher=request.user).aggregate(v=Avg('score'))['v'] or 3.0)

    # 3. PREDICT WITH V2 BRAIN
    try:
        model = joblib.load('teacher_model.pkl')
        # Must perfectly match the columns from train_models.py
        features = pd.DataFrame([{
            'avg_feedback': avg_fb,
            'avg_marks': avg_marks,
            'pass_rate': pass_rate,
            'workload': float(workload)
        }])
        
        # The V2 model outputs a 0-100 score directly, no need to multiply by 20!
        effectiveness_score = round(model.predict(features)[0], 1) 
    except Exception as e:
        print(f"Teacher ML Error: {e}")
        effectiveness_score = 0.0

    # 4. AI EXPLANATION LOGIC
    if effectiveness_score >= 80:
        ai_text = "Highly effective. Strong balance of student satisfaction and academic results."
    elif effectiveness_score >= 50:
        ai_text = "Average effectiveness. Check if low marks or poor feedback is bringing your score down."
    else:
        ai_text = "Underperforming. High feedback alone cannot compensate for low student pass rates."

    # 5. SCORE BREAKDOWN (For Visualization)
    # Normed 0-100 components used in the hybrid model
    score_breakdown = {
        'academic': round((float(avg_marks) / 50.0 * 50) + (pass_rate / 100.0 * 50), 1),
        'feedback': round(float(avg_fb) / 5.0 * 100, 1),
        'workload_impact': -5 if workload > 2 else 0
    }

    # Recent Alerts
    alerts = SystemAlert.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:5]

    context = {
        'allocations':          allocations,
        'effectiveness_score':  effectiveness_score,
        'ai_text':              ai_text,
        'avg_feedback':         round(avg_fb, 1),
        'score_breakdown':      score_breakdown,
        'alerts':               alerts,
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

    # Time-Machine Logic: Support historical attendance
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    if request.method == 'POST':
        # Get date from hidden input to ensure consistency
        post_date_str = request.POST.get('attendance_date')
        if post_date_str:
            save_date = datetime.strptime(post_date_str, '%Y-%m-%d').date()
        else:
            save_date = selected_date

        present_ids = set(map(int, request.POST.getlist('present_ids')))
        saved_count = 0
        for student in students:
            is_present = student.id in present_ids
            AttendanceRecord.objects.update_or_create(
                student=student,
                allocation=allocation,
                date=save_date,
                defaults={'is_present': is_present}
            )
            saved_count += 1
        messages.success(request, f"Attendance recorded for {save_date} — {len(present_ids)}/{saved_count} present.")
        return redirect(reverse('teacher_attendance', args=[allocation.id]) + f"?date={save_date}")

    # Fetch existing records for the selected date
    existing = {
        r.student_id: r.is_present
        for r in AttendanceRecord.objects.filter(allocation=allocation, date=selected_date)
    }

    student_data = [
        {'user': s, 'is_present': existing.get(s.id, True)}
        for s in students
    ]

    context = {
        'allocation':    allocation,
        'student_data':  student_data,
        'selected_date': selected_date,
    }
    return render(request, 'teacher_attendance.html', context)


@login_required
@user_passes_test(is_teacher)
def teacher_attendance_report(request, allocation_id):
    allocation = get_object_or_404(Allocation, id=allocation_id, teacher=request.user)
    students = User.objects.filter(role=User.Role.STUDENT, class_section=allocation.class_section).order_by('username')
    
    report_data = []
    for student in students:
        total_classes = AttendanceRecord.objects.filter(student=student, allocation=allocation).count()
        days_present = AttendanceRecord.objects.filter(student=student, allocation=allocation, is_present=True).count()
        days_absent = total_classes - days_present
        
        percentage = 0.0
        if total_classes > 0:
            percentage = round((days_present / total_classes) * 100, 1)
            
        report_data.append({
            'student': student,
            'total_classes': total_classes,
            'days_present': days_present,
            'days_absent': days_absent,
            'percentage': percentage,
        })
        
    context = {
        'allocation': allocation,
        'report_data': report_data,
    }
    return render(request, 'attendance_report.html', context)


# ---------------------------------------------------------------------------
# Student Dashboard (UPDATED: AI prediction, warnings, suggestions)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_student)
def student_dashboard(request):
    academic_records = AcademicRecord.objects.filter(student=request.user).select_related('subject', 'teacher')
    non_academic     = NonAcademicRecord.objects.filter(student=request.user).last()

    # Run AI prediction (ML model)
    prediction = get_ai_prediction(request.user)

    # Low-attendance warning
    low_attendance_warning = (
        non_academic and float(non_academic.attendance_percentage) < 75
    )

    # Improvement suggestions from prediction insights
    suggestions = []
    if prediction and isinstance(prediction.insights, dict):
        suggestions = prediction.insights.get('improvement_suggestions', [])

    # Today's local live attendance notification
    todays_attendance = AttendanceRecord.objects.filter(
        student=request.user, 
        date=timezone.now().date()
    ).select_related('allocation__subject')

    # Recent Alerts (FIX: Added to context)
    alerts = SystemAlert.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:5]

    context = {
        'academic_records':       academic_records,
        'non_academic':           non_academic,
        'prediction':             prediction,
        'low_attendance_warning': low_attendance_warning,
        'suggestions':            suggestions,
        'todays_attendance':      todays_attendance,
        'alerts':                 alerts,
    }
    return render(request, 'student_dashboard.html', context)


@login_required
@user_passes_test(is_student)
def student_feedback_view(request):
    """
    Dedicated view for students to rate teachers whom they are allocated to.
    """
    # 1. Get allocations for the student's class section
    student_class = request.user.class_section
    if not student_class:
        messages.warning(request, "You are not assigned to a class. Please contact staff.")
        return redirect('student_dashboard')

    allocations = Allocation.objects.filter(class_section=student_class).select_related('teacher', 'subject')

    if request.method == 'POST':
        teacher_id = request.POST.get('teacher_id')
        subject_id = request.POST.get('subject_id')
        score      = request.POST.get('score')
        comments   = request.POST.get('comments', '')

        try:
            teacher = get_object_or_404(User, id=teacher_id, role=User.Role.TEACHER)
            subject = get_object_or_404(Subject, id=subject_id)

            # Update or create feedback to prevent duplicates for same teacher/subject/student
            TeacherFeedback.objects.update_or_create(
                student=request.user,
                teacher=teacher,
                subject=subject,
                defaults={
                    'score': int(score),
                    'comments': comments
                }
            )
            messages.success(request, f"Feedback submitted successfully for {teacher.username}!")
        except Exception as e:
            messages.error(request, f"Error submitting feedback: {str(e)}")
        
        return redirect('student_feedback')

    # Fetch existing feedback to pre-fill if needed (optional optimization)
    existing_feedback = {
        (f.teacher_id, f.subject_id): f
        for f in TeacherFeedback.objects.filter(student=request.user)
    }

    # Attach existing feedback data to allocations for UI display
    for alloc in allocations:
        fb = existing_feedback.get((alloc.teacher_id, alloc.subject_id))
        alloc.existing_score = fb.score if fb else None
        alloc.existing_comments = fb.comments if fb else ""

    context = {
        'allocations': allocations,
    }
    return render(request, 'student_feedback.html', context)


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

        # Handle department and class_section updates
        department_id = request.POST.get('department_id')
        class_section_id = request.POST.get('class_section_id')

        if department_id:
            try:
                user_obj.department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                pass
        
        if class_section_id:
            try:
                user_obj.class_section = ClassSection.objects.get(id=class_section_id)
            except ClassSection.DoesNotExist:
                pass
        elif user_obj.role == User.Role.STUDENT and not class_section_id:
            # Handle possible unassignment if that's a requirement, but usually students need a class
            pass

        try:
            user_obj.save()
            messages.success(request, f"User {user_obj.username} updated.")
            return redirect('staff_dashboard')
        except Exception as e:
            messages.error(request, f"Error updating: {str(e)}")

    departments = Department.objects.all()
    classes = ClassSection.objects.all()
    return render(request, 'staff_edit_user.html', {
        'edit_user': user_obj,
        'departments': departments,
        'classes': classes
    })


@login_required
@user_passes_test(is_staff)
def staff_manage_classes(request):
    dept = request.user.department
    if request.method == 'POST':
        name = request.POST.get('name')
        department_id = request.POST.get('department_id')
        
        try:
            target_dept = dept
            if department_id:
                target_dept = Department.objects.get(id=department_id)

            if ClassSection.objects.filter(name=name, department=target_dept).exists():
                messages.error(request, f"Class '{name}' already exists in {target_dept.code}.")
            else:
                ClassSection.objects.create(name=name, department=target_dept)
                messages.success(request, f"Class '{name}' created successfully in {target_dept.code}.")
                return redirect('staff_manage_classes')
        except Exception as e:
            messages.error(request, f"Error creating class: {str(e)}")

    classes = ClassSection.objects.all().select_related('department')
    departments = Department.objects.all()
    return render(request, 'staff_manage_classes.html', {'classes': classes, 'departments': departments, 'dept': dept})


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

    classes      = ClassSection.objects.all()
    class_filter = request.GET.get('class_filter')
    subjects     = Subject.objects.all().select_related('class_section')

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
            return redirect('staff_create_allocation') # Changed to redirect back to same page to see new list
        except Exception as e:
            messages.error(request, f"Error creating allocation: {str(e)}")

    teachers = User.objects.filter(role=User.Role.TEACHER, department=dept)
    classes  = ClassSection.objects.filter(department=dept)
    subjects = Subject.objects.all()
    
    # Fetch existing allocations for the dept for display on right side
    existing_allocations = Allocation.objects.filter(
        class_section__department=dept
    ).select_related('teacher', 'subject', 'class_section').order_by('teacher__username')

    context = {
        'teachers': teachers,
        'classes':  classes,
        'subjects': subjects,
        'existing_allocations': existing_allocations,
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
@login_required
@user_passes_test(is_staff)
def staff_consolidated_report(request, class_id):
    class_obj = get_object_or_404(ClassSection, id=class_id)
    
    # 1. Filtering Logic
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = timezone.now().date() - timedelta(days=30)
    else:
        start_date = timezone.now().date() - timedelta(days=30)
        
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = timezone.now().date()
    else:
        end_date = timezone.now().date()

    # 2. Data Query
    report_records = AttendanceRecord.objects.filter(
        allocation__class_section=class_obj,
        date__range=[start_date, end_date]
    ).select_related('student', 'allocation__subject').order_by('-date', 'student__username')

    # 3. CSV Export Logic
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_{class_obj.name}_{start_date}_{end_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Student Name', 'Date', 'Subject', 'Status'])
        
        for record in report_records:
            writer.writerow([
                record.student.get_full_name() or record.student.username,
                record.date,
                record.allocation.subject.name,
                'Present' if record.is_present else 'Absent'
            ])
        return response

    context = {
        'class_obj': class_obj,
        'report_records': report_records,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'staff_consolidated_report.html', context)

@login_required
@user_passes_test(is_staff)
def staff_attendance_matrix(request, class_id):
    class_obj = get_object_or_404(ClassSection, id=class_id)
    
    # 1. Inputs & Filtering
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    subject_id = request.GET.get('subject_id')
    
    # Get all records for this class initially to determine date bounds
    class_records = AttendanceRecord.objects.filter(allocation__class_section=class_obj)
    
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = None
    else:
        start_date = None
        
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = None
    else:
        end_date = None

    # Base query for the matrix
    records_query = class_records
    
    if start_date:
        records_query = records_query.filter(date__gte=start_date)
    if end_date:
        records_query = records_query.filter(date__lte=end_date)
    if subject_id and subject_id not in ['all', 'None', '']:
        records_query = records_query.filter(allocation__subject_id=subject_id)

    # Determine display dates for the UI (if not filtered, show min/max found in DB)
    actual_start = start_date
    actual_end = end_date
    
    if not actual_start:
        first_record = class_records.order_by('date').first()
        actual_start = first_record.date if first_record else timezone.now().date()
    if not actual_end:
        last_record = class_records.order_by('-date').first()
        actual_end = last_record.date if last_record else timezone.now().date()
    
    # 2. Logic: Fetch students and build Matrix
    students_query = User.objects.filter(role=User.Role.STUDENT, class_section=class_obj)
    
    # Natural sorting for usernames
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]
    
    students = sorted(list(students_query), key=lambda u: natural_sort_key(u.username))
    subjects = Subject.objects.filter(class_section=class_obj).order_by('name')

    # Get distinct sessions (Date + Subject)
    sessions_records = records_query.select_related('allocation__subject').order_by('date', 'allocation__subject__code')
    
    # Unique sessions list
    sessions = []
    seen_sessions = set()
    for r in sessions_records:
        session_key = (r.date, r.allocation.subject_id)
        if session_key not in seen_sessions:
            sessions.append({
                'date': r.date,
                'subject_name': r.allocation.subject.name,
                'subject_code': r.allocation.subject.code,
                'subject_id': r.allocation.subject_id
            })
            seen_sessions.add(session_key)

    # Build the Matrix
    matrix = []
    for student in students:
        status_list = []
        for session in sessions:
            record = records_query.filter(
                student=student, 
                date=session['date'], 
                allocation__subject_id=session['subject_id']
            ).first()
            
            if record:
                status_list.append(record.is_present)
            else:
                status_list.append(None)
        
        matrix.append({
            'student': student,
            'status_list': status_list
        })

    # 3. Export Logic
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_matrix_{class_obj.name}_{start_date}.csv"'
        
        writer = csv.writer(response)
        header = ['Student Name'] + [f"{s['date']} ({s['subject_code']})" for s in sessions]
        writer.writerow(header)
        
        for row in matrix:
            writer_row = [row['student'].get_full_name() or row['student'].username]
            for status in row['status_list']:
                if status is True:
                    writer_row.append('P')
                elif status is False:
                    writer_row.append('A')
                else:
                    writer_row.append('-')
            writer.writerow(writer_row)
        return response

    context = {
        'class_obj': class_obj,
        'sessions': sessions,
        'matrix': matrix,
        'subjects': subjects,
        'start_date': actual_start,
        'end_date': actual_end,
        'selected_subject_id': subject_id,
    }
    return render(request, 'staff_attendance_matrix.html', context)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from .models import User, Department, ClassSection, Subject, Allocation, AcademicRecord, NonAcademicRecord
from django.db.models import Count, Avg
from django.contrib import messages

# --- Helper Functions ---
def is_admin(user):
    return user.role == User.Role.ADMIN

def is_staff(user):
    return user.role == User.Role.STAFF

def is_teacher(user):
    return user.role == User.Role.TEACHER

def is_student(user):
    return user.role == User.Role.STUDENT

# --- Auth Views ---

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

# --- Dashboards ---

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    context = {
        'total_students': User.objects.filter(role=User.Role.STUDENT).count(),
        'total_teachers': User.objects.filter(role=User.Role.TEACHER).count(),
        'total_depts': Department.objects.count(),
        'users': User.objects.all(), # Simple list for now
        'departments': Department.objects.all(),
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
@user_passes_test(is_staff)
def staff_dashboard(request):
    dept = request.user.department
    if not dept:
        messages.error(request, "You are not assigned to a department.")
        return redirect('login')
        
    teachers = User.objects.filter(role=User.Role.TEACHER, department=dept)
    
    # Attach allocations to each teacher for display
    for t in teachers:
        t.allocations_list = Allocation.objects.filter(teacher=t)

    context = {
        'dept': dept,
        'students': User.objects.filter(role=User.Role.STUDENT, department=dept),
        'teachers': teachers,
    }
    return render(request, 'staff_dashboard.html', context)

@login_required
@user_passes_test(is_teacher)
def teacher_dashboard(request):
    allocations = Allocation.objects.filter(teacher=request.user)
    context = {
        'allocations': allocations,
    }
    return render(request, 'teacher_dashboard.html', context)

@login_required
@user_passes_test(is_student)
def student_dashboard(request):
    academic_records = AcademicRecord.objects.filter(student=request.user)
    non_academic = NonAcademicRecord.objects.filter(student=request.user).last() # Get latest
    
    context = {
        'academic_records': academic_records,
        'non_academic': non_academic,
    }
    return render(request, 'student_dashboard.html', context)

# --- Actions ---

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
        internal = request.POST.get('internal')
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

    return render(request, 'manage_marks.html', {'allocation': allocation, 'students': students})

@login_required
@user_passes_test(is_admin)
def create_allocation(request):
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher_id')
        subject_id = request.POST.get('subject_id')
        class_section_id = request.POST.get('class_section_id')
        
        try:
            teacher = User.objects.get(id=teacher_id, role=User.Role.TEACHER)
            subject = Subject.objects.get(id=subject_id)
            class_section = ClassSection.objects.get(id=class_section_id)
            
            Allocation.objects.create(teacher=teacher, subject=subject, class_section=class_section)
            messages.success(request, f"Allocation created successfully!")
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Error creating allocation: {str(e)}")
            
    context = {
        'teachers': User.objects.filter(role=User.Role.TEACHER),
        'subjects': Subject.objects.all(),
        'class_sections': ClassSection.objects.all(),
    }
    return render(request, 'create_allocation.html', context)

@login_required
@user_passes_test(is_admin)
def add_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        if not password:
            password = username
        role = request.POST.get('role')
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
        'roles': User.Role.choices,
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
        user_obj.email = request.POST.get('email')
        
        # Only update password if provided
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
        'edit_user': user_obj,
        'roles': User.Role.choices,
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
    return render(request, 'edit_department.html', {'dept': dept})

@login_required
@user_passes_test(is_staff)
def staff_add_user(request):
    dept = request.user.department
    target_role = request.GET.get('role', 'student').lower()
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        if not password:
            password = username
        role_input = request.POST.get('role')
        class_section_id = request.POST.get('class_section_id') or request.POST.get('class_id')
        
        try:
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists.")
            else:
                role_val = User.Role.TEACHER if role_input and role_input.upper() == 'TEACHER' else User.Role.STUDENT
                user = User.objects.create_user(username=username, email=email, password=password, role=role_val)
                user.department = dept
                
                # Assign class only if role is student or logic permits
                if role_val == User.Role.STUDENT and class_section_id:
                     user.class_section = ClassSection.objects.get(id=class_section_id, department=dept)
                
                user.save()
                messages.success(request, f"{role_input.title()} {username} added to {dept.name}.")
                return redirect('staff_dashboard')
        except Exception as e:
            messages.error(request, f"Error creating user: {str(e)}")
            
    classes = ClassSection.objects.filter(department=dept)
    return render(request, 'staff_add_user.html', {'classes': classes, 'target_role': target_role})

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
    
    # Ensure Staff can only edit Students or Teachers, not Admins or other Staff (optional, but good practice)
    if user_obj.role == User.Role.ADMIN:
         messages.error(request, "Cannot edit Admin users.")
         return redirect('staff_dashboard')

    if request.method == 'POST':
        user_obj.username = request.POST.get('username')
        user_obj.email = request.POST.get('email')
        
        password = request.POST.get('password')
        if password:
            user_obj.set_password(password)
            
        # Staff shouldn't change role or department generally?
        # Maybe just details.
        
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
        # name e.g., "S1-MCA"
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
        name = request.POST.get('name')
        code = request.POST.get('code')
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
            
    # Filter subjects by department (via ClassSection)? 
    # Or show all? The model change links Subject -> ClassSection -> Department.
    # So we can filter subjects belonging to this department's classes.
    # For global subjects (no class linkage), maybe exclude or include?
    # Let's show subjects linked to this dept's classes.
    
    classes = ClassSection.objects.filter(department=dept)
    
    # Filter Logic
    class_filter = request.GET.get('class_filter')
    subjects = Subject.objects.filter(class_section__department=dept) | Subject.objects.filter(class_section__isnull=True)
    
    if class_filter:
        subjects = subjects.filter(class_section_id=class_filter)
        
    subjects = subjects.distinct()
    
    return render(request, 'staff_manage_subjects.html', {'subjects': subjects, 'classes': classes, 'current_filter': class_filter})

@login_required
@user_passes_test(is_staff)
def staff_create_allocation(request):
    dept = request.user.department
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher_id')
        subject_id = request.POST.get('subject_id')
        class_section_id = request.POST.get('class_section_id')
        
        try:
            teacher = User.objects.get(id=teacher_id, role=User.Role.TEACHER)
            subject = Subject.objects.get(id=subject_id)
            class_section = ClassSection.objects.get(id=class_section_id)
            
            # Ensure staff only allocates for their dept
            if class_section.department != dept:
                 messages.error(request, "You can only allocate for your department's classes.")
                 return redirect('staff_create_allocation')
            
            Allocation.objects.create(teacher=teacher, subject=subject, class_section=class_section)
            messages.success(request, f"Allocation created successfully!")
            return redirect('staff_dashboard')
        except Exception as e:
            messages.error(request, f"Error creating allocation: {str(e)}")
            
    teachers = User.objects.filter(role=User.Role.TEACHER, department=dept)
    classes = ClassSection.objects.filter(department=dept)
    subjects = Subject.objects.all()
    
    context = {
        'teachers': teachers,
        'classes': classes,
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
    dept = request.user.department
    class_obj = get_object_or_404(ClassSection, id=class_id, department=dept)
    
    if request.method == 'POST':
        name = class_obj.name
        class_obj.delete()
        messages.success(request, f"Class '{name}' deleted successfully.")
        return redirect('staff_manage_classes')
        
    return render(request, 'confirm_delete.html', {'item': f"Class: {class_obj.name}", 'back_url': 'staff_manage_classes'})

@login_required
@user_passes_test(is_staff)
def staff_delete_subject(request, subject_id):
    # Staff can delete any subject visible to them? 
    # Or strict check? For MVP let's allow deleting any Subject by ID if logged in as staff.
    # Ideally check ownership/dept linkage.
    subject = get_object_or_404(Subject, id=subject_id)
    
    if request.method == 'POST':
        name = subject.name
        subject.delete()
        messages.success(request, f"Subject '{name}' deleted successfully.")
        return redirect('staff_manage_subjects')
        
    return render(request, 'confirm_delete.html', {'item': f"Subject: {subject.name} ({subject.code})", 'back_url': 'staff_manage_subjects'})

@login_required
@user_passes_test(is_staff)
def staff_manage_non_academic(request, student_id):
    student = get_object_or_404(User, id=student_id, department=request.user.department)
    # Fix IntegrityError: Provide defaults for required fields
    record, created = NonAcademicRecord.objects.get_or_create(
        student=student,
        defaults={
            'attendance_percentage': 0.00,
            'lab_performance': 0.00,
            'disciplinary_score': 100
        }
    )
    
    if request.method == 'POST':
        attendance = request.POST.get('attendance')
        lab = request.POST.get('lab')
        discipline = request.POST.get('discipline')
        
        try:
            record.attendance_percentage = attendance
            record.lab_performance = lab
            record.disciplinary_score = discipline
            record.save()
            messages.success(request, f"Records updated for {student.username}")
            return redirect('staff_dashboard')
        except Exception as e:
            messages.error(request, f"Error updating records: {str(e)}")
            
    return render(request, 'staff_manage_non_academic.html', {'student': student, 'record': record})

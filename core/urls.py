from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('staff-dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('teacher-dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('student-dashboard/', views.student_dashboard, name='student_dashboard'),
    
    path('manage-marks/<int:allocation_id>/', views.manage_marks, name='manage_marks'),
    path('create-allocation/', views.create_allocation, name='create_allocation'),
    path('add-user/', views.add_user, name='add_user'),
    path('create-department/', views.create_department, name='create_department'),
    path('edit-user/<int:user_id>/', views.edit_user, name='edit_user'),
    path('edit-department/<int:dept_id>/', views.edit_department, name='edit_department'),
    path('staff/add-user/', views.staff_add_user, name='staff_add_user'),
    path('staff/edit-user/<int:user_id>/', views.staff_edit_user, name='staff_edit_user'),
    path('staff/manage-classes/', views.staff_manage_classes, name='staff_manage_classes'),
    path('staff/manage-subjects/', views.staff_manage_subjects, name='staff_manage_subjects'),
    path('staff/create-allocation/', views.staff_create_allocation, name='staff_create_allocation'),
    path('staff/non-academic/<int:student_id>/', views.staff_manage_non_academic, name='staff_manage_non_academic'),
    path('staff/delete-user/<int:user_id>/', views.staff_delete_user, name='staff_delete_user'),
    path('staff/delete-class/<int:class_id>/', views.staff_delete_class, name='staff_delete_class'),
    path('staff/delete-subject/<int:subject_id>/', views.staff_delete_subject, name='staff_delete_subject'),
    path('api/get-subjects/', views.get_subjects_by_class, name='get_subjects_by_class'),
]

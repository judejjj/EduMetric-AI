from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('staff-dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('teacher-dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('student-dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/feedback/', views.student_feedback_view, name='student_feedback'),
    
    path('manage-marks/<int:allocation_id>/', views.manage_marks, name='manage_marks'),
    path('staff/class/<int:class_id>/consolidated-report/', views.staff_consolidated_report, name='staff_consolidated_report'),
    path('staff/class/<int:class_id>/matrix/', views.staff_attendance_matrix, name='staff_attendance_matrix'),
    path('create-allocation/', views.create_allocation, name='create_allocation'),
    path('teacher/allocation/<int:allocation_id>/attendance/report/', views.teacher_attendance_report, name='teacher_attendance_report'),
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
    
    # New Analytics & AI Routes
    path('admin-dashboard/send-alert/<int:user_id>/', views.admin_send_alert, name='admin_send_alert'),
    path('admin-dashboard/bulk-upload/', views.admin_bulk_upload, name='admin_bulk_upload'),
    path('admin-dashboard/export-csv/', views.admin_export_csv, name='admin_export_csv'),
    path('admin-dashboard/export-at-risk-csv/', views.admin_export_at_risk_csv, name='admin_export_at_risk_csv'),
    path('admin-dashboard/export-underperforming-csv/', views.admin_export_underperforming_teachers_csv, name='admin_export_underperforming_teachers_csv'),
    path('staff/class-report/<int:class_id>/', views.staff_class_report, name='staff_class_report'),
    path('teacher/attendance/<int:allocation_id>/', views.teacher_attendance, name='teacher_attendance'),
]

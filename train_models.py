import os
import django
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from django.db.models import Avg

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edumetric_project.settings')
django.setup()

from core.models import AcademicRecord, NonAcademicRecord, TeacherFeedback, User, Allocation

def train_student_model():
    print("🧠 1. Training Student Performance Model...")
    academics = AcademicRecord.objects.all().values('student_id', 'internal_marks', 'assignment_score')
    non_academics = NonAcademicRecord.objects.all().values('student_id', 'attendance_percentage', 'disciplinary_score')
    
    df_a = pd.DataFrame(list(academics))
    df_na = pd.DataFrame(list(non_academics))
    
    if df_a.empty or df_na.empty:
        print("⚠️ Not enough student data to train.")
        return

    df = pd.merge(df_a, df_na, on='student_id')
    df = df.astype({'internal_marks': float, 'assignment_score': float, 'attendance_percentage': float, 'disciplinary_score': float})

    def categorize(row):
        score = (row['internal_marks'] * 2) + (row['attendance_percentage'] * 0.5)
        if score > 130: return 'Excellent'
        if score < 80: return 'At-Risk'
        return 'Average'

    df['label'] = df.apply(categorize, axis=1)
    
    X = df[['internal_marks', 'assignment_score', 'attendance_percentage', 'disciplinary_score']]
    y = df['label']

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    joblib.dump(model, 'student_model.pkl')
    print("✅ Student Model retrained and saved!")

def train_hybrid_teacher_model():
    print("🧠 2. Training HYBRID Teacher Effectiveness Model...")
    teachers = User.objects.filter(role=User.Role.TEACHER)
    data = []
    
    for t in teachers:
        workload = Allocation.objects.filter(teacher=t).count()
        avg_fb = TeacherFeedback.objects.filter(teacher=t).aggregate(v=Avg('score'))['v'] or 3.0
        
        records = AcademicRecord.objects.filter(teacher=t)
        avg_marks = records.aggregate(v=Avg('internal_marks'))['v'] or 0.0
        total_students = records.count()
        passed_students = records.filter(internal_marks__gte=15).count() 
        pass_rate = (passed_students / total_students * 100) if total_students > 0 else 0.0

        # AI Target Logic
        score = (float(avg_marks) / 50.0 * 40) + (pass_rate / 100.0 * 40) + (float(avg_fb) / 5.0 * 20)
        if workload > 2:
            score -= 5 # Burnout penalty
            
        data.append({
            'avg_feedback': float(avg_fb),
            'avg_marks': float(avg_marks),
            'pass_rate': float(pass_rate),
            'workload': float(workload),
            'label': float(min(max(score, 0), 100))
        })

    df = pd.DataFrame(data)
    
    if df.empty:
        print("⚠️ Not enough teacher data to train.")
        return

    X = df[['avg_feedback', 'avg_marks', 'pass_rate', 'workload']]
    y = df['label']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    joblib.dump(model, 'teacher_model.pkl')
    print("✅ HYBRID Teacher Model trained and saved!")

if __name__ == "__main__":
    train_student_model()
    train_hybrid_teacher_model()
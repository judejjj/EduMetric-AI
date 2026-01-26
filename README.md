# EduMatrix - Educational Management System

EduMatrix is a comprehensive web-based management system designed for educational institutions. It facilitates seamless interaction between Administrators, Staff, Teachers, and Students, handling everything from user management to academic record tracking.

## 🚀 Features

### 1. **Admin Dashboard**
*   **Department Management**: Create and manage multiple departments (e.g., MCA, CS, EC).
*   **Staff Management**: Appoint Staff members for specific departments.
*   **User Control**: Full control over all users in the system.

### 2. **Staff Dashboard** (Department Level)
*   **Class Management**: Create and manage classes (e.g., S1-MCA, S3-CS).
*   **Subject Management**: Add subjects and link them to specific classes.
*   **student & Teacher Management**: Add and manage faculty and students within the department.
*   **allocations**: Assign teachers to specific subjects and classes.
*   **Non-Academic Records**: specific Manage attendance and discipline scores for students.

### 3. **Teacher Dashboard**
*   **View Allocations**: See assigned subjects and classes.
*   **Manage Marks**: Enter and update internal marks and assignment scores for students in allocated classes.

### 4. **Student Dashboard**
*   **Academic View**: Check internal marks and assignment scores.
*   **Performance Tracking**: View attendance percentage and discipline updates.

## 🛠️ Installation & Setup

Follow these steps to get the project running on your local machine.

### Prerequisites
*   Python 3.10+ installed.

### Step 1: Clone the Repository
```bash
git clone <repository-url>
cd EduMetric
```

### Step 2: Create a Virtual Environment (Recommended)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Database Setup
Run the migrations to set up the SQLite database.
```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 5: Create Admin User
Create a superuser to log in to the admin dashboard.
```bash
python manage.py createsuperuser
```
Follow the prompts to set a username, email, and password.

### Step 6: Run the Server
```bash
python manage.py runserver
```
Open your browser and navigate to: `http://127.0.0.1:8000/`

## 🔑 Usage Guide

1.  **Login**: Use the `Login` page.
    *   **Admin**: Log in with the superuser credentials created in Step 5.
    *   **Staff/Teachers/Students**: Log in with credentials created by Admin or Staff.
2.  **Workflow**:
    *   **Admin** creates Departments and Staff.
    *   **Staff** creates Classes, Subjects, Teachers, and Students.
    *   **Staff** allocates Teachers to Subjects/Classes.
    *   **Teachers** login to add marks for their students.
    *   **Students** login to view their progress.

## 📝 Tech Stack
*   **Backend**: Django (Python)
*   **Database**: SQLite (Default)
*   **Frontend**: HTML, Tailwind CSS (via CDN/Vanilla CSS)
*   **Authentication**: Django Auth System with Role-Based Access Control (RBAC)

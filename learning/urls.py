from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("learn/", views.home, name="home"),
    path("learn/quizzes/", views.quiz_list, name="quizzes"),
    path("learn/quizzes/<int:pk>/", views.quiz_take, name="quiz_take"),
    path("learn/attempts/<int:pk>/", views.attempt_detail, name="attempt_detail"),
    path("learn/assignments/", views.assignment_list, name="assignments"),
    path("learn/assignments/<int:pk>/", views.assignment_detail, name="assignment_detail"),
    path("learn/submissions/<int:pk>/file/", views.submission_file, name="submission_file"),
    path("learn/grading/", views.grading_list, name="grading"),
    path("learn/grading/<int:pk>/", views.grade_assignment, name="grade_assignment"),
    path("learn/grading/submission/<int:pk>/", views.grade_submission, name="grade_submission"),
]

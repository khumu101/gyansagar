from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("schools/", views.schools, name="schools"),
    path("study-tools/", views.tools, name="tools"),
    path("blogs/", views.blog_list, name="blog_list"),
    path("blogs/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("scholarships/", views.scholarships, name="scholarships"),
    path("careers/", views.careers, name="careers"),
    path("community/", views.community, name="community"),
    path("community/new/", views.post_new, name="post_new"),
    path("community/<int:pk>/", views.post_detail, name="post_detail"),
    path("community/<int:pk>/delete/", views.post_delete, name="post_delete"),
    path("community/comment/<int:pk>/delete/", views.comment_delete, name="comment_delete"),
    path("ai-tutor/", views.tutor, name="tutor"),
    path("ai-tutor/clear/", views.tutor_clear, name="tutor_clear"),
    path("more/", views.more, name="more"),
]

from django.contrib import admin

from .models import BlogPost, Comment, ContactMessage, Opportunity, Post, School, TutorMessage


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "kind", "levels_offered", "is_published")
    list_filter = ("kind", "is_published", "city")
    search_fields = ("name", "city", "address")


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "is_published", "published_at")
    list_filter = ("is_published",)
    search_fields = ("title", "body")
    prepopulated_fields = {"slug": ("title",)}

    def save_model(self, request, obj, form, change):
        if not change and not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "organization", "deadline", "is_published")
    list_filter = ("kind", "is_published", "level")
    search_fields = ("title", "organization", "description")
    date_hierarchy = "deadline"


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("author", "body", "is_hidden")
    readonly_fields = ("author",)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "level", "subject", "is_hidden", "created_at")
    list_filter = ("is_hidden", "level")
    search_fields = ("title", "body", "author__username")
    actions = ["hide", "unhide"]
    inlines = [CommentInline]

    @admin.action(description="Hide selected posts")
    def hide(self, request, queryset):
        queryset.update(is_hidden=True)

    @admin.action(description="Unhide selected posts")
    def unhide(self, request, queryset):
        queryset.update(is_hidden=False)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("post", "author", "is_hidden", "created_at")
    list_filter = ("is_hidden",)
    search_fields = ("body", "author__username")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "is_resolved", "created_at")
    list_filter = ("is_resolved",)
    search_fields = ("subject", "message", "name", "email")
    readonly_fields = ("user", "name", "email", "subject", "message", "created_at")


@admin.register(TutorMessage)
class TutorMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "subject", "created_at")
    search_fields = ("question", "user__username")
    readonly_fields = ("user", "subject", "question", "answer", "created_at")

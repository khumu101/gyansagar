from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    """Let people log in with either their username or their e-mail address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None
        user = None
        try:
            user = User._default_manager.get_by_natural_key(username)
        except User.DoesNotExist:
            if "@" in username:
                matches = list(User._default_manager.filter(email__iexact=username)[:2])
                if len(matches) == 1:  # ambiguous e-mail -> refuse rather than guess
                    user = matches[0]
        if user is None:
            User().set_password(password)  # constant-ish timing, don't leak which accounts exist
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

from django import forms
from django.contrib.auth.forms import AuthenticationForm


class SuperuserAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise forms.ValidationError(
                "Bu panele sadece superuser ile girilebilir.",
                code="no_superuser",
            )

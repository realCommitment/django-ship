from django import forms

from .models import Role, Team


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name"]


class InvitationForm(forms.Form):
    email = forms.EmailField()
    role = forms.TypedChoiceField(choices=Role.choices, coerce=int, initial=Role.MEMBER)


class RoleForm(forms.Form):
    role = forms.TypedChoiceField(choices=Role.choices, coerce=int)

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile

FC = {'class': 'form-control'}
FS = {'class': 'form-select'}


class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={**FC, 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={**FC, 'placeholder': 'Password'}))


class UserCreateForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs=FC))
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs=FC))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs=FC))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']
        widgets = {'username': forms.TextInput(attrs=FC)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget = forms.PasswordInput(attrs={**FC, 'placeholder': 'Min 8 characters'})
        self.fields['password2'].widget = forms.PasswordInput(attrs={**FC, 'placeholder': 'Repeat password'})
        self.fields['password1'].help_text = None
        self.fields['password2'].help_text = None


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs=FC),
            'last_name': forms.TextInput(attrs=FC),
            'email': forms.EmailInput(attrs=FC),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'organization', 'avatar']
        widgets = {
            'phone': forms.TextInput(attrs=FC),
            'organization': forms.TextInput(attrs=FC),
        }

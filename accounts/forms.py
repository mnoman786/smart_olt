from django import forms
from django.contrib.auth.models import User
from .models import UserProfile

FC = {'class': 'form-control'}
FS = {'class': 'form-select'}


class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={**FC, 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={**FC, 'placeholder': 'Password'}))


class UserCreateForm(forms.ModelForm):
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs=FC))
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs=FC))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs=FC))
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={**FC, 'placeholder': 'Min 8 characters'}))
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput(attrs={**FC, 'placeholder': 'Repeat password'}))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {'username': forms.TextInput(attrs=FC)}

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1', '')
        p2 = self.cleaned_data.get('password2', '')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        if len(p1) < 8:
            raise forms.ValidationError('Password must be at least 8 characters.')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


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
        fields = ['phone', 'organization', 'avatar', 'olt_quota']
        widgets = {
            'phone': forms.TextInput(attrs=FC),
            'organization': forms.TextInput(attrs=FC),
            'olt_quota': forms.NumberInput(attrs={**FC, 'min': '0'}),
        }

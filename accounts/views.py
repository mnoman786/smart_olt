from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from .models import UserProfile
from .forms import LoginForm, UserCreateForm, UserEditForm, UserProfileForm
from core.utils import superuser_required


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username     = request.POST.get('username', '').strip()
        email        = request.POST.get('email', '').strip()
        password1    = request.POST.get('password1', '')
        password2    = request.POST.get('password2', '')
        organization = request.POST.get('organization', '').strip()

        error = None
        if not username or not password1:
            error = 'Username and password are required.'
        elif password1 != password2:
            error = 'Passwords do not match.'
        elif len(password1) < 8:
            error = 'Password must be at least 8 characters.'
        elif User.objects.filter(username=username).exists():
            error = 'Username already taken.'

        if error:
            messages.error(request, error)
        else:
            user = User.objects.create_user(username=username, email=email, password=password1)
            user.profile.organization = organization
            user.profile.save()
            login(request, user)
            messages.success(request, f'Welcome, {username}! Your account is ready.')
            return redirect('olt_list')

    return render(request, 'accounts/register.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm()
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password']
            )
            if user:
                login(request, user)
                return redirect(request.GET.get('next', 'dashboard'))
            messages.error(request, 'Invalid username or password.')
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def profile_view(request):
    profile = request.user.profile
    if request.method == 'POST':
        user_form = UserEditForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        user_form = UserEditForm(instance=request.user)
        profile_form = UserProfileForm(instance=profile)
    return render(request, 'accounts/profile.html', {
        'user_form': user_form,
        'profile_form': profile_form,
    })


@login_required
@superuser_required
def users_list(request):
    search = request.GET.get('q', '')
    users = User.objects.select_related('profile').order_by('username')
    if search:
        users = users.filter(Q(username__icontains=search) | Q(email__icontains=search) |
                             Q(first_name__icontains=search) | Q(last_name__icontains=search))
    return render(request, 'accounts/users.html', {'users': users, 'search': search})


@login_required
@superuser_required
def user_create(request):
    if request.method == 'POST':
        user_form = UserCreateForm(request.POST)
        profile_form = UserProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            profile = user.profile
            profile.phone = profile_form.cleaned_data.get('phone', '')
            profile.organization = profile_form.cleaned_data.get('organization', '')
            profile.save()
            messages.success(request, f'User {user.username} created successfully.')
            return redirect('users_list')
    else:
        user_form = UserCreateForm()
        profile_form = UserProfileForm()
    return render(request, 'accounts/user_form.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'action': 'Create',
    })


@login_required
@superuser_required
def user_edit(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        user_form = UserEditForm(request.POST, instance=target_user)
        profile_form = UserProfileForm(request.POST, instance=target_user.profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, f'User {target_user.username} updated.')
            return redirect('users_list')
    else:
        user_form = UserEditForm(instance=target_user)
        profile_form = UserProfileForm(instance=target_user.profile)
    return render(request, 'accounts/user_form.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'target_user': target_user,
        'action': 'Edit',
    })


@login_required
@superuser_required
def user_toggle_superuser(request, pk):
    if request.method != 'POST':
        return redirect('users_list')
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, 'You cannot change your own superuser status.')
        return redirect('users_list')
    target.is_superuser = not target.is_superuser
    target.is_staff = target.is_superuser
    target.save(update_fields=['is_superuser', 'is_staff'])
    action = 'promoted to Super Admin' if target.is_superuser else 'changed to User'
    messages.success(request, f'{target.username} {action}.')
    return redirect('users_list')


@login_required
@superuser_required
def user_delete(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if target_user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('users_list')
    if request.method == 'POST':
        username = target_user.username
        target_user.delete()
        messages.success(request, f'User {username} deleted.')
        return redirect('users_list')
    return render(request, 'accounts/user_confirm_delete.html', {'target_user': target_user})

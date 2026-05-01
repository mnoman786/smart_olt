from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from .models import UserProfile
from .forms import LoginForm, UserCreateForm, UserEditForm, UserProfileForm


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
def users_list(request):
    if not request.user.profile.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    search = request.GET.get('q', '')
    users = User.objects.select_related('profile').order_by('username')
    if search:
        users = users.filter(Q(username__icontains=search) | Q(email__icontains=search) |
                             Q(first_name__icontains=search) | Q(last_name__icontains=search))
    return render(request, 'accounts/users.html', {'users': users, 'search': search})


@login_required
def user_create(request):
    if not request.user.profile.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    if request.method == 'POST':
        user_form = UserCreateForm(request.POST)
        profile_form = UserProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            profile = user.profile
            profile.role = profile_form.cleaned_data['role']
            profile.phone = profile_form.cleaned_data['phone']
            profile.organization = profile_form.cleaned_data['organization']
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
def user_edit(request, pk):
    if not request.user.profile.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
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
def user_delete(request, pk):
    if not request.user.profile.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
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

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)
    organization = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    olt_quota = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def olt_used(self):
        return self.user.olts.filter(is_deleted=False).count()

    @property
    def quota_remaining(self):
        if self.user.is_superuser:
            return None  # unlimited
        return max(0, self.olt_quota - self.olt_used)

    @property
    def can_add_olt(self):
        if self.user.is_superuser:
            return True
        return self.olt_used < self.olt_quota

    def __str__(self):
        return self.user.username

    @property
    def is_admin(self):
        return self.user.is_superuser

    @property
    def is_operator(self):
        return True  # all logged-in users can manage their own OLTs

    @property
    def role_badge_class(self):
        return 'bg-danger' if self.user.is_superuser else 'bg-primary'

    def get_role_display(self):
        return 'Super Admin' if self.user.is_superuser else 'User'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError('Phone number is required')
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CLIENT     = 'client'
    ROLE_ASTROLOGER = 'astrologer'
    ROLE_ADMIN      = 'admin'
    ROLE_CHOICES = [
        (ROLE_CLIENT,     'Client'),
        (ROLE_ASTROLOGER, 'Astrologer'),
        (ROLE_ADMIN,      'Admin'),
    ]

    GENDER_CHOICES = [
        ('male',   'Male'),
        ('female', 'Female'),
        ('other',  'Other'),
    ]

    phone         = models.CharField(max_length=15, unique=True)
    full_name     = models.CharField(max_length=150, blank=True, default='')
    role          = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CLIENT)
    gender        = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=255, null=True, blank=True)   # e.g. "Panna, Madhya Pradesh, India"
    time_of_birth  = models.TimeField(null=True, blank=True)                   # null = user doesn't know
    birth_time_unknown = models.BooleanField(default=False)                    # "Don't know my exact time"
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    firebase_uid  = models.CharField(max_length=128, null=True, blank=True, unique=True)
    has_used_free_session = models.BooleanField(default=False)

    is_active  = models.BooleanField(default=True)
    is_staff   = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD  = 'phone'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.phone} ({self.role})"


class OTPRecord(models.Model):
    """
    Stores OTP codes for phone verification.
    Currently uses STATIC OTP — swap `otp_service.py` to enable dynamic/Firebase OTP.
    """
    phone      = models.CharField(max_length=15, db_index=True)
    otp_code   = models.CharField(max_length=10)
    is_used    = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'otp_records'
        ordering = ['-created_at']

    def is_valid(self):
        """Check if OTP is still valid (not used, not expired)."""
        return (not self.is_used) and (timezone.now() < self.expires_at)

    def __str__(self):
        return f"{self.phone} — {'used' if self.is_used else 'active'}"

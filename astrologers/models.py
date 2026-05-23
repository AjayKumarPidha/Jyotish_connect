import uuid
from django.db import models
from django.conf import settings


class Category(models.Model):
    """Session type category: Chat, Call, Video"""
    name        = models.CharField(max_length=50, unique=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table        = 'categories'
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class Specialty(models.Model):
    """Astrology specialties: Love, Marriage, Career, Business, Health etc."""
    name        = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table        = 'specialties'
        verbose_name_plural = 'Specialties'

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'languages'

    def __str__(self):
        return self.name


class AstrologerProfile(models.Model):
    STATUS_ONLINE  = 'online'
    STATUS_OFFLINE = 'offline'
    STATUS_BUSY    = 'busy'
    STATUS_CHOICES = [
        (STATUS_ONLINE,  'Online'),
        (STATUS_OFFLINE, 'Offline'),
        (STATUS_BUSY,    'Busy'),
    ]

    id                 = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user               = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='astrologer_profile',
    )
    display_name       = models.CharField(max_length=100)
    bio                = models.TextField(blank=True)
    experience_years   = models.PositiveIntegerField(default=0)
    categories         = models.ManyToManyField(Category, blank=True)
    specialties        = models.TextField(blank=True, help_text="Comma-separated list of specialties")
    languages          = models.TextField(blank=True, help_text="Comma-separated list of languages")
    

    # Per-minute rates
    chat_rate_per_min  = models.DecimalField(max_digits=8, decimal_places=2, default=10)
    call_rate_per_min  = models.DecimalField(max_digits=8, decimal_places=2, default=15)
    video_rate_per_min = models.DecimalField(max_digits=8, decimal_places=2, default=20)

    # Stats
    status             = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OFFLINE)
    average_rating     = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_sessions     = models.PositiveIntegerField(default=0)
    total_earnings     = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Admin approval
    is_approved        = models.BooleanField(default=False)
    profile_photo      = models.ImageField(upload_to='astrologer_photos/', null=True, blank=True)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'astrologer_profiles'
        ordering = ['-average_rating', '-total_sessions']

    def __str__(self):
        return f"{self.display_name} ({self.user.phone})"

    def update_rating(self):
        """Recalculate average rating from all reviews."""
        reviews = self.reviews.all()
        if reviews.exists():
            avg = reviews.aggregate(models.Avg('rating'))['rating__avg']
            self.average_rating = round(avg, 2)
            self.save(update_fields=['average_rating'])


class Review(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    astrologer  = models.ForeignKey(
        AstrologerProfile, on_delete=models.CASCADE, related_name='reviews'
    )
    client      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews'
    )
    rating      = models.PositiveSmallIntegerField()   # 1-5
    comment     = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reviews'
        unique_together = ['astrologer', 'client']   # One review per client per astrologer

    def __str__(self):
        return f"{self.client.phone} → {self.astrologer.display_name} ({self.rating}★)"

from django.contrib import admin
from django import forms
from .models import User, OTPRecord


class UserCreationForm(forms.ModelForm):
    password              = forms.CharField(widget=forms.PasswordInput(), label='Password')
    password_confirmation = forms.CharField(widget=forms.PasswordInput(), label='Confirm password')

    class Meta:
        model  = User
        fields = ('phone', 'role', 'gender', 'date_of_birth', 'place_of_birth')

    def clean(self):
        data = super().clean()
        if data.get('password') != data.get('password_confirmation'):
            raise forms.ValidationError("Passwords don't match.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    add_form      = UserCreationForm
    list_display  = ('phone', 'full_name', 'role', 'is_active', 'created_at')
    list_filter   = ('role', 'gender', 'is_staff', 'is_active')
    search_fields = ('phone', 'full_name')
    ordering      = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return (
                (None, {'fields': ('phone', 'password', 'password_confirmation', 'role')}),
            )
        return (
            ('Personal Info', {
                'fields': (
                    'phone', 'full_name', 'gender', 'date_of_birth',
                    'place_of_birth', 'time_of_birth', 'birth_time_unknown',
                    'profile_photo', 'firebase_uid',
                )
            }),
            ('Status', {'fields': ('role', 'has_used_free_session', 'is_active', 'is_staff', 'is_superuser')}),
            ('Permissions', {'fields': ('groups', 'user_permissions')}),
            ('Timestamps', {'fields': ('created_at', 'updated_at')}),
        )

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = self.add_form
        return super().get_form(request, obj, **kwargs)


@admin.register(OTPRecord)
class OTPRecordAdmin(admin.ModelAdmin):
    list_display  = ('phone', 'otp_code', 'is_used', 'expires_at', 'created_at')
    list_filter   = ('is_used',)
    search_fields = ('phone',)
    ordering      = ('-created_at',)
    readonly_fields = ('created_at',)

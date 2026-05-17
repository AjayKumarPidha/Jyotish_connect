from django.contrib import admin
from django import forms
from .models import User

# 1. Naya User Create karne ka Form (Isme se username gayab hai)
class CustomUserCreationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(), label="Password")
    password_confirmation = forms.CharField(widget=forms.PasswordInput(), label="Password confirmation")

    class Meta:
        model = User
        fields = ('phone', 'role', 'gender', 'date_of_birth')

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirmation = cleaned_data.get("password_confirmation")
        if password and password_confirmation and password != password_confirmation:
            raise forms.ValidationError("The two password fields didn't match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


# 2. Custom User Admin Jo Aapke Naye fields ke sath chalega
@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    add_form = CustomUserCreationForm
    
    # List view settings
    list_display = ('phone', 'role', 'is_staff', 'is_active', 'created_at')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('phone',)
    ordering = ('-created_at',)

    # Form layouts (Yahan se date_joined hata kar created_at kiya hai jo readonly hai)
    readonly_fields = ('created_at', 'updated_at')

    def get_fieldsets(self, request, obj=None):
        if not obj:  # Jab naya user ADD ho raha ho
            return (
                (None, {'fields': ('phone', 'password', 'password_confirmation', 'role', 'gender', 'date_of_birth')}),
            )
        # Jab purana user EDIT/VIEW ho raha ho
        return (
            ('Personal Info', {'fields': ('phone', 'gender', 'date_of_birth', 'profile_photo', 'firebase_uid', 'has_used_free_session')}),
            ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
            ('Important dates', {'fields': ('created_at', 'updated_at')}),
        )

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = self.add_form
        return super().get_form(request, obj, **kwargs)
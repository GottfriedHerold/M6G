from __future__ import annotations
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
# from django.contrib.auth.forms import UserCreationForm
# import DBInterface.models.char_models
# import DBInterface.models.permission_models
# import DBInterface.models.user_model
from .models import CGUser, get_default_group
from . import models as DBInterfaceModels
# from . import models
from django.contrib.auth.forms import ReadOnlyPasswordHashField
import logging
user_logger = logging.getLogger('chargen.database.users')

class CGUserCreationForm(forms.ModelForm):
    """
    Used by Django's admin to create users.
    """
    class Meta:
        model = CGUser
        fields = ('username', 'email')

    password1 = forms.CharField(label='Enter password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Retype password', widget=forms.PasswordInput)

    def clean_password2(self):
        """
        validation of input to password2. super().clean() calls self.clean_<formname>() for all form fields.
        """
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match")
        return password2

    # needs to be overridden to properly make use of the set_password function from CGUser's base class.
    # (otherwise, the password would be stored in the clean)
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
            user.groups.add(get_default_group())
            user_logger.info('Created user %s via admin interface', user.username)
        return user

class CGUserChangeForm(forms.ModelForm):
    """
    Settings for Django's admin interface to change users.
    """
    class Meta:
        model = CGUser
        fields = ('username', 'email', 'password', 'is_active', 'is_admin', 'groups')
    password = ReadOnlyPasswordHashField()

    def clean_password(self):
        return self.initial['password']


class UserAdmin(BaseUserAdmin):
    """
    Settings required to make Django's admin interface work with our custom CGUser class.
    This is below with admin.site.register
    """
    add_form = CGUserCreationForm
    form = CGUserChangeForm
    list_display = ('username', 'email', 'is_admin')
    list_filter = ('is_admin',)
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Permissions', {'fields': ('is_admin', 'is_active')}),
        ('Groups', {'fields': ('groups',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )
    search_fields = ('username', 'email')
    ordering = 'username',
    filter_horizontal = ()


# Register your models here.
# admin.site.unregister(CGUser)
admin.site.register(CGUser, UserAdmin)
admin.site.register(DBInterfaceModels.CGGroup)
admin.site.register(DBInterfaceModels.CharModel)
admin.site.register(DBInterfaceModels.CharVersionModel)
admin.site.register(DBInterfaceModels.GroupPermissionsForChar)
admin.site.register(DBInterfaceModels.UserPermissionsForChar)
admin.site.register(DBInterfaceModels.CharUsers)
admin.site.register(DBInterfaceModels.LongDictEntry)
admin.site.register(DBInterfaceModels.ShortDictEntry)

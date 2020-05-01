from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
#from django.contrib.auth.forms import UserCreationForm
from .models import CGUser

class CGUserCreationForm(forms.ModelForm):
    class Meta:
        model = CGUser
        fields = ('username', 'email')

    password1 = forms.CharField(label='Enter password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Retype password', widget=forms.PasswordInput)

    def clean_password2(self):
        """
            validation of input to password2, called from super().clean()
        """
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1!=password2:
            raise forms.ValidationError("Passwords do not match")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user

class CGUserChangeForm(forms.ModelForm):
    class Meta:
            model = CGUser
            fields = ('username', 'email', 'password', 'is_active', 'is_admin', 'groups')

    def clean_password(self):
        return self.initial['password']


class UserAdmin(BaseUserAdmin):
    #add_form = CGUserCreationForm
    #form = CGUserChangeForm
    list_display = ('username', 'email', 'is_admin')
    list_filter = ('is_admin',)
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Permissions', {'fields': ('is_admin','is_active')}),
        #('Groups', {'fields':('groups',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )
    search_fields = ('username', 'email')
    ordering = ('username'),
    filter_horizontal = ()

# Register your models here.
admin.site.register(CGUser, UserAdmin)
"""Django admin registration for disclaimrNG models, themed with django-unfold."""

from __future__ import annotations

import json

from adminsortable2.admin import SortableAdminBase, SortableTabularInline
from django import forms
from django.contrib import admin
from django.forms import PasswordInput
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from . import constants
from .models import (
    Action,
    DirectoryServer,
    DirectoryServerURL,
    Disclaimer,
    Requirement,
    Rule,
    SignatureImage,
)
from .widgets import TemplateEditorWidget


class RequirementInline(StackedInline):
    model = Requirement
    extra = 0


class ActionInline(StackedInline):
    model = Action
    extra = 0
    ordering = ["position"]


class DirectoryServerURLInline(SortableTabularInline, TabularInline):
    model = DirectoryServerURL
    extra = 0
    min_num = 1


@admin.register(Rule)
class RuleAdmin(SortableAdminBase, ModelAdmin):
    list_display = ("name", "position", "continue_rules")
    inlines = [RequirementInline, ActionInline]


class DisclaimerForm(forms.ModelForm):
    class Meta:
        model = Disclaimer
        fields = "__all__"
        widgets = {
            "text": TemplateEditorWidget(content_type="text/plain"),
            "html": TemplateEditorWidget(content_type="text/html"),
        }


@admin.register(Disclaimer)
class DisclaimerAdmin(ModelAdmin):
    form = DisclaimerForm
    list_display = ("name", "html_use_text", "use_html_fallback")
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (
            "Plaintext part",
            {
                "fields": (
                    "text",
                    "text_charset",
                    "text_use_template",
                ),
            },
        ),
        (
            "HTML part",
            {
                "fields": (
                    "html_use_text",
                    "html",
                    "html_charset",
                    "html_use_template",
                    "use_html_fallback",
                ),
            },
        ),
        ("Behaviour", {"fields": ("template_fail",)}),
    )


@admin.register(SignatureImage)
class SignatureImageAdmin(ModelAdmin):
    list_display = ("slug", "name", "thumbnail")
    search_fields = ("slug", "name", "description")
    readonly_fields = ("thumbnail",)
    fieldsets = (
        (None, {"fields": ("slug", "name", "description")}),
        ("File", {"fields": ("image", "thumbnail")}),
        ("Display", {"fields": ("alt_text", "width", "height")}),
    )

    @admin.display(description="Preview")
    def thumbnail(self, obj: SignatureImage) -> str:
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" alt="{}" style="max-height:80px;max-width:240px;'
            'border:1px solid #d0d7de;border-radius:4px"/>',
            obj.image.url,
            obj.alt_text or obj.name,
        )


class DirectoryServerForm(forms.ModelForm):
    class Meta:
        model = DirectoryServer
        fields = "__all__"
        widgets = {"password": PasswordInput(render_value=True)}


@admin.register(DirectoryServer)
class DirectoryServerAdmin(SortableAdminBase, ModelAdmin):
    list_display = ("name", "flavor", "enabled", "base_dn")
    list_filter = ("flavor", "enabled")
    form = DirectoryServerForm
    inlines = [DirectoryServerURLInline]
    change_form_template = "admin/disclaimrwebadmin/directoryserver/change_form.html"
    fieldsets = (
        (None, {"fields": ("name", "description", "enabled")}),
        (
            "Connection",
            {
                "fields": ("flavor", "base_dn", "auth", "userdn", "password"),
            },
        ),
        (
            "Query",
            {
                "fields": ("search_query", "search_attributes"),
            },
        ),
        (
            "Cache",
            {
                "fields": ("enable_cache", "cache_timeout"),
            },
        ),
    )

    class Media:
        js = ("disclaimrwebadmin/directory_server/directory_server.js",)
        css = {
            "all": ("disclaimrwebadmin/directory_server/directory_server.css",),
        }

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["flavor_defaults"] = json.dumps(
            {
                str(flavor): {
                    "search_query": constants.DIR_FLAVOR_DEFAULT_QUERY[flavor],
                    "attributes": constants.DIR_FLAVOR_DEFAULT_ATTRIBUTES[flavor],
                }
                for flavor in constants.DIR_FLAVOR_DEFAULT_QUERY
            }
        )
        return super().changeform_view(request, object_id, form_url, extra_context)

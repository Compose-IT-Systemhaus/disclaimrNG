"""Django admin registration for disclaimrNG models, themed with django-unfold."""

from __future__ import annotations

import json

from adminsortable2.admin import CustomInlineFormSet, SortableAdminBase, SortableTabularInline
from django import forms
from django.contrib import admin
from django.template.defaultfilters import linebreaksbr
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.widgets import (
    UnfoldAdminFileFieldWidget,
    UnfoldAdminPasswordWidget,
    UnfoldAdminTextareaWidget,
)

from . import constants
from .models import (
    Action,
    DirectoryServer,
    DirectoryServerURL,
    Disclaimer,
    MailLog,
    Requirement,
    RequirementCondition,
    Rule,
    SignatureImage,
    SSOGroupMapping,
    Tenant,
    TenantDomain,
)
from .widgets import TemplateEditorWidget


class RequirementInline(StackedInline):
    model = Requirement
    extra = 0
    show_change_link = True


class RequirementConditionInline(TabularInline):
    model = RequirementCondition
    extra = 1
    fields = ("kind", "attribute", "pattern", "group_dn")


@admin.register(Requirement)
class RequirementAdmin(ModelAdmin):
    """Reached from the rule; it carries the directory conditions as an inline."""

    list_display = ("name", "rule", "action", "enabled")
    list_filter = ("rule",)
    search_fields = ("name", "rule__name")
    inlines = [RequirementConditionInline]

    def get_model_perms(self, request):
        return {}  # not in the dashboard or the app list; the rule links here


class ActionInline(StackedInline):
    model = Action
    extra = 0
    ordering = ["position"]


class TenantDomainInline(TabularInline):
    model = TenantDomain
    extra = 1


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    list_display = ("name", "slug", "enabled", "domain_summary")
    list_filter = ("enabled",)
    search_fields = ("name", "slug", "description", "domains__domain")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TenantDomainInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "enabled")}),
    )

    def get_queryset(self, request):
        # One query for all domains of the page instead of one per row.
        return super().get_queryset(request).prefetch_related("domains")

    @admin.display(description="Domains")
    def domain_summary(self, obj: Tenant) -> str:
        domains = [d.domain for d in obj.domains.all()]
        if not domains:
            return "—"
        if len(domains) <= 3:
            return ", ".join(domains)
        return f"{', '.join(domains[:3])} (+{len(domains) - 3} more)"


class DirectoryServerURLFormSet(CustomInlineFormSet):
    """The URL scheme has to match the server's TLS setting (ldaps:// iff TLS)."""

    def clean(self):
        super().clean()
        for form in self.forms:
            data = getattr(form, "cleaned_data", {})
            url = data.get("url", "")
            if not url or data.get("DELETE"):
                continue
            is_tls = url.lower().startswith("ldaps://")
            if self.instance.use_tls and not is_tls:
                form.add_error("url", _("TLS is on: use an ldaps:// URL (or turn TLS off)."))
            elif not self.instance.use_tls and is_tls:
                form.add_error("url", _("TLS is off: use an ldap:// URL (or turn TLS on)."))


class DirectoryServerURLInline(SortableTabularInline, TabularInline):
    model = DirectoryServerURL
    formset = DirectoryServerURLFormSet
    extra = 0
    min_num = 1


@admin.register(Rule)
class RuleAdmin(SortableAdminBase, ModelAdmin):
    list_display = ("name", "tenant", "position", "continue_rules")
    list_filter = ("tenant", "continue_rules")
    list_select_related = ("tenant",)
    autocomplete_fields = ("tenant",)
    inlines = [RequirementInline, ActionInline]


class DisclaimerForm(forms.ModelForm):
    class Meta:
        model = Disclaimer
        # Explicit list keeps ruff DJ006/DJ007 happy (no ``exclude``,
        # no ``"__all__"``). Keep in sync with the Disclaimer model.
        fields = (
            "tenant",
            "name",
            "description",
            "text",
            "text_charset",
            "text_use_template",
            "html_use_text",
            "html",
            "html_charset",
            "html_use_template",
            "template_fail",
            "use_html_fallback",
        )
        widgets = {
            "text": TemplateEditorWidget(content_type="text/plain"),
            "html": TemplateEditorWidget(content_type="text/html"),
        }


@admin.register(Disclaimer)
class DisclaimerAdmin(ModelAdmin):
    form = DisclaimerForm
    list_display = ("name", "tenant", "html_use_text", "use_html_fallback")
    list_filter = ("tenant",)
    list_select_related = ("tenant",)
    autocomplete_fields = ("tenant",)
    fieldsets = (
        (None, {"fields": ("tenant", "name", "description")}),
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
        ("Display", {"fields": ("alt_text", "width", "height", "embed")}),
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
    ca_certificate_file = forms.FileField(
        required=False,
        label=_("CA certificate file"),
        help_text=_("Upload a PEM file; it replaces the CA certificate text below."),
        widget=UnfoldAdminFileFieldWidget,
    )

    class Meta:
        model = DirectoryServer
        # Explicit list keeps ruff DJ006/DJ007 happy (no ``exclude``,
        # no ``"__all__"``). Keep in sync with the DirectoryServer model.
        fields = (
            "tenant",
            "name",
            "description",
            "enabled",
            "flavor",
            "base_dn",
            "use_tls",
            "ca_certificate",
            "auth",
            "userdn",
            "password",
            "search_query",
            "search_attributes",
            "enable_cache",
            "cache_timeout",
        )
        # Unfold's widget, so the field looks like the user-DN field above it.
        widgets = {
            "password": UnfoldAdminPasswordWidget(render_value=True),
            "ca_certificate": UnfoldAdminTextareaWidget(attrs={"rows": 6}),
        }

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get("ca_certificate_file")
        if upload:
            try:
                if upload.size > 64 * 1024:
                    raise ValueError
                cleaned["ca_certificate"] = upload.read().decode("ascii")
            except (ValueError, UnicodeDecodeError):
                self.add_error("ca_certificate_file", _("Not a PEM certificate file."))
        return cleaned


@admin.register(DirectoryServer)
class DirectoryServerAdmin(SortableAdminBase, ModelAdmin):
    list_display = ("name", "tenant", "flavor", "enabled", "base_dn")
    list_filter = ("tenant", "flavor", "enabled")
    list_select_related = ("tenant",)
    autocomplete_fields = ("tenant",)
    form = DirectoryServerForm
    inlines = [DirectoryServerURLInline]
    change_form_template = "admin/disclaimrwebadmin/directoryserver/change_form.html"
    fieldsets = (
        (None, {"fields": ("tenant", "name", "description", "enabled")}),
        (
            "Connection",
            {
                "fields": (
                    "flavor",
                    "base_dn",
                    "use_tls",
                    "ca_certificate_file",
                    "ca_certificate",
                    "auth",
                    "userdn",
                    "password",
                ),
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


@admin.register(SSOGroupMapping)
class SSOGroupMappingAdmin(ModelAdmin):
    list_display = ("sso_group", "group")
    list_select_related = ("group",)
    search_fields = ("sso_group", "group__name")


@admin.register(MailLog)
class MailLogAdmin(ModelAdmin):
    """Read-only list of the mails the milter saw — visible to superusers only."""

    list_display = ("created", "sender", "recipient", "subject", "processed", "applied_summary")
    list_filter = ("processed",)
    search_fields = ("sender", "recipient", "subject", "queue_id", "applied")
    date_hierarchy = "created"
    fields = (
        "created", "queue_id", "sender", "recipient", "subject", "sender_ip", "processed", "applied"
    )
    readonly_fields = fields

    def has_module_permission(self, request) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    @admin.display(description=_("Applied signatures"))
    def applied_summary(self, obj: MailLog) -> str:
        return linebreaksbr(obj.applied) or "—"

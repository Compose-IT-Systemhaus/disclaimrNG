"""Django admin registration for disclaimrNG models, themed with django-unfold."""

from __future__ import annotations

import json
import re

from adminsortable2.admin import SortableAdminBase
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.template.defaultfilters import linebreaksbr
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.widgets import (
    UnfoldAdminFileFieldWidget,
    UnfoldAdminPasswordWidget,
    UnfoldAdminTextareaWidget,
)

from . import constants
from .html_text import html_to_text
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


class EditLinkMixin:
    """A pencil column that opens the object.

    The first column links there too, but nothing in the list says so.
    """

    @admin.display(description=_("Edit"))
    def edit_link(self, obj) -> str:
        opts = obj._meta
        return format_html(
            '<a href="{}" title="{}" aria-label="{}">'
            '<span class="material-symbols-outlined" aria-hidden="true">edit</span></a>',
            reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk]),
            _("Edit"),
            _("Edit"),
        )


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
class TenantAdmin(EditLinkMixin, ModelAdmin):
    list_display = ("name", "slug", "enabled", "domain_summary", "edit_link")
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


@admin.register(Rule)
class RuleAdmin(EditLinkMixin, SortableAdminBase, ModelAdmin):
    list_display = ("name", "tenant", "position", "continue_rules", "edit_link")
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
            "font_family",
            "font_size",
            "text_from_html",
            "template_fail",
            "use_html_fallback",
        )
        widgets = {
            "text": TemplateEditorWidget(content_type="text/plain"),
            "html": TemplateEditorWidget(content_type="text/html"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Shown above the text part by disclaimer_form.js while the switch is on.
        self.fields["text_from_html"].widget.attrs["data-hint"] = _(
            "Generated from the HTML part when saving — changes here are overwritten."
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("text_from_html"):
            cleaned["text"] = html_to_text(cleaned.get("html", ""))
        return cleaned


@admin.register(Disclaimer)
class DisclaimerAdmin(EditLinkMixin, ModelAdmin):
    form = DisclaimerForm
    list_display = ("name", "tenant", "html_use_text", "use_html_fallback", "edit_link")
    list_filter = ("tenant",)
    list_select_related = ("tenant",)
    autocomplete_fields = ("tenant",)
    # The signature is designed in the HTML part; the text part usually follows from it.
    fieldsets = (
        (None, {"fields": ("tenant", "name", "description")}),
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
        ("Formatting", {"fields": ("font_family", "font_size")}),
        (
            "Plaintext part",
            {
                "fields": (
                    "text_from_html",
                    "text",
                    "text_charset",
                    "text_use_template",
                ),
            },
        ),
        ("Behaviour", {"fields": ("template_fail",)}),
    )

    class Media:
        js = ("disclaimrwebadmin/js/disclaimer_form.js",)

    def get_changeform_initial_data(self, request):
        # New signatures start in the HTML workflow; existing ones keep their setting.
        return {
            "html_use_text": False,
            "text_from_html": True,
            **super().get_changeform_initial_data(request),
        }


@admin.register(SignatureImage)
class SignatureImageAdmin(EditLinkMixin, ModelAdmin):
    list_display = ("slug", "name", "thumbnail", "edit_link")
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


# host, IPv4 or [IPv6], optionally :port — what is left of an LDAP URL without scheme and path
_HOST_RE = re.compile(r"^(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9][A-Za-z0-9.-]*)(:\d{1,5})?$")


class DirectoryServerForm(forms.ModelForm):
    hosts = forms.CharField(
        label=_("Hosts"),
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}),
        help_text=_(
            "Host name of the server, optionally with :port (default 636 with TLS, 389 "
            "without). With TLS it has to be the name in the server's certificate, usually "
            "the full name (dc1.example.com), not the IP address. One per line; further "
            "lines are tried in order if the first does not answer."
        ),
    )
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["hosts"] = "\n".join(
                re.sub(r"^ldaps?://|/$", "", u.url)
                for u in self.instance.directoryserverurl_set.all()
            )

    def clean_hosts(self) -> list[str]:
        # A pasted URL is fine: the scheme comes from the TLS switch, the rest is checked.
        hosts = [
            re.sub(r"^ldaps?://|/$", "", line.strip(), flags=re.IGNORECASE)
            for line in self.cleaned_data["hosts"].splitlines()
            if line.strip()
        ]
        bad = [h for h in hosts if not _HOST_RE.match(h)]
        if bad or not hosts:
            raise forms.ValidationError(
                _("Not a host name or IP address (with optional :port): %(hosts)s"),
                params={"hosts": ", ".join(bad)},
            )
        return hosts

    def urls(self) -> list[str]:
        scheme = "ldaps" if self.cleaned_data.get("use_tls") else "ldap"
        return [f"{scheme}://{host}" for host in self.cleaned_data["hosts"]]

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
class DirectoryServerAdmin(EditLinkMixin, ModelAdmin):
    list_display = ("name", "tenant", "flavor", "enabled", "base_dn", "edit_link")
    list_filter = ("tenant", "flavor", "enabled")
    list_select_related = ("tenant",)
    autocomplete_fields = ("tenant",)
    form = DirectoryServerForm
    change_form_template = "admin/disclaimrwebadmin/directoryserver/change_form.html"
    fieldsets = (
        (None, {"fields": ("tenant", "name", "description", "enabled")}),
        (
            "Connection",
            {
                "fields": (
                    "flavor",
                    "hosts",
                    "use_tls",
                    "base_dn",
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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.directoryserverurl_set.all().delete()
        DirectoryServerURL.objects.bulk_create(
            DirectoryServerURL(directory_server=obj, url=url, position=i)
            for i, url in enumerate(form.urls())
        )

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
class SSOGroupMappingAdmin(EditLinkMixin, ModelAdmin):
    list_display = ("sso_group", "group", "edit_link")
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


# Users and groups keep Django's admins; they only get the edit column like the other lists.
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(EditLinkMixin, BaseUserAdmin):
    list_display = (*BaseUserAdmin.list_display, "edit_link")


@admin.register(Group)
class GroupAdmin(EditLinkMixin, BaseGroupAdmin):
    list_display = ("name", "edit_link")

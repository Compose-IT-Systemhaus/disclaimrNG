"""Database models for the disclaimrNG web administration."""

from __future__ import annotations

import netaddr
from django.db import models
from django.utils.translation import gettext_lazy as _

from . import constants


def _signature_image_upload_to(instance: "SignatureImage", filename: str) -> str:
    """Place uploads under ``signatures/<slug>/<filename>``.

    Keeping the slug in the path means re-uploading a different file under
    the same slug doesn't collide with the previous one (older files stay
    on disk until manually purged), and a single ``ls signatures/<slug>/``
    shows the version history.
    """
    return f"signatures/{instance.slug}/{filename}"


class Rule(models.Model):
    """A disclaimer rule.

    If all requirements are met, the actions of the rule are carried out.
    """

    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("The name of this rule."),
    )
    description = models.TextField(
        _("description"),
        help_text=_("The description of this rule."),
        blank=True,
    )
    position = models.PositiveIntegerField(
        _("position"),
        help_text=_("The position inside the rule processor"),
        default=0,
    )
    continue_rules = models.BooleanField(
        _("Continue after this rule"),
        help_text=_(
            "Continue with other possibly matching rules after this one is processed?"
        ),
        default=False,
    )

    class Meta:
        ordering = ["position"]
        verbose_name = _("Rule")
        verbose_name_plural = _("Rules")

    def __str__(self) -> str:
        return self.name


class Requirement(models.Model):
    """A disclaimer requirement.

    Describes various filters that need to match for a rule to apply.
    A requirement set to *deny* will short-circuit the whole rule.
    Each rule needs at least one *accept* requirement.
    """

    rule = models.ForeignKey(
        Rule,
        verbose_name=_("Rule"),
        on_delete=models.CASCADE,
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("The name of this requirement."),
    )
    description = models.TextField(
        _("description"),
        help_text=_("The description of this requirement."),
        blank=True,
    )
    enabled = models.BooleanField(
        _("enabled"),
        default=True,
        help_text=_("Is this requirement enabled?"),
    )
    sender_ip = models.GenericIPAddressField(
        _("sender-IP address"),
        help_text=_("A filter for the IP-address of the sender server."),
        default="0.0.0.0",
    )
    sender_ip_cidr = models.CharField(
        _("netmask"),
        max_length=2,
        help_text=_("The CIDR-netmask for the sender ip address"),
        default="0",
    )
    sender = models.TextField(
        _("sender"),
        help_text=_("A regexp, that has to match the sender of a mail."),
        default=".*",
    )
    recipient = models.TextField(
        _("recipient"),
        help_text=_("A regexp, that has to match the recipient of a mail"),
        default=".*",
    )
    header = models.TextField(
        _("header-filter"),
        help_text=_(
            "A regexp, that has to match all headers of a mail. The headers will be "
            "represented in a key: value - format."
        ),
        default=".*",
    )
    body = models.TextField(
        _("body-filter"),
        help_text=_("A regexp, that has to match the body of a mail"),
        default=".*",
    )
    action = models.SmallIntegerField(
        _("action"),
        help_text=_("What to do, if this requirement is met?"),
        choices=(
            (constants.REQ_ACTION_ACCEPT, _("Accept rule")),
            (constants.REQ_ACTION_DENY, _("Deny rule")),
        ),
        default=constants.REQ_ACTION_ACCEPT,
    )

    class Meta:
        verbose_name = _("Requirement")
        verbose_name_plural = _("Requirements")

    def get_sender_ip_network(self) -> netaddr.IPNetwork:
        return netaddr.IPNetwork(f"{self.sender_ip}/{self.sender_ip_cidr}")

    def __str__(self) -> str:
        if not self.enabled:
            return f"{self.name} ({_('disabled')})"
        return self.name


class Disclaimer(models.Model):
    """A disclaimer text used in an :class:`Action`.

    Holds plaintext and HTML representations of a signature, with optional
    template-tag substitution.
    """

    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("Name of this disclaimer"),
        default="",
    )
    description = models.TextField(
        _("description"),
        help_text=_("A short description of this disclaimer"),
        default="",
        blank=True,
    )
    text = models.TextField(
        _("text-part"),
        help_text=_("A plain text disclaimer"),
        default="",
        blank=True,
    )
    text_charset = models.CharField(
        _("Charset"),
        help_text=_("Charset of the text field"),
        default="utf-8",
        max_length=255,
    )
    text_use_template = models.BooleanField(
        _("use template tags"),
        help_text=_(
            "Use template tags in the text part. Available tags are: {sender}, "
            "{recipient} and all attributes provided by resolving the sender in a "
            "directory server"
        ),
        default=True,
    )
    html_use_text = models.BooleanField(
        _("use text part"),
        help_text=_("Use the contents of the text part for the html part"),
        default=True,
    )
    html = models.TextField(
        _("html-part"),
        help_text=_(
            "An HTML disclaimer (if not filled, the plain text disclaimer will be used)."
        ),
        default="",
        blank=True,
    )
    html_charset = models.CharField(
        _("Charset"),
        help_text=_("Charset of the html field"),
        default="utf-8",
        max_length=255,
    )
    html_use_template = models.BooleanField(
        _("use template tags"),
        help_text=_(
            "Use template tags in the html part. Available tags are: {sender}, "
            "{recipient} and all attributes provided by resolving the sender in a "
            "directory server"
        ),
        default=True,
    )
    template_fail = models.BooleanField(
        _("fail if template doesn't exist"),
        help_text=_(
            "Don't use this disclaimer (and stop the associated action) if a template "
            "tag cannot be filled. If this is false, the template tag will be replaced "
            "with an empty string."
        ),
        default=False,
    )
    use_html_fallback = models.BooleanField(
        _("use HTML as a fallback"),
        help_text=_(
            "Usually disclaimr tries to identify the content type of the sent mail and "
            "uses the matching disclaimer. If that doesn't work, use HTML instead of "
            "text."
        ),
        default=False,
    )

    class Meta:
        verbose_name = _("Disclaimer")
        verbose_name_plural = _("Disclaimers")

    def __str__(self) -> str:
        return self.name


class DirectoryServer(models.Model):
    """An LDAP / Active Directory server used by the resolver."""

    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("The name of this directory server."),
    )
    description = models.TextField(
        _("description"),
        help_text=_("The description of this directory server."),
        blank=True,
    )
    enabled = models.BooleanField(
        _("enabled"),
        default=True,
        help_text=_("Is this directory server enabled?"),
    )
    flavor = models.SmallIntegerField(
        _("flavour"),
        help_text=_(
            "Pre-fills sensible defaults for the search query and attribute "
            "autocomplete. Pick 'Active Directory' for AD, 'LDAP' for vanilla "
            "OpenLDAP/389DS, 'Custom' to disable the defaults."
        ),
        choices=(
            (constants.DIR_FLAVOR_LDAP, _("LDAP")),
            (constants.DIR_FLAVOR_AD, _("Active Directory")),
            (constants.DIR_FLAVOR_CUSTOM, _("Custom")),
        ),
        default=constants.DIR_FLAVOR_LDAP,
    )
    base_dn = models.CharField(
        _("base-dn"),
        max_length=255,
        help_text=_("The LDAP base dn."),
    )
    auth = models.SmallIntegerField(
        _("auth-method"),
        help_text=_("Authentication method to connect to the server"),
        choices=(
            (constants.DIR_AUTH_NONE, _("None")),
            (constants.DIR_AUTH_SIMPLE, _("Simple")),
        ),
        default=constants.DIR_AUTH_NONE,
    )
    userdn = models.CharField(
        _("user-DN"),
        max_length=255,
        help_text=_("DN of the user to authenticate with"),
        blank=True,
        default="",
    )
    password = models.CharField(
        _("password"),
        max_length=255,
        help_text=_("Password to authenticate with"),
        blank=True,
        default="",
    )
    search_query = models.TextField(
        _("search query"),
        help_text=_(
            "A search query to run against the directory server to fetch the LDAP "
            "object when resolving. %s will be replaced when resolving."
        ),
        default="mail=%s",
    )
    enable_cache = models.BooleanField(
        _("enable cache"),
        help_text=_("Enable the LDAP query cache for this directory server"),
        default=True,
    )
    cache_timeout = models.SmallIntegerField(
        _("cache timeout"),
        help_text=_("How long (in seconds) a query is cached"),
        default=3600,
    )
    search_attributes = models.TextField(
        _("attribute vocabulary"),
        help_text=_(
            "Comma- or newline-separated list of attribute names exposed to the "
            "template editor's autocomplete (e.g. cn, mail, telephoneNumber). "
            "Leave empty to use the flavour defaults."
        ),
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = _("Directory server")
        verbose_name_plural = _("Directory servers")

    def __str__(self) -> str:
        if not self.enabled:
            return f"{self.name} ({_('disabled')})"
        return self.name

    def get_attribute_vocabulary(self) -> list[str]:
        """Return the curated attribute list (custom or flavour default)."""
        raw = (self.search_attributes or "").replace("\n", ",")
        custom = [a.strip() for a in raw.split(",") if a.strip()]
        if custom:
            return custom
        return list(constants.DIR_FLAVOR_DEFAULT_ATTRIBUTES.get(self.flavor, []))


class DirectoryServerURL(models.Model):
    """A URL pointing at a :class:`DirectoryServer`.

    A directory server can have multiple URLs that are tried in order if the
    earlier ones do not respond.
    """

    directory_server = models.ForeignKey(
        DirectoryServer,
        verbose_name=_("Directory server"),
        on_delete=models.CASCADE,
    )
    url = models.CharField(
        _("URL"),
        max_length=255,
        help_text=_(
            "URL of the directory server. For example: ldap://ldapserver:389/ or "
            "ldaps://ldapserver/"
        ),
    )
    position = models.PositiveSmallIntegerField(_("Position"))

    class Meta:
        ordering = ["position"]
        verbose_name = _("URL")
        verbose_name_plural = _("URLs")

    def __str__(self) -> str:
        return self.url


class SignatureImage(models.Model):
    """An image asset that can be embedded in disclaimers via ``{image["slug"]}``.

    Stored on disk under ``MEDIA_ROOT/signatures/<slug>/`` and referenced
    from rendered HTML disclaimers as an absolute URL (``MEDIA_BASE_URL`` +
    file path). For plaintext disclaimers, the tag expands to the bare URL.
    """

    slug = models.SlugField(
        _("slug"),
        max_length=64,
        unique=True,
        help_text=_(
            "Used as the substitution key — write {image[\"<slug>\"]} in a "
            "disclaimer to embed this image."
        ),
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("Display name shown in the admin and in autocomplete."),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
    )
    image = models.ImageField(
        _("image"),
        upload_to=_signature_image_upload_to,
        help_text=_("PNG/JPG/SVG file. Keep it small — every recipient will load it."),
    )
    alt_text = models.CharField(
        _("alt text"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Used as the <img alt=\"…\"> attribute when rendered."),
    )
    width = models.PositiveSmallIntegerField(
        _("display width"),
        null=True,
        blank=True,
        help_text=_(
            "Optional width in pixels. Leave empty to use the image's intrinsic size."
        ),
    )
    height = models.PositiveSmallIntegerField(
        _("display height"),
        null=True,
        blank=True,
        help_text=_("Optional height in pixels."),
    )

    class Meta:
        ordering = ["slug"]
        verbose_name = _("Signature image")
        verbose_name_plural = _("Signature images")

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class Action(models.Model):
    """A disclaimer action.

    Describes what to do with a mail that meets the requirements of its rule.
    """

    rule = models.ForeignKey(
        Rule,
        verbose_name=_("Rule"),
        on_delete=models.CASCADE,
    )
    position = models.PositiveSmallIntegerField(_("Position"))
    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("The name of this action."),
    )
    enabled = models.BooleanField(
        _("enabled"),
        default=True,
        help_text=_("Is this action enabled?"),
    )
    description = models.TextField(
        _("description"),
        help_text=_("The description of this action."),
        blank=True,
    )
    action = models.SmallIntegerField(
        _("action"),
        help_text=_("What action should be done?"),
        choices=(
            (
                constants.ACTION_ACTION_REPLACETAG,
                _("Replace a tag in the body with a disclaimer string"),
            ),
            (
                constants.ACTION_ACTION_ADD,
                _("Add a disclaimer string to the body"),
            ),
            (
                constants.ACTION_ACTION_ADDPART,
                _("Add the disclaimer using an additional MIME part"),
            ),
        ),
        default=constants.ACTION_ACTION_ADD,
    )
    only_mime = models.CharField(
        _("mime type"),
        max_length=255,
        help_text=_("Only carry out the action in the given mime type"),
        default="",
        blank=True,
    )
    action_parameters = models.TextField(
        _("action parameters"),
        help_text=_(
            "Parameters for the action (see the action documentation for details)"
        ),
        default="",
        blank=True,
    )
    resolve_sender = models.BooleanField(
        _("resolve the sender"),
        help_text=_(
            "Resolve the sender by querying a directory server and provide data for "
            "the template tags inside a disclaimer"
        ),
        default=False,
    )
    resolve_sender_fail = models.BooleanField(
        _("fail when unable to resolve sender"),
        help_text=_("Stop the action if the sender cannot be resolved."),
        default=False,
    )
    disclaimer = models.ForeignKey(
        Disclaimer,
        verbose_name=_("Disclaimer"),
        help_text=_("Which disclaimer to use"),
        on_delete=models.PROTECT,
    )
    directory_servers = models.ManyToManyField(
        DirectoryServer,
        verbose_name=_("Directory servers"),
        help_text=_("Which directory server(s) to use."),
        blank=True,
    )

    class Meta:
        ordering = ["position"]
        verbose_name = _("Action")
        verbose_name_plural = _("Actions")

    def __str__(self) -> str:
        if not self.enabled:
            return f"{self.name} ({_('disabled')})"
        return self.name

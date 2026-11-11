""" Disclaimrweb Constants """

# Requirement Actions

REQ_ACTION_ACCEPT = 0
REQ_ACTION_DENY = 1

# Fonts offered for signatures: (name, CSS font stack). Mail-safe fonts, plus Calibri and
# Segoe UI (Outlook/Windows) with a fallback for Mac and mobile. Used by the model choices
# and the TinyMCE toolbar alike.
SIGNATURE_FONTS = [
    ("Arial", "Arial, Helvetica, sans-serif"),
    ("Calibri", "Calibri, Arial, sans-serif"),
    ("Courier New", "'Courier New', Courier, monospace"),
    ("Georgia", "Georgia, serif"),
    ("Helvetica", "Helvetica, Arial, sans-serif"),
    ("Segoe UI", "'Segoe UI', Arial, sans-serif"),
    ("Tahoma", "Tahoma, Geneva, sans-serif"),
    ("Times New Roman", "'Times New Roman', Times, serif"),
    ("Trebuchet MS", "'Trebuchet MS', Arial, sans-serif"),
    ("Verdana", "Verdana, Geneva, sans-serif"),
]
# Font sizes in pt (Outlook measures in pt).
SIGNATURE_FONT_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 24]

# Requirement directory conditions

COND_KIND_ATTRIBUTE = 0
COND_KIND_GROUP = 1

# Actions Actions

ACTION_ACTION_REPLACETAG = 0
ACTION_ACTION_ADD = 1
ACTION_ACTION_ADDPART = 2

# Directory Server auth methods

DIR_AUTH_NONE = 0
DIR_AUTH_SIMPLE = 1

# Directory Server flavours
#
# A flavour is a soft hint that lets the admin UI pre-fill sensible defaults
# for the search query and the attribute autocomplete vocabulary. Resolution
# itself does not branch on the flavour — once saved, all directory servers
# are queried the same way.

DIR_FLAVOR_LDAP = 0
DIR_FLAVOR_AD = 1
DIR_FLAVOR_CUSTOM = 2

# Default search filters per flavour. ``%s`` is replaced with the envelope
# sender address at query time (see DirectoryServer.search_query).
DIR_FLAVOR_DEFAULT_QUERY = {
    DIR_FLAVOR_LDAP: "mail=%s",
    DIR_FLAVOR_AD: "(|(mail=%s)(userPrincipalName=%s))",
    DIR_FLAVOR_CUSTOM: "mail=%s",
}

# Default attribute vocabulary used by the template editor autocomplete.
# These can be overridden per-server via DirectoryServer.search_attributes.
DIR_FLAVOR_DEFAULT_ATTRIBUTES = {
    DIR_FLAVOR_LDAP: [
        "cn",
        "displayName",
        "givenName",
        "sn",
        "mail",
        "telephoneNumber",
        "mobile",
        "title",
        "ou",
        "o",
    ],
    DIR_FLAVOR_AD: [
        "cn",
        "displayName",
        "givenName",
        "sn",
        "mail",
        "userPrincipalName",
        "sAMAccountName",
        "telephoneNumber",
        "mobile",
        "title",
        "department",
        "company",
        "physicalDeliveryOfficeName",
        "streetAddress",
        "l",
        "postalCode",
        "co",
    ],
    DIR_FLAVOR_CUSTOM: [],
}

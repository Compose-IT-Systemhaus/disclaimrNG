""" Disclaimrweb Constants """

# Requirement Actions

REQ_ACTION_ACCEPT = 0
REQ_ACTION_DENY = 1

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

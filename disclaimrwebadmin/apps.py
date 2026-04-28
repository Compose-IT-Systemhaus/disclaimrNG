"""App config for ``disclaimrwebadmin`` — sets the verbose name and
patches the admin index so the dashboard's app list mirrors the
sidebar's *Signaturen* / *Einstellungen* groups instead of dumping
every model under a single ``Disclaimrwebadmin`` heading.
"""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

# Lower-case object_name -> which sidebar group the model belongs to.
# Anything not listed here stays under whatever app Django put it in.
_SIGNATURE_MODELS = {"disclaimer", "rule", "signatureimage"}
_SETTINGS_MODELS = {"tenant", "directoryserver"}


class DisclaimrwebadminConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "disclaimrwebadmin"
    verbose_name = _("disclaimrNG")

    def ready(self) -> None:
        from django.contrib import admin

        original_get_app_list = admin.site.get_app_list

        def patched_get_app_list(request, app_label=None):
            apps = list(original_get_app_list(request, app_label))

            signatures_group = {
                "name": _("Signatures"),
                "app_label": "signatures",
                "app_url": "",
                "has_module_perms": True,
                "models": [],
            }
            settings_group = {
                "name": _("Settings"),
                "app_label": "settings",
                "app_url": "",
                "has_module_perms": True,
                "models": [],
            }
            leftover_apps: list[dict] = []

            for app in apps:
                if app["app_label"] == "disclaimrwebadmin":
                    for model in app["models"]:
                        obj = model["object_name"].lower()
                        if obj in _SIGNATURE_MODELS:
                            signatures_group["models"].append(model)
                        elif obj in _SETTINGS_MODELS:
                            settings_group["models"].append(model)
                        else:
                            # Unknown new model — keep it under the
                            # original app heading so it never goes
                            # missing from the dashboard.
                            leftover_apps.append(
                                {**app, "models": [model]}
                            )
                elif app["app_label"] == "auth":
                    # Pull Users/Groups under Settings to match the
                    # sidebar (where ``Benutzer`` and ``Gruppen`` sit
                    # in the Einstellungen section).
                    settings_group["models"].extend(app["models"])
                else:
                    leftover_apps.append(app)

            result: list[dict] = []
            if signatures_group["models"]:
                result.append(signatures_group)
            if settings_group["models"]:
                result.append(settings_group)
            result.extend(leftover_apps)
            return result

        admin.site.get_app_list = patched_get_app_list

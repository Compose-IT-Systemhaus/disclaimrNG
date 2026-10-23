/**
 * Inject a compact EN / DE toggle into unfold's topbar.
 *
 * The toggle POSTs ``/i18n/setlang/`` (Django's built-in language
 * switch view) which sets the ``django_language`` cookie and reloads
 * the current page. Each language is a tiny form with a submit button —
 * plain HTML round-trip, no client-side state.
 *
 * Text codes instead of flag emoji: Windows renders flag emoji as bare
 * letters ("GB", "DE").
 */
(function () {
    "use strict";

    const LANGUAGES = [
        { code: "en", label: "EN", title: "English" },
        { code: "de", label: "DE", title: "Deutsch" },
    ];

    function getCookie(name) {
        const m = document.cookie.match(
            "(^|; )" + name + "=([^;]*)"
        );
        return m ? decodeURIComponent(m[2]) : "";
    }

    function csrfToken() {
        const node = document.querySelector("[name=csrfmiddlewaretoken]");
        if (node) return node.value;
        return getCookie("csrftoken");
    }

    function hiddenInput(name, value) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        return input;
    }

    function buildSwitcher(currentLang) {
        const wrap = document.createElement("div");
        wrap.className = "language-switcher";
        wrap.setAttribute("role", "group");
        wrap.setAttribute("aria-label", "Language");
        for (const language of LANGUAGES) {
            const form = document.createElement("form");
            form.method = "post";
            form.action = "/i18n/setlang/";
            form.className = "language-switcher__form";
            form.appendChild(hiddenInput("csrfmiddlewaretoken", csrfToken()));
            form.appendChild(hiddenInput("language", language.code));
            form.appendChild(
                hiddenInput("next", window.location.pathname + window.location.search)
            );

            const active = language.code === currentLang;
            const button = document.createElement("button");
            button.type = "submit";
            button.className =
                "language-switcher__button" +
                (active ? " language-switcher__button--active" : "");
            button.title = language.title;
            button.lang = language.code;
            button.setAttribute("aria-pressed", active ? "true" : "false");
            button.textContent = language.label;
            form.appendChild(button);

            wrap.appendChild(form);
        }
        return wrap;
    }

    /**
     * The right-hand action area of unfold's topbar, or the corner with
     * the theme switch on the login page.
     */
    function findToolbar() {
        const topbar = document.querySelector("#header-inner .ml-auto");
        if (topbar) return topbar;
        const unauthenticated = document.querySelector("body.login #page .absolute .ml-auto");
        if (unauthenticated) {
            unauthenticated.classList.add("dz-unauth-tools");
            return unauthenticated;
        }
        return null;
    }

    function insertSwitcher() {
        if (document.querySelector(".language-switcher")) return; // idempotent
        const toolbar = findToolbar();
        if (!toolbar) return;
        const lang = (document.documentElement.lang || "en").split("-")[0];
        toolbar.prepend(buildSwitcher(lang));
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", insertSwitcher);
    } else {
        insertSwitcher();
    }
})();

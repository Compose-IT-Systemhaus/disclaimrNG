/**
 * Inject a tiny DE / EN flag toggle into unfold's topbar.
 *
 * The toggle POSTs ``/i18n/setlang/`` (Django's built-in language
 * switch view) which sets the ``django_language`` cookie and reloads
 * the current page. We render two flag buttons that submit hidden
 * forms — keeping the round-trip in plain HTML so it works without
 * any extra client-side state.
 */
(function () {
    "use strict";

    const FLAGS = [
        { code: "en", label: "EN", emoji: "🇬🇧", title: "English" },
        { code: "de", label: "DE", emoji: "🇩🇪", title: "Deutsch" },
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

    function buildSwitcher(currentLang) {
        const wrap = document.createElement("div");
        wrap.className = "language-switcher";
        for (const flag of FLAGS) {
            const form = document.createElement("form");
            form.method = "post";
            form.action = "/i18n/setlang/";
            form.className = "language-switcher__form";

            const csrfInput = document.createElement("input");
            csrfInput.type = "hidden";
            csrfInput.name = "csrfmiddlewaretoken";
            csrfInput.value = csrfToken();
            form.appendChild(csrfInput);

            const langInput = document.createElement("input");
            langInput.type = "hidden";
            langInput.name = "language";
            langInput.value = flag.code;
            form.appendChild(langInput);

            const nextInput = document.createElement("input");
            nextInput.type = "hidden";
            nextInput.name = "next";
            nextInput.value = window.location.pathname + window.location.search;
            form.appendChild(nextInput);

            const button = document.createElement("button");
            button.type = "submit";
            button.className =
                "language-switcher__button" +
                (flag.code === currentLang
                    ? " language-switcher__button--active"
                    : "");
            button.title = flag.title;
            button.setAttribute("aria-label", flag.title);
            button.innerHTML = `<span class="language-switcher__flag" aria-hidden="true">${flag.emoji}</span><span class="language-switcher__label">${flag.label}</span>`;
            form.appendChild(button);

            wrap.appendChild(form);
        }
        return wrap;
    }

    function insertSwitcher() {
        if (document.querySelector(".language-switcher")) return; // idempotent

        // unfold renders the user-menu / theme-switcher block on the
        // right of the topbar. Try a couple of candidate hooks and
        // pin our switcher next to the first one we find. As a last
        // resort fall back to ``<header>`` / ``<body>`` so it never
        // disappears entirely.
        const candidates = [
            "header [data-active-link]",      // unfold "Return to site" link
            "header form#logout-form",        // unfold logout form
            "header [data-target='theme']",   // unfold theme switcher
            "header nav",
            "header",
            "body",
        ];
        for (const sel of candidates) {
            const host = document.querySelector(sel);
            if (!host) continue;
            const switcher = buildSwitcher(
                document.documentElement.lang || "en"
            );
            // Insert before so the switcher sits to the *left* of
            // the user menu / theme toggle.
            if (host.parentNode && host.tagName !== "BODY") {
                host.parentNode.insertBefore(switcher, host);
            } else {
                host.appendChild(switcher);
            }
            return;
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", insertSwitcher);
    } else {
        insertSwitcher();
    }
})();

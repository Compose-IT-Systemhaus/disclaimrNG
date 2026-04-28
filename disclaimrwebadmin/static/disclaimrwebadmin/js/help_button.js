/**
 * Inject a "?" help button into unfold's topbar that links to the
 * bundled docs at ``/admin/disclaimr/docs/``. Lives next to the
 * language switcher.
 *
 * The docs URL is read from a ``data-docs-url`` attribute on
 * ``<body>`` so we don't have to hard-code Django's URL routing here.
 */
(function () {
    "use strict";

    function findDocsUrl() {
        return (
            document.body.dataset.docsUrl
            || "/admin/disclaimr/docs/"
        );
    }

    function buildButton() {
        const a = document.createElement("a");
        a.className = "help-button";
        a.href = findDocsUrl();
        a.title = "Documentation";
        a.setAttribute("aria-label", "Documentation");
        a.innerHTML =
            '<span class="help-button__mark" aria-hidden="true">?</span>';
        return a;
    }

    function insertButton() {
        if (document.querySelector(".help-button")) return;

        const candidates = [
            ".language-switcher",            // sit right next to the flag toggle
            "header [data-active-link]",
            "header form#logout-form",
            "header [data-target='theme']",
            "header nav",
            "header",
            "body",
        ];
        for (const sel of candidates) {
            const host = document.querySelector(sel);
            if (!host) continue;
            const button = buildButton();
            if (host.parentNode && host.tagName !== "BODY") {
                host.parentNode.insertBefore(button, host);
            } else {
                host.appendChild(button);
            }
            return;
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", insertButton);
    } else {
        insertButton();
    }
})();

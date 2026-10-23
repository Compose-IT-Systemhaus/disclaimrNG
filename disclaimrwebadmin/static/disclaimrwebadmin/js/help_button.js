/**
 * Inject a help button into unfold's topbar that links to the bundled
 * docs at ``/admin/disclaimr/docs/``. Sits next to the language toggle.
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
        const label = document.documentElement.lang === "de" ? "Dokumentation" : "Documentation";
        const a = document.createElement("a");
        a.className = "help-button";
        a.href = findDocsUrl();
        a.title = label;
        a.setAttribute("aria-label", label);
        a.innerHTML =
            '<span class="material-symbols-outlined" aria-hidden="true">help</span>';
        return a;
    }

    function insertButton() {
        if (document.querySelector(".help-button")) return;
        // Only in the authenticated topbar — the docs need a login anyway.
        const toolbar = document.querySelector("#header-inner .ml-auto");
        if (!toolbar) return;
        toolbar.appendChild(buildButton());
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", insertButton);
    } else {
        insertButton();
    }
})();

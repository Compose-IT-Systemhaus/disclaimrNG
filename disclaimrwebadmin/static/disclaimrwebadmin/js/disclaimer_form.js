/**
 * Signature form: while "create the text part from the HTML part" is on, the text part is
 * generated on save — show it as read-only with a hint instead of letting edits get lost.
 */
(function () {
    "use strict";

    function init() {
        const toggle = document.querySelector('[name="text_from_html"]');
        const row = document.querySelector(".field-text");
        if (!toggle || !row) return;

        const hint = document.createElement("p");
        hint.className = "disclaimer-form__generated-hint";
        hint.textContent = toggle.dataset.hint || "";
        row.prepend(hint);

        const update = () => {
            hint.hidden = !toggle.checked;
            const editor = row.querySelector(".template-editor");
            if (editor) {
                editor.style.opacity = toggle.checked ? "0.6" : "";
                editor.style.pointerEvents = toggle.checked ? "none" : "";
            }
        };
        toggle.addEventListener("change", update);
        update();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

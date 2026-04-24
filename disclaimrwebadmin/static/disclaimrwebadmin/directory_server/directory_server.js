/**
 * Directory-server admin enhancements.
 *
 *  - Flavour preset auto-fill: changing the "flavour" select drops a default
 *    search query and attribute vocabulary into their fields, but only when
 *    those fields are still empty (so we never clobber an admin's edits).
 *  - "Test connection" button: POSTs to the test endpoint and renders the
 *    per-URL probe results.
 *  - "Discover attributes" button: POSTs to the attributes endpoint and
 *    drops the discovered attribute names into the search_attributes
 *    textarea (after confirming with the admin if it isn't empty).
 */
(function () {
    "use strict";

    function csrfToken() {
        const el = document.querySelector("[name=csrfmiddlewaretoken]");
        return el ? el.value : "";
    }

    function getField(name) {
        return document.querySelector(`[name="${name}"]`);
    }

    function setOutput(node, state, text) {
        node.hidden = false;
        node.classList.remove("is-ok", "is-error", "is-pending");
        if (state) node.classList.add(`is-${state}`);
        node.textContent = text;
    }

    function buildUrl(template, id) {
        // Django's {% url %} with a placeholder of 0 — swap in the real id.
        return template.replace(/\/0\//, `/${id}/`);
    }

    async function postAction(url) {
        const fd = new FormData();
        fd.append("csrfmiddlewaretoken", csrfToken());
        const response = await fetch(url, {
            method: "POST",
            body: fd,
            credentials: "same-origin",
        });
        return response.json();
    }

    function renderTestResult(node, data) {
        if (!data.probes || !data.probes.length) {
            setOutput(node, data.ok ? "ok" : "error", data.summary || "(no result)");
            return;
        }
        const lines = [data.summary || ""];
        for (const probe of data.probes) {
            const marker = probe.ok ? "✓" : "✗";
            lines.push(`${marker} ${probe.url} — ${probe.detail}`);
        }
        setOutput(node, data.ok ? "ok" : "error", lines.join("\n"));
    }

    function renderAttributes(node, data, vocabField) {
        if (!data.ok) {
            setOutput(node, "error", data.detail || "Discovery failed.");
            return;
        }
        const attrs = data.attributes || [];
        const lines = [
            `Sampled DN: ${data.sample_dn}`,
            `${attrs.length} attribute(s) found:`,
            attrs.join(", "),
        ];
        setOutput(node, "ok", lines.join("\n"));

        if (!vocabField) return;
        const current = (vocabField.value || "").trim();
        const fill =
            !current ||
            window.confirm(
                "Replace the current attribute vocabulary with the discovered list?"
            );
        if (fill) {
            vocabField.value = attrs.join(", ");
        }
    }

    function applyFlavorPreset(defaults, flavor) {
        const preset = defaults[String(flavor)];
        if (!preset) return;

        const queryField = getField("search_query");
        if (queryField && !queryField.value.trim()) {
            queryField.value = preset.search_query;
        }

        const vocabField = getField("search_attributes");
        if (vocabField && !vocabField.value.trim()) {
            vocabField.value = (preset.attributes || []).join(", ");
        }
    }

    function init() {
        const root = document.querySelector(".directory-server-actions");
        if (!root) return;

        let defaults = {};
        try {
            defaults = JSON.parse(root.dataset.flavorDefaults || "{}");
        } catch (err) {
            console.warn("flavor defaults parse failed", err);
        }

        const flavorField = getField("flavor");
        if (flavorField) {
            flavorField.addEventListener("change", () => {
                applyFlavorPreset(defaults, flavorField.value);
            });
        }

        const objectId = root.dataset.objectId;
        if (!objectId) return;

        const output = root.querySelector(".directory-server-actions__output");
        const testUrl = buildUrl(root.dataset.testUrlTemplate, objectId);
        const attrsUrl = buildUrl(root.dataset.attributesUrlTemplate, objectId);
        const vocabField = getField("search_attributes");

        root.querySelectorAll("[data-action]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                setOutput(output, "pending", "Working…");
                btn.disabled = true;
                try {
                    if (btn.dataset.action === "test") {
                        const data = await postAction(testUrl);
                        renderTestResult(output, data);
                    } else if (btn.dataset.action === "discover") {
                        const data = await postAction(attrsUrl);
                        renderAttributes(output, data, vocabField);
                    }
                } catch (err) {
                    setOutput(output, "error", String(err));
                } finally {
                    btn.disabled = false;
                }
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

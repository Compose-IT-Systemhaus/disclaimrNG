/**
 * Directory-server admin enhancements.
 *
 *  - Flavour preset auto-fill: changing the "flavour" select drops a default
 *    search query and attribute vocabulary into their fields, but only when
 *    those fields are still empty (so we never clobber an admin's edits).
 *  - "Test connection" button next to the save buttons: POSTs the form as it is
 *    (nothing is saved) and renders the per-URL probe results above the buttons.
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

    async function postAction(url, fd = new FormData()) {
        fd.set("csrfmiddlewaretoken", csrfToken());
        const response = await fetch(url, {
            method: "POST",
            body: fd,
            credentials: "same-origin",
        });
        if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
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

    function addTestButton(root) {
        const form = document.querySelector("#directoryserver_form");
        const save = document.querySelector('#submit-row [name="_save"]');
        if (!form || !save) return;

        const button = document.createElement("button");
        button.type = "button";
        const next = document.querySelector('#submit-row [name="_continue"]') || save;
        button.className = next.className;
        button.innerHTML =
            '<span class="material-symbols-outlined" aria-hidden="true">network_check</span>';
        button.append(` ${root.dataset.testLabel}`);
        // The row is flex-row-reverse: right after "Save" in the DOM is just left of it.
        save.after(button);

        const output = document.createElement("div");
        output.className = "directory-server-actions__output directory-server-test-output";
        output.hidden = true;
        document.querySelector("#submit-row").before(output);

        button.addEventListener("click", async () => {
            setOutput(output, "pending", "…");
            button.disabled = true;
            try {
                const fd = new FormData(form);
                if (root.dataset.objectId) fd.set("_object_id", root.dataset.objectId);
                renderTestResult(output, await postAction(root.dataset.testUrl, fd));
            } catch (err) {
                setOutput(output, "error", String(err));
            } finally {
                button.disabled = false;
            }
        });
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

        // The CA certificate only matters with TLS.
        const tlsField = getField("use_tls");
        if (tlsField) {
            const showCa = () => {
                document
                    .querySelectorAll(".field-ca_certificate, .field-ca_certificate_file")
                    .forEach((row) => {
                        row.style.display = tlsField.checked ? "" : "none";
                    });
            };
            tlsField.addEventListener("change", showCa);
            showCa();
        }

        const flavorField = getField("flavor");
        if (flavorField) {
            flavorField.addEventListener("change", () => {
                applyFlavorPreset(defaults, flavorField.value);
            });
        }

        addTestButton(root);

        const objectId = root.dataset.objectId;
        if (!objectId) return;

        const output = root.querySelector(".directory-server-actions__output");
        const attrsUrl = buildUrl(root.dataset.attributesUrlTemplate, objectId);
        const vocabField = getField("search_attributes");

        root.querySelectorAll("[data-action]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                setOutput(output, "pending", "Working…");
                btn.disabled = true;
                try {
                    if (btn.dataset.action === "discover") {
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

/**
 * Template editor — Code / Visual / Preview tabs sharing one textarea.
 *
 * Loaded by the TemplateEditorWidget. Pulls Monaco and TinyMCE from
 * jsdelivr — versions are pinned so the editor behaves the same across
 * deployments. (Self-hosting both libraries would mean shipping a
 * couple of MB extra in the image; for an admin UI the CDN trade-off
 * is fine. Vendoring is tracked as a follow-up issue.)
 *
 *   window.monaco — Monaco editor (loaded via require())
 *   window.tinymce — TinyMCE editor
 *
 * The widget's hidden <textarea> is the source of truth. Tab switches sync
 * the active editor's content back into the textarea so nothing is lost.
 */
(function () {
    "use strict";

    const MONACO_VERSION = "0.50.0";
    const TINYMCE_VERSION = "7.3.0";

    const MONACO_LOADER_URL =
        `https://cdn.jsdelivr.net/npm/monaco-editor@${MONACO_VERSION}/min/vs/loader.js`;
    const MONACO_BASE_URL =
        `https://cdn.jsdelivr.net/npm/monaco-editor@${MONACO_VERSION}/min/vs`;
    const TINYMCE_URL =
        `https://cdn.jsdelivr.net/npm/tinymce@${TINYMCE_VERSION}/tinymce.min.js`;

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[src="${src}"]`);
            if (existing) {
                if (existing.dataset.loaded === "true") return resolve();
                existing.addEventListener("load", () => resolve());
                existing.addEventListener("error", reject);
                return;
            }
            const script = document.createElement("script");
            script.src = src;
            script.async = true;
            script.addEventListener("load", () => {
                script.dataset.loaded = "true";
                resolve();
            });
            script.addEventListener("error", reject);
            document.head.appendChild(script);
        });
    }

    async function ensureMonaco() {
        if (window.monaco) return window.monaco;
        await loadScript(MONACO_LOADER_URL);
        await new Promise((resolve) => {
            window.require.config({ paths: { vs: MONACO_BASE_URL } });
            window.require(["vs/editor/editor.main"], resolve);
        });
        return window.monaco;
    }

    async function ensureTinyMCE() {
        if (window.tinymce) return window.tinymce;
        await loadScript(TINYMCE_URL);
        return window.tinymce;
    }

    function activateTab(root, tab) {
        root.querySelectorAll(".template-editor__tab").forEach((btn) => {
            const isActive = btn.dataset.tab === tab;
            btn.classList.toggle("is-active", isActive);
            btn.setAttribute("aria-selected", isActive ? "true" : "false");
        });
        root.querySelectorAll(".template-editor__pane").forEach((pane) => {
            pane.classList.toggle("is-active", pane.dataset.pane === tab);
        });
    }

    // Cache the vocabulary fetch across editor instances on the same page —
    // both Disclaimer.text and Disclaimer.html mount the widget, no point
    // hitting the endpoint twice. Upload handler invalidates the cache so
    // a freshly-uploaded image shows up immediately in every gallery.
    let vocabularyPromise = null;
    function loadVocabulary(url) {
        if (!url) return Promise.resolve({ attributes: [], images: [] });
        if (!vocabularyPromise) {
            vocabularyPromise = fetch(url, { credentials: "same-origin" })
                .then((r) =>
                    r.ok ? r.json() : { attributes: [], images: [] }
                )
                .catch(() => ({ attributes: [], images: [] }));
        }
        return vocabularyPromise;
    }
    function invalidateVocabulary() {
        vocabularyPromise = null;
    }

    function csrfToken() {
        const node = document.querySelector("[name=csrfmiddlewaretoken]");
        return node ? node.value : "";
    }

    function renderImageGallery(root, images) {
        const grid = root.querySelector(".template-editor__images-grid");
        if (!grid) return;
        if (!images.length) {
            grid.innerHTML =
                '<div class="template-editor__images-empty">' +
                "Noch keine Bilder hochgeladen.</div>";
            return;
        }
        grid.innerHTML = images
            .map(
                (img) => `
                <button type="button" class="template-editor__image"
                        data-slug="${img.slug}"
                        title="Klicken zum Einfügen — Slug: ${img.slug}">
                    <img src="${img.url}" alt="${img.alt_text || img.name}">
                    <span class="template-editor__image-slug">${img.slug}</span>
                </button>
            `
            )
            .join("");
    }

    function renderPlaceholderChips(root, vocab) {
        const grid = root.querySelector(".template-editor__chips-grid");
        if (!grid) return;
        const fixed = ["sender", "recipient"];
        const headers = ["subject", "from", "to", "cc", "date"];
        const attributes = (vocab && vocab.attributes) || [];

        const chip = (token, kind, label, hint) =>
            `<button type="button" class="template-editor__chip"
                     data-token="${token.replace(/"/g, "&quot;")}"
                     data-kind="${kind}"
                     title="${(hint || token).replace(/"/g, "&quot;")}">
                <span class="template-editor__chip-label">${label}</span>
            </button>`;

        const sections = [];

        // Envelope (sender / recipient)
        sections.push(
            `<div class="template-editor__chip-group">
                <div class="template-editor__chip-group-title">Umschlag</div>
                <div class="template-editor__chip-row">${
                    fixed.map((k) => chip(`{${k}}`, "envelope", k)).join("")
                }</div>
            </div>`
        );

        // Mail headers
        sections.push(
            `<div class="template-editor__chip-group">
                <div class="template-editor__chip-group-title">Header</div>
                <div class="template-editor__chip-row">${
                    headers
                        .map((k) =>
                            chip(`{header["${k}"]}`, "header", k, `Header: ${k}`)
                        )
                        .join("")
                }</div>
            </div>`
        );

        // LDAP / directory attributes
        if (attributes.length) {
            sections.push(
                `<div class="template-editor__chip-group">
                    <div class="template-editor__chip-group-title">
                        Verzeichnis-Attribute
                    </div>
                    <div class="template-editor__chip-row">${
                        attributes
                            .map((a) =>
                                chip(
                                    `{resolver["${a}"]}`,
                                    "resolver",
                                    a,
                                    `LDAP / AD attribute: ${a}`
                                )
                            )
                            .join("")
                    }</div>
                </div>`
            );
        } else {
            sections.push(
                `<div class="template-editor__chip-group">
                    <div class="template-editor__chip-group-title">
                        Verzeichnis-Attribute
                    </div>
                    <div class="template-editor__chips-empty">
                        Kein Verzeichnis-Server konfiguriert oder noch keine
                        Attribute entdeckt.
                    </div>
                </div>`
            );
        }

        grid.innerHTML = sections.join("");
    }

    function setStatus(root, message, kind) {
        const node = root.querySelector(".template-editor__images-status");
        if (!node) return;
        node.textContent = message || "";
        node.dataset.kind = kind || "";
    }

    function registerCompletions(monaco, language, vocab) {
        const fixed = ["sender", "recipient"];
        const headers = ["subject", "from", "to", "cc", "date"];
        const attributes = vocab.attributes || [];
        const images = vocab.images || [];

        monaco.languages.registerCompletionItemProvider(language, {
            triggerCharacters: ["{", '"'],
            provideCompletionItems(model, position) {
                const word = model.getWordUntilPosition(position);
                const range = {
                    startLineNumber: position.lineNumber,
                    endLineNumber: position.lineNumber,
                    startColumn: word.startColumn,
                    endColumn: word.endColumn,
                };
                const suggestions = [];
                for (const key of fixed) {
                    suggestions.push({
                        label: `{${key}}`,
                        kind: monaco.languages.CompletionItemKind.Variable,
                        insertText: `{${key}}`,
                        range,
                    });
                }
                for (const key of headers) {
                    suggestions.push({
                        label: `{header["${key}"]}`,
                        kind: monaco.languages.CompletionItemKind.Property,
                        insertText: `{header["${key}"]}`,
                        range,
                    });
                }
                for (const attr of attributes) {
                    suggestions.push({
                        label: `{resolver["${attr}"]}`,
                        kind: monaco.languages.CompletionItemKind.Field,
                        insertText: `{resolver["${attr}"]}`,
                        detail: "LDAP / AD attribute",
                        range,
                    });
                }
                for (const img of images) {
                    suggestions.push({
                        label: `{image["${img.slug}"]}`,
                        kind: monaco.languages.CompletionItemKind.File,
                        insertText: `{image["${img.slug}"]}`,
                        detail: `Signature image — ${img.name}`,
                        range,
                    });
                }
                return { suggestions };
            },
        });
    }

    async function initEditor(root) {
        const textarea = root.querySelector(".template-editor__source");
        const contentType = root.dataset.contentType;
        const previewUrl = root.dataset.previewUrl;
        const vocabularyUrl = root.dataset.vocabularyUrl;
        const uploadUrl = root.dataset.uploadUrl;

        const monaco = await ensureMonaco();
        const monacoHost = root.querySelector(".template-editor__monaco");
        const language = contentType === "text/html" ? "html" : "plaintext";
        const editor = monaco.editor.create(monacoHost, {
            value: textarea.value || "",
            language: language,
            automaticLayout: true,
            minimap: { enabled: false },
            wordWrap: "on",
        });
        editor.onDidChangeModelContent(() => {
            textarea.value = editor.getValue();
        });

        loadVocabulary(vocabularyUrl).then((vocab) => {
            registerCompletions(monaco, language, vocab);
            renderImageGallery(root, vocab.images || []);
            renderPlaceholderChips(root, vocab);
        });

        async function refreshGallery() {
            invalidateVocabulary();
            const vocab = await loadVocabulary(vocabularyUrl);
            renderImageGallery(root, vocab.images || []);
            renderPlaceholderChips(root, vocab);
        }

        // Insert an arbitrary token into the currently active editor
        // (Code, Visual, or — if neither is mounted — straight into the
        // textarea). Used by both the image gallery and the placeholder
        // chip strip.
        function insertToken(token) {
            const activeTab = root.querySelector(
                ".template-editor__tab.is-active"
            ).dataset.tab;
            if (activeTab === "visual" && tinymceEditor) {
                tinymceEditor.execCommand("mceInsertContent", false, token);
                textarea.value = tinymceEditor.getContent();
            } else {
                // Default to the Monaco editor, even when Preview is open
                // — there's nothing useful to do with an insert in the
                // preview iframe, so we put it in Code so it sticks.
                const selection = editor.getSelection();
                editor.executeEdits("template-editor", [
                    {
                        range: selection,
                        text: token,
                        forceMoveMarkers: true,
                    },
                ]);
                editor.focus();
                textarea.value = editor.getValue();
            }
        }

        root.addEventListener("click", (event) => {
            const imageBtn = event.target.closest(".template-editor__image");
            if (imageBtn && root.contains(imageBtn)) {
                event.preventDefault();
                insertToken(`{image["${imageBtn.dataset.slug}"]}`);
                return;
            }
            const chipBtn = event.target.closest(".template-editor__chip");
            if (chipBtn && root.contains(chipBtn)) {
                event.preventDefault();
                insertToken(chipBtn.dataset.token);
                return;
            }
        });

        const uploadInput = root.querySelector(".template-editor__upload-input");
        if (uploadInput && uploadUrl) {
            uploadInput.addEventListener("change", async () => {
                const file = uploadInput.files[0];
                if (!file) return;
                setStatus(root, `Lade ${file.name} hoch …`, "pending");
                const formData = new FormData();
                formData.append("image", file);
                formData.append("csrfmiddlewaretoken", csrfToken());
                try {
                    const response = await fetch(uploadUrl, {
                        method: "POST",
                        body: formData,
                        credentials: "same-origin",
                    });
                    const payload = await response.json();
                    if (!response.ok) {
                        setStatus(
                            root,
                            `Fehler: ${payload.error || response.statusText}`,
                            "error"
                        );
                    } else {
                        setStatus(
                            root,
                            `Hochgeladen als „${payload.slug}". Klick zum Einfügen.`,
                            "success"
                        );
                        await refreshGallery();
                    }
                } catch (err) {
                    setStatus(root, `Netzwerkfehler: ${err}`, "error");
                } finally {
                    uploadInput.value = "";
                }
            });
        }

        let tinymceEditor = null;
        const tinymceHost = root.querySelector(".template-editor__tinymce");
        if (tinymceHost) {
            const tinymce = await ensureTinyMCE();
            tinymceHost.value = textarea.value || "";
            const inits = await tinymce.init({
                target: tinymceHost,
                // Tell TinyMCE where to fetch its skins/themes/plugins
                // from — without this it would look for them on the
                // same-origin host and 404 every plugin import.
                base_url: `https://cdn.jsdelivr.net/npm/tinymce@${TINYMCE_VERSION}`,
                suffix: ".min",
                menubar: false,
                toolbar:
                    "undo redo | bold italic underline | bullist numlist | " +
                    "link unlink | alignleft aligncenter alignright | code",
                plugins: ["link", "lists", "code"],
                height: 320,
                setup: (ed) => {
                    ed.on("Change KeyUp Undo Redo", () => {
                        textarea.value = ed.getContent();
                    });
                },
            });
            tinymceEditor = inits[0] || null;
        }

        root.querySelectorAll(".template-editor__tab").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const tab = btn.dataset.tab;

                // Sync from the editor that was active *before* the switch.
                const previouslyActive = root.querySelector(
                    ".template-editor__tab.is-active"
                ).dataset.tab;
                if (previouslyActive === "code") {
                    textarea.value = editor.getValue();
                } else if (previouslyActive === "visual" && tinymceEditor) {
                    textarea.value = tinymceEditor.getContent();
                }

                activateTab(root, tab);

                // Push the textarea content into the now-active editor.
                if (tab === "code") {
                    editor.setValue(textarea.value || "");
                } else if (tab === "visual" && tinymceEditor) {
                    tinymceEditor.setContent(textarea.value || "");
                } else if (tab === "preview") {
                    const iframe = root.querySelector(".template-editor__preview");
                    const formData = new FormData();
                    formData.append("content", textarea.value || "");
                    formData.append("content_type", contentType);
                    const csrf = document.querySelector(
                        "[name=csrfmiddlewaretoken]"
                    );
                    if (csrf) formData.append("csrfmiddlewaretoken", csrf.value);
                    const response = await fetch(previewUrl, {
                        method: "POST",
                        body: formData,
                        credentials: "same-origin",
                    });
                    const html = await response.text();
                    iframe.srcdoc = html;
                }
            });
        });
    }

    function init() {
        document
            .querySelectorAll(".template-editor")
            .forEach((root) => initEditor(root).catch((err) => console.error(err)));
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

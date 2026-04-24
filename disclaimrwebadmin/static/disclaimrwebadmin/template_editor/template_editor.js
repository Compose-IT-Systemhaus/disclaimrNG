/**
 * Template editor — Code / Visual / Preview tabs sharing one textarea.
 *
 * Loaded by the TemplateEditorWidget. Expects the following globals on the
 * page (vendored by docker/fetch-frontend-deps.sh, fallback: CDN):
 *
 *   window.monaco — Monaco editor (loaded via require())
 *   window.tinymce — TinyMCE editor
 *
 * The widget's hidden <textarea> is the source of truth. Tab switches sync
 * the active editor's content back into the textarea so nothing is lost.
 */
(function () {
    "use strict";

    const MONACO_LOADER_URL =
        "/static/disclaimrwebadmin/template_editor/vendor/monaco/min/vs/loader.js";
    const MONACO_BASE_URL =
        "/static/disclaimrwebadmin/template_editor/vendor/monaco/min/vs";
    const TINYMCE_URL =
        "/static/disclaimrwebadmin/template_editor/vendor/tinymce/tinymce.min.js";

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
    // hitting the endpoint twice.
    let vocabularyPromise = null;
    function loadVocabulary(url) {
        if (!url) return Promise.resolve({ attributes: [] });
        if (!vocabularyPromise) {
            vocabularyPromise = fetch(url, { credentials: "same-origin" })
                .then((r) => (r.ok ? r.json() : { attributes: [] }))
                .catch(() => ({ attributes: [] }));
        }
        return vocabularyPromise;
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
        });

        let tinymceEditor = null;
        const tinymceHost = root.querySelector(".template-editor__tinymce");
        if (tinymceHost) {
            const tinymce = await ensureTinyMCE();
            tinymceHost.value = textarea.value || "";
            const inits = await tinymce.init({
                target: tinymceHost,
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

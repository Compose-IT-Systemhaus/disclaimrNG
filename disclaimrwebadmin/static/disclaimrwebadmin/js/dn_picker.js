/**
 * Directory conditions: while typing into the DN field of a group or OU condition, offer
 * matching groups/OUs from the directory as suggestions. Typing a DN by hand still works.
 */
(function () {
    "use strict";

    const KINDS = { 1: "group", 2: "ou" };
    const timers = new WeakMap();

    function requirementId() {
        const match = location.pathname.match(/\/requirement\/(\d+)\/change\//);
        return match ? match[1] : "";
    }

    function parts(input) {
        const kind = document.querySelector(`[name="${input.name.replace(/group_dn$/, "kind")}"]`);
        let list = document.getElementById(`${input.id}-list`);
        if (!list) {
            list = document.createElement("datalist");
            list.id = `${input.id}-list`;
            input.setAttribute("list", list.id);
            input.after(list);
        }
        let status = list.nextElementSibling;
        if (!status || !status.classList.contains("dn-picker__status")) {
            status = document.createElement("small");
            status.className = "dn-picker__status";
            list.after(status);
        }
        return { kind: kind && KINDS[kind.value], list, status };
    }

    async function search(input) {
        const { kind, list, status } = parts(input);
        const text = input.value.trim();
        if (!kind || text.length < 2 || text.includes("=")) return; // a DN, not a search
        status.textContent = input.dataset.searching || "";
        const params = new URLSearchParams({ kind, q: text, requirement: requirementId() });
        try {
            const response = await fetch(`${input.dataset.dnSearch}?${params}`, {
                credentials: "same-origin",
            });
            const data = await response.json();
            list.replaceChildren(
                ...data.results.map((entry) => {
                    const option = document.createElement("option");
                    option.value = entry.dn;
                    option.label = entry.name;
                    return option;
                })
            );
            status.textContent = data.error || (data.results.length ? "" : input.dataset.none || "");
        } catch (error) {
            status.textContent = String(error);
        }
    }

    document.addEventListener("input", (event) => {
        const input = event.target;
        if (!(input instanceof HTMLInputElement) || !input.dataset.dnSearch) return;
        clearTimeout(timers.get(input));
        timers.set(input, setTimeout(() => search(input), 300));
    });
})();

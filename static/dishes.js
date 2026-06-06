// Manage-dishes: recategorize and delete in place (no reload, no jump).
(function () {
    document.addEventListener("change", function (e) {
        var sel = e.target;
        if (!sel.classList || !sel.classList.contains("js-cat")) return;
        var f = sel.closest("form");
        fetch(f.action, {
            method: "POST",
            body: new FormData(f),
            headers: { "X-Requested-With": "fetch" },
        }).then(function (r) {
            if (!r.ok) { f.submit(); return; }
            sel.classList.add("saved");
            setTimeout(function () { sel.classList.remove("saved"); }, 900);
        }).catch(function () { f.submit(); });
    });

    document.addEventListener("submit", function (e) {
        var f = e.target;
        if (!f.classList.contains("js-del-dish")) return;
        e.preventDefault();
        var msg = f.getAttribute("data-confirm") || "Delete?";
        if (!window.confirm(msg)) return;
        fetch(f.action, {
            method: "POST",
            body: new FormData(f),
            headers: { "X-Requested-With": "fetch" },
        }).then(function (r) {
            if (!r.ok) { f.submit(); return; }
            var item = f.closest(".delete-item");
            if (item) item.remove();
        }).catch(function () { f.submit(); });
    });
})();

// Add an AI-recommended dish to today's meal without reloading, so the whole
// recommendation list stays on screen and you can add several one by one.
(function () {
    document.addEventListener("submit", function (e) {
        var f = e.target;
        if (!f.classList.contains("js-add")) return;
        e.preventDefault();
        var btn = f.querySelector("button");
        if (btn && btn.disabled) return;
        fetch(f.action, {
            method: "POST",
            body: new FormData(f),
            headers: { "X-Requested-With": "fetch" },
        }).then(function (r) {
            if (!r.ok) { f.submit(); return; }
            if (btn) {
                btn.textContent = "已加 ✓";
                btn.disabled = true;
                btn.classList.add("added");
            }
        }).catch(function () { f.submit(); });
    });
})();

// Mark a shopping item bought (remove it) without reloading. Used on both the
// mom order page and the helper dashboard.
(function () {
    document.addEventListener("submit", function (e) {
        var f = e.target;
        if (!f.classList.contains("js-shop-done")) return;
        e.preventDefault();
        fetch(f.action, {
            method: "POST",
            body: new FormData(f),
            headers: { "X-Requested-With": "fetch" },
        }).then(function (r) {
            if (!r.ok) { f.submit(); return; }
            var it = f.closest(".shop-item");
            if (it) it.remove();
        }).catch(function () { f.submit(); });
    });
})();

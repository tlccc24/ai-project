// Progressive enhancement for the fridge page: update status / delete an item
// in place via fetch, so the page never reloads or jumps back to the top.
// If JS is unavailable or a request fails, the plain form submit still works.
(function () {
    document.addEventListener("submit", function (e) {
        var f = e.target;

        // change status (有 / 不多 / 没有)
        if (f.classList.contains("js-status")) {
            e.preventDefault();
            var data = new FormData(f);
            fetch(f.action, {
                method: "POST",
                body: data,
                headers: { "X-Requested-With": "fetch" },
            }).then(function (r) {
                if (!r.ok) { f.submit(); return; }
                var seg = f.closest(".seg");
                if (seg) {
                    seg.querySelectorAll(".js-status button").forEach(function (b) {
                        b.className = "";
                    });
                }
                var st = data.get("status");
                var btn = f.querySelector("button");
                if (btn) {
                    btn.className = st === "有" ? "on-have" : (st === "不多" ? "on-low" : "on-none");
                }
            }).catch(function () { f.submit(); });
            return;
        }

        // delete an ingredient
        if (f.classList.contains("js-del")) {
            e.preventDefault();
            var msg = f.getAttribute("data-confirm") || "Delete?";
            if (!window.confirm(msg)) return;
            var data2 = new FormData(f);
            fetch(f.action, {
                method: "POST",
                body: data2,
                headers: { "X-Requested-With": "fetch" },
            }).then(function (r) {
                if (!r.ok) { f.submit(); return; }
                var item = f.closest(".fridge-item");
                if (item) item.remove();
            }).catch(function () { f.submit(); });
            return;
        }
    });
})();

// Generic instant filter. An <input class="js-filter" data-scope="#sel"> filters
// elements with class "filter-item" inside that scope by their data-name (or text),
// hides empty "filter-group" wrappers, and toggles a ".no-result" message.
(function () {
    function apply(inp) {
        var scope = document.querySelector(inp.getAttribute("data-scope"));
        if (!scope) return;
        var q = inp.value.trim().toLowerCase();
        scope.querySelectorAll(".filter-item").forEach(function (el) {
            var name = (el.getAttribute("data-name") || el.textContent || "").toLowerCase();
            el.classList.toggle("hidden", !!q && name.indexOf(q) === -1);
        });
        scope.querySelectorAll(".filter-group").forEach(function (g) {
            g.classList.toggle("hidden", !g.querySelector(".filter-item:not(.hidden)"));
        });
        var nores = scope.querySelector(".no-result");
        if (nores) {
            nores.style.display = scope.querySelector(".filter-item:not(.hidden)") ? "none" : "block";
        }
    }
    document.addEventListener("input", function (e) {
        if (e.target.classList && e.target.classList.contains("js-filter")) apply(e.target);
    });
    // don't let Enter in a filter box submit the surrounding form
    document.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && e.target.classList && e.target.classList.contains("js-filter")) {
            e.preventDefault();
        }
    });
})();

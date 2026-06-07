// Order page: add AI-recommended dishes and remove dishes from today's meal
// without reloading, so the recommendation list stays and 今天已点 updates live.
(function () {
    function removeForm(date, meal, dish) {
        var f = document.createElement("form");
        f.className = "js-remove-dish";
        f.action = "/remove_meal_dish";
        f.method = "post";
        f.innerHTML =
            '<input type="hidden" name="meal_date">' +
            '<input type="hidden" name="meal_type">' +
            '<input type="hidden" name="dish">' +
            '<button class="row-del" type="submit">✕</button>';
        f.querySelector('[name=meal_date]').value = date;
        f.querySelector('[name=meal_type]').value = meal;
        f.querySelector('[name=dish]').value = dish;
        return f;
    }

    function appendToToday(meal, dish) {
        var menu = document.getElementById("today-menu");
        if (!menu) return;
        var date = menu.getAttribute("data-today") || "";
        var list = menu.querySelector('.meal-dishes[data-today-meal="' + meal + '"]');
        if (!list) return;
        var dup = Array.prototype.some.call(list.querySelectorAll(".md-item span"),
            function (s) { return s.textContent === dish; });
        if (dup) return;
        var li = document.createElement("li");
        li.className = "md-item";
        var span = document.createElement("span");
        span.textContent = dish;
        li.appendChild(span);
        li.appendChild(removeForm(date, meal, dish));
        var empty = list.querySelector(".md-empty");
        if (empty) empty.style.display = "none";
        list.insertBefore(li, empty);
    }

    document.addEventListener("submit", function (e) {
        var f = e.target;

        // add an AI-recommended dish
        if (f.classList.contains("js-add")) {
            e.preventDefault();
            var btn = f.querySelector("button");
            if (btn && btn.disabled) return;
            var meal = f.querySelector('[name=meal_type]').value;
            var dish = f.querySelector('[name=dishes]').value;
            fetch(f.action, {
                method: "POST",
                body: new FormData(f),
                headers: { "X-Requested-With": "fetch" },
            }).then(function (r) {
                if (!r.ok) { f.submit(); return; }
                if (btn) { btn.textContent = "已加 ✓"; btn.disabled = true; btn.classList.add("added"); }
                appendToToday(meal, dish);
            }).catch(function () { f.submit(); });
            return;
        }

        // remove a dish from today's meal
        if (f.classList.contains("js-remove-dish")) {
            e.preventDefault();
            fetch(f.action, {
                method: "POST",
                body: new FormData(f),
                headers: { "X-Requested-With": "fetch" },
            }).then(function (r) {
                if (!r.ok) { f.submit(); return; }
                var li = f.closest(".md-item");
                var list = li ? li.parentNode : null;
                if (li) li.remove();
                if (list && !list.querySelector(".md-item")) {
                    var empty = list.querySelector(".md-empty");
                    if (empty) empty.style.display = "";
                }
            }).catch(function () { f.submit(); });
            return;
        }
    });
})();

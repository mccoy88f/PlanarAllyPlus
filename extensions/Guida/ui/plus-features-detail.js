/* Caricare nelle pagine plus-features/*.html dopo il body */
(function () {
    function init() {
        var currentTheme = localStorage.getItem("theme");
        if (currentTheme === "dark") document.body.classList.add("dark-theme");
        if (currentTheme === "light") document.body.classList.add("light-theme");

        var params = new URLSearchParams(window.location.search);
        var locale = (params.get("locale") || "it").toLowerCase().split("-")[0];
        if (locale !== "it") {
            document.querySelectorAll(".lang-it").forEach(function (el) {
                el.style.display = "none";
            });
            document.querySelectorAll(".lang-en").forEach(function (el) {
                el.style.display = "block";
            });
        }
        var back = document.getElementById("backToIndex");
        if (back) {
            back.href = "../plus-features.html?locale=" + encodeURIComponent(locale);
            if (locale === "it") {
                back.textContent = "← Torna all'indice delle estensioni";
                back.setAttribute("aria-label", "Torna all'indice delle estensioni");
            } else {
                back.textContent = "← Back to extensions index";
                back.setAttribute("aria-label", "Back to extensions index");
            }
        }
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

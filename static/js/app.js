document.addEventListener("DOMContentLoaded", function () {
  var sidebar = document.getElementById("sidebar");
  var sidebarToggle = document.getElementById("sidebarToggle");
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
    document.addEventListener("click", function (e) {
      if (window.innerWidth > 860) return;
      if (!sidebar.contains(e.target) && e.target !== sidebarToggle) {
        sidebar.classList.remove("open");
      }
    });
  }

  var themeToggle = document.getElementById("themeToggle");
  var root = document.documentElement;
  var saved = localStorage.getItem("gyansagar-theme");
  if (saved === "dark") root.setAttribute("data-theme", "dark");

  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      var isDark = root.getAttribute("data-theme") === "dark";
      if (isDark) {
        root.removeAttribute("data-theme");
        localStorage.setItem("gyansagar-theme", "light");
      } else {
        root.setAttribute("data-theme", "dark");
        localStorage.setItem("gyansagar-theme", "dark");
      }
    });
  }
});

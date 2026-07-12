(function () {
  var toggle = document.getElementById("mobile-nav-toggle");
  var sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("sidebar-open");
    });
  }
})();

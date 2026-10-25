/* Admin > Resources: Class -> Faculty -> Subject -> Chapter cascading dropdowns. */
(function () {
  function ready(fn) { document.readyState !== "loading" ? fn() : document.addEventListener("DOMContentLoaded", fn); }

  ready(function () {
    var level = document.getElementById("id_level"), program = document.getElementById("id_program"),
        subject = document.getElementById("id_subject"), chapter = document.getElementById("id_chapter");
    if (!level || !program || !subject || !chapter) return;

    // Hide/disable options that don't match; clear the selection if it no longer fits.
    function filter(select, test) {
      var keep = false;
      Array.prototype.forEach.call(select.options, function (o) {
        if (!o.value) { o.hidden = false; o.disabled = false; return; }
        var ok = test(o);
        o.hidden = !ok; o.disabled = !ok;
        if (ok && o.value === select.value) keep = true;
      });
      if (!keep) select.value = "";
    }

    function apply() {
      var l = level.value, p = program.value;
      filter(program, function (o) { return !l || o.getAttribute("data-level") === l; });
      p = program.value;
      filter(subject, function (o) {
        return (!l || o.getAttribute("data-level") === l) && (!p || o.getAttribute("data-program") === p);
      });
      filter(chapter, function (o) { return !!subject.value && o.getAttribute("data-subject") === subject.value; });
    }

    level.addEventListener("change", apply);
    program.addEventListener("change", apply);
    subject.addEventListener("change", function () {
      // Picking a subject first? Fill in its class / faculty automatically.
      var o = subject.options[subject.selectedIndex];
      if (o && o.value) {
        if (!level.value) level.value = o.getAttribute("data-level") || "";
        if (!program.value && o.getAttribute("data-program")) program.value = o.getAttribute("data-program");
      }
      apply();
    });
    apply();
  });
})();

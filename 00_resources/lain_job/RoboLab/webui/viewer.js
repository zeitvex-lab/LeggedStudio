/* Dependency-free viewport enhancement.  It is intentionally small: the API
   supplies geometry metadata, while this module gives users immediate visual
   feedback before a full mesh renderer is selected for deployment. */
(function () {
  window.RoboLabViewer = {
    focusJoint(name) {
      const viewport = document.querySelector(".viewport");
      if (!viewport) return;
      viewport.animate([{ filter: "brightness(1.35)" }, { filter: "brightness(1)" }], { duration: 280 });
      viewport.title = `选中关节: ${name}`;
    },
  };
})();

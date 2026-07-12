(function () {
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (e) {
        reject(e);
      } finally {
        document.body.removeChild(ta);
      }
    });
  }

  function getCopyText(btn) {
    var targetId = btn.getAttribute("data-copy-target");
    if (targetId) {
      var target = document.getElementById(targetId);
      if (target) return target.textContent.trim();
    }
    var field = btn.closest(".api-key-field");
    if (field) {
      var value = field.querySelector(".api-key-value");
      if (value) return value.textContent.trim();
    }
    return "";
  }

  function setCopiedState(btn, copied) {
    var copyIcon = btn.querySelector(".copy-api-key-icon-copy");
    var checkIcon = btn.querySelector(".copy-api-key-icon-check");
    if (copyIcon) copyIcon.hidden = copied;
    if (checkIcon) checkIcon.hidden = !copied;
    btn.classList.toggle("is-copied", copied);
    btn.setAttribute("aria-label", copied ? "Copied" : "Copy API key");
    btn.disabled = copied;
  }

  function markCopied(btn) {
    setCopiedState(btn, true);
    window.setTimeout(function () { setCopiedState(btn, false); }, 2000);
  }

  document.querySelectorAll(".copy-api-key-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var text = getCopyText(btn);
      if (!text) return;
      copyText(text)
        .then(function () { markCopied(btn); })
        .catch(function () {
          btn.classList.add("is-error");
          window.setTimeout(function () { btn.classList.remove("is-error"); }, 2000);
        });
    });
  });
})();

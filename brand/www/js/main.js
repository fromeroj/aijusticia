/* ==========================================================================
   AI Justicia — JavaScript principal
   Sin dependencias. Vanilla JS.
   ========================================================================== */
(function () {
  'use strict';

  /* ---------- Menú móvil ---------- */
  function initMobileNav() {
    var toggle = document.querySelector('.nav-toggle');
    if (!toggle) return;
    toggle.addEventListener('click', function () {
      document.body.classList.toggle('nav-open');
      var open = document.body.classList.contains('nav-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    // Cierra al hacer click en un enlace
    document.querySelectorAll('.nav-links a').forEach(function (link) {
      link.addEventListener('click', function () {
        document.body.classList.remove('nav-open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
    // Cierra con tecla Escape
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && document.body.classList.contains('nav-open')) {
        document.body.classList.remove('nav-open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ---------- Selector de nivel (pestañas) ---------- */
  function initLevelTabs() {
    var tabs = document.querySelectorAll('.level-tab');
    var panels = document.querySelectorAll('.level-panel');
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var target = tab.getAttribute('data-level');
        tabs.forEach(function (t) { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
        panels.forEach(function (p) { p.classList.remove('active'); });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        var panel = document.getElementById('level-' + target);
        if (panel) panel.classList.add('active');
      });
    });
  }

  /* ---------- FAQ acordeón ---------- */
  function initFaq() {
    var items = document.querySelectorAll('.faq-item');
    if (!items.length) return;
    items.forEach(function (item) {
      var q = item.querySelector('.faq-q');
      var a = item.querySelector('.faq-a');
      if (!q || !a) return;
      q.setAttribute('aria-expanded', 'false');
      q.addEventListener('click', function () {
        var isOpen = item.classList.contains('open');
        // Cierra los demás
        items.forEach(function (other) {
          other.classList.remove('open');
          var oq = other.querySelector('.faq-q');
          var oa = other.querySelector('.faq-a');
          if (oq) oq.setAttribute('aria-expanded', 'false');
          if (oa) oa.style.maxHeight = null;
        });
        if (!isOpen) {
          item.classList.add('open');
          q.setAttribute('aria-expanded', 'true');
          a.style.maxHeight = a.scrollHeight + 'px';
        }
      });
    });
  }

  /* ---------- Validación de formularios ---------- */
  function initForms() {
    var forms = document.querySelectorAll('form[data-validate]');
    forms.forEach(function (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var valid = true;
        // Limpia errores previos
        form.querySelectorAll('.field').forEach(function (f) { f.classList.remove('invalid'); });

        // Campos requeridos
        form.querySelectorAll('[required]').forEach(function (input) {
          var field = input.closest('.field');
          if (!input.value || (input.type === 'checkbox' && !input.checked)) {
            if (field) field.classList.add('invalid');
            valid = false;
          }
        });

        // Email
        var email = form.querySelector('input[type="email"]');
        if (email && email.value) {
          var re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (!re.test(email.value)) {
            var field = email.closest('.field');
            if (field) field.classList.add('invalid');
            valid = false;
          }
        }

        if (!valid) {
          var firstError = form.querySelector('.field.invalid');
          if (firstError) firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
          return;
        }

        // Simulación de envío exitoso (no hay backend)
        var success = form.querySelector('.form-success') || form.parentNode.querySelector('.form-success');
        form.style.display = 'none';
        if (success) {
          success.classList.add('show');
          success.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
          // Para formularios inline (waitlist)
          var msg = document.createElement('p');
          msg.className = 'form-success show';
          msg.textContent = '¡Gracias! Te avisaremos pronto.';
          form.parentNode.insertBefore(msg, form.nextSibling);
        }
      });
    });
  }

  /* ---------- Año dinámico en footer ---------- */
  function initYear() {
    var els = document.querySelectorAll('[data-year]');
    els.forEach(function (el) { el.textContent = new Date().getFullYear(); });
  }

  /* ---------- Resaltar enlace de navegación activo ---------- */
  function initActiveNav() {
    var path = window.location.pathname.split('/').pop() || 'index.html';
    document.querySelectorAll('.nav-links a').forEach(function (a) {
      var href = a.getAttribute('href');
      if (href === path) a.classList.add('active-nav');
    });
  }

  /* ---------- Init ---------- */
  document.addEventListener('DOMContentLoaded', function () {
    initMobileNav();
    initLevelTabs();
    initFaq();
    initForms();
    initYear();
    initActiveNav();
  });
})();

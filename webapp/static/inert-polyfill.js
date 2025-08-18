// Minimal inert polyfill: sets aria-hidden and disables tabindex/focusability for children
(function(){
  if ('inert' in HTMLElement.prototype) return; // native supported

  Object.defineProperty(HTMLElement.prototype, 'inert', {
    enumerable: true,
    configurable: true,
    get: function() { return this.hasAttribute('data-inert') && this.getAttribute('data-inert') === 'true'; },
    set: function(val) {
      try {
        if (val) {
          this.setAttribute('data-inert', 'true');
          this.setAttribute('aria-hidden', 'true');
          // mark and disable focusable children
          var focusables = this.querySelectorAll('a, button, input, textarea, select, [tabindex]');
          focusables.forEach(function(el){
            if (!el.hasAttribute('data-inert-tabindex')) {
              if (el.hasAttribute('tabindex')) el.setAttribute('data-inert-tabindex', el.getAttribute('tabindex'));
              else el.setAttribute('data-inert-tabindex', 'none');
            }
            try { el.setAttribute('tabindex', '-1'); } catch(e){}
            try { el.setAttribute('aria-hidden', 'true'); } catch(e){}
          });
        } else {
          this.removeAttribute('data-inert');
          this.removeAttribute('aria-hidden');
          var focusables = this.querySelectorAll('[data-inert-tabindex]');
          focusables.forEach(function(el){
            var prev = el.getAttribute('data-inert-tabindex');
            if (prev === 'none') el.removeAttribute('tabindex'); else el.setAttribute('tabindex', prev);
            el.removeAttribute('data-inert-tabindex');
            el.removeAttribute('aria-hidden');
          });
        }
      } catch (e) { console.warn('inert polyfill error', e); }
    }
  });
})();

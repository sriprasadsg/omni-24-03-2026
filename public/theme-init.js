/* Runs before first paint (loaded from <head>; an external file because the CSP allows no inline
   script). Applies the saved theme and density so a light or compact user never sees a dark,
   roomy flash before React starts. Mirrors contexts/ThemeProvider.tsx. */
(function () {
  var root = document.documentElement;
  var get = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var pref = get('app-theme-preference');
  if (pref !== 'system' && pref !== 'light' && pref !== 'dark') pref = get('app-dark-mode') === 'false' ? 'light' : 'dark';
  var dark = pref === 'dark';
  if (pref === 'system') {
    try { dark = window.matchMedia('(prefers-color-scheme: dark)').matches; } catch (e) { dark = true; }
  }
  root.classList.toggle('dark', dark);
  root.classList.toggle('density-compact', get('app-density') === 'compact');
  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', dark ? '#060a14' : '#f3f6fa');
})();

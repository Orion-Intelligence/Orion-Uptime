// Applies the stored colour theme before the first paint so a reload never flashes the light palette.
// Loaded synchronously from index.html <head>; ThemeService re-applies the same class once Angular boots.
(function () {
  // Public status pages use a fixed light palette regardless of the stored theme.
  var theme = window.location.pathname.indexOf('/status/') === 0 ? 'light' : 'dark';
  try {
    if (theme === 'dark' && window.localStorage.getItem('orion-uptime-theme') === 'light') {
      theme = 'light';
    }
  } catch (error) {
    // Storage can be unavailable (privacy mode); keep the default theme.
  }
  var root = document.documentElement;
  root.classList.remove('dark-theme', 'light-theme');
  root.classList.add(theme + '-theme');
})();

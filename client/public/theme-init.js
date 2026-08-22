(function () {
  var theme = window.location.pathname.indexOf('/status/') === 0 ? 'light' : 'dark';
  try {
    if (theme === 'dark' && window.localStorage.getItem('orion-uptime-theme') === 'light') {
      theme = 'light';
    }
  } catch (error) {
  }
  var root = document.documentElement;
  root.classList.remove('dark-theme', 'light-theme');
  root.classList.add(theme + '-theme');
})();

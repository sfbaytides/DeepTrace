// Theme management for DeepTrace
(function() {
  // Get theme from localStorage or default to light
  function getTheme() {
    const stored = localStorage.getItem('deeptrace-theme');
    if (stored) {
      return stored;
    }
    // Default to light theme for better accessibility
    return 'light';
  }

  // Set theme and save to localStorage
  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('deeptrace-theme', theme);
  }

  // Toggle between light and dark
  window.toggleTheme = function() {
    const current = getTheme();
    const next = current === 'dark' ? 'light' : 'dark';
    setTheme(next);
  };

  // Initialize theme on page load
  const initialTheme = getTheme();
  setTheme(initialTheme);
})();

document.addEventListener('DOMContentLoaded', function() {
    // Select DOM elements
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');
    const htmlElement = document.getElementById('html-element');
    
    // Check if a preference is saved in localStorage
    const savedTheme = localStorage.getItem('theme') || 'dark';
    
    // Apply the saved theme when page loads
    applyTheme(savedTheme);
    
    // Add event listener for toggling
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
    
    // Function to toggle between themes
    function toggleTheme() {
        const currentTheme = htmlElement.getAttribute('data-bs-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        // Save new theme in localStorage
        localStorage.setItem('theme', newTheme);
        
        // Apply the new theme
        applyTheme(newTheme);
        
        // Add animation class for transition effect
        document.body.classList.add('theme-transition');
        setTimeout(() => {
            document.body.classList.remove('theme-transition');
        }, 1000);
    }
    
    // Function to apply the theme
    function applyTheme(theme) {
        // Set theme attribute
        htmlElement.setAttribute('data-bs-theme', theme);
        
        // Update icon
        if (themeIcon) {
            if (theme === 'dark') {
                themeIcon.classList.remove('fa-moon');
                themeIcon.classList.add('fa-sun');
            } else {
                themeIcon.classList.remove('fa-sun');
                themeIcon.classList.add('fa-moon');
            }
        }
        
        // Update navbar classes based on theme
        const navbar = document.querySelector('.navbar');
        if (navbar) {
            if (theme === 'dark') {
                navbar.classList.remove('navbar-light', 'bg-light');
                navbar.classList.add('navbar-dark', 'bg-dark');
            } else {
                navbar.classList.remove('navbar-dark', 'bg-dark');
                navbar.classList.add('navbar-light', 'bg-light');
            }
        }
        
        // Apply custom CSS variables for the selected theme
        updateThemeColors(theme);
    }
    
    // Function to update CSS custom properties (variables) based on theme
    function updateThemeColors(theme) {
        const root = document.documentElement;
        
        if (theme === 'dark') {
            root.style.setProperty('--custom-bg', 'var(--dark-bg)');
            root.style.setProperty('--custom-text', 'var(--dark-text)');
            root.style.setProperty('--custom-border', 'var(--dark-border)');
            root.style.setProperty('--custom-card-bg', 'var(--dark-card-bg)');
            root.style.setProperty('--custom-input-bg', 'var(--dark-input-bg)');
        } else {
            root.style.setProperty('--custom-bg', 'var(--light-bg)');
            root.style.setProperty('--custom-text', 'var(--light-text)');
            root.style.setProperty('--custom-border', 'var(--light-border)');
            root.style.setProperty('--custom-card-bg', 'var(--light-card-bg)');
            root.style.setProperty('--custom-input-bg', 'var(--light-input-bg)');
        }
    }
    
    // Check user's system preference for dark/light mode
    function checkSystemThemePreference() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }
        return 'light';
    }
    
    // Check for system theme changes and update accordingly if user hasn't set a preference
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        const userTheme = localStorage.getItem('theme');
        if (!userTheme) {
            const newTheme = e.matches ? 'dark' : 'light';
            applyTheme(newTheme);
        }
    });
});
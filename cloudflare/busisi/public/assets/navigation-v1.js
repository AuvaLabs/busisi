const header = document.querySelector('.site-header');
const toggle = document.querySelector('.nav-toggle');
const navigation = document.querySelector('#primary-navigation');
const mobile = window.matchMedia('(max-width: 720px)');

const setOpen = (open, { restoreFocus = false } = {}) => {
  if (!header || !toggle || !navigation) return;
  header.classList.toggle('nav-open', open);
  toggle.setAttribute('aria-expanded', String(open));
  toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  if (restoreFocus) toggle.focus();
};

if (header && toggle && navigation) {
  header.classList.add('nav-ready');

  toggle.addEventListener('click', () => {
    setOpen(!header.classList.contains('nav-open'));
  });

  navigation.addEventListener('click', (event) => {
    if (mobile.matches && event.target.closest('a')) setOpen(false);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && header.classList.contains('nav-open')) {
      setOpen(false, { restoreFocus: true });
    }
  });

  document.addEventListener('click', (event) => {
    if (mobile.matches && header.classList.contains('nav-open') && !header.contains(event.target)) {
      setOpen(false);
    }
  });

  mobile.addEventListener('change', () => setOpen(false));
}

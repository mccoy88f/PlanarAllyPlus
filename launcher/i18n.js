import en from './locales/en.json';
import it from './locales/it.json';

let locale = {};

function getLang() {
  const nav = navigator.language || navigator.userLanguage || 'en';
  return nav.startsWith('it') ? 'it' : 'en';
}

export async function initI18n() {
  const lang = getLang();
  locale = lang === 'it' ? it : en;
  document.documentElement.lang = lang === 'it' ? 'it' : 'en';
  applyTranslations();
}

export function t(key) {
  return locale[key] ?? key;
}

export function tFormat(key, params) {
  let s = locale[key] ?? key;
  for (const [k, v] of Object.entries(params || {})) {
    s = s.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
  }
  return s;
}

function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (key && locale[key]) {
      if (el.tagName === 'INPUT' || el.tagName === 'BUTTON') {
        el.textContent = locale[key];
      } else {
        el.textContent = locale[key];
      }
    }
  });
  const title = document.querySelector('title');
  if (title && locale.appTitle) title.textContent = locale.appTitle;
}

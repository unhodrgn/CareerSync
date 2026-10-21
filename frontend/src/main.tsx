import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { DEFAULT_LOCALE, t } from '@/i18n';
import App from './App';
import './styles/global.css';

// index.html holds the same values for the moment before this script runs
document.documentElement.lang = DEFAULT_LOCALE;
document.title = t('app.name');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

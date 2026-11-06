import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { DEFAULT_LOCALE } from '@/i18n';
import App from './App';
import { router } from './routes/router';
import { startTitleSync } from './routes/title';
import './styles/global.css';
// App pages only ([data-theme='app']): form elements, focus and autofill; the landing never matches it
import './styles/app.css';

// index.html holds the same values for the moment before this script runs
document.documentElement.lang = DEFAULT_LOCALE;
// The route's title from the start (the landing keeps the bare app name); see routes/title.ts
startTitleSync(router);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

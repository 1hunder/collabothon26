import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './styles/index.css';
import { adoptSessionFromUrl } from './api/client';
import { router } from './router';
import { SessionProvider } from './shell/lib/session';

// After a new deploy, an open tab may ask for a lazily loaded chunk of the previous build
// (e.g. StoryChart-<oldhash>.js) that no longer exists. Reload once to pick up the new build;
// the session-storage flag stops a reload loop if the chunk is genuinely missing.
window.addEventListener('vite:preloadError', (event) => {
  try {
    if (sessionStorage.getItem('fq.chunkReload') === '1') return;
    sessionStorage.setItem('fq.chunkReload', '1');
  } catch {
    /* storage blocked: still try one reload */
  }
  event.preventDefault();
  window.location.reload();
});
window.addEventListener('load', () => {
  window.setTimeout(() => {
    try {
      sessionStorage.removeItem('fq.chunkReload');
    } catch {
      /* ignore */
    }
  }, 10_000);
});

adoptSessionFromUrl();

const root = document.getElementById('root');
if (!root) throw new Error('Root element not found');

createRoot(root).render(
  <StrictMode>
    <SessionProvider>
      <RouterProvider router={router} />
    </SessionProvider>
  </StrictMode>,
);

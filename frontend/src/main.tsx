import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles/tailwind.css';

declare global {
  interface Window {
    __TOP_EUROPEAN_FOOTBALL_VERSION__?: string;
  }
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

// Surface version metadata for debugging.
window.__TOP_EUROPEAN_FOOTBALL_VERSION__ = 'v1.0.0';

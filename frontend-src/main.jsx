import React from 'react';
import ReactDOM from 'react-dom/client';
import { PostHogProvider } from 'posthog-js/react';
import App from './App.jsx';
import './index.css';

// Public PostHog project key — safe to ship in the browser bundle. US region.
const POSTHOG_KEY = 'phc_m6UAiEkP3t6tavwv8U8akS7rPmzdE3xyN9SSwwEnSxiz';
const POSTHOG_HOST = 'https://us.i.posthog.com';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PostHogProvider
      apiKey={POSTHOG_KEY}
      options={{ api_host: POSTHOG_HOST, defaults: '2025-05-24' }}
    >
      <App />
    </PostHogProvider>
  </React.StrictMode>
);

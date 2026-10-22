// React islands: React components inside Django templates, without a separate front end.
// A template mounts one with <div data-island="Name" data-props='{"key": "value"}'></div> and loads this file:
// {% vite_react_refresh %} then {% vite_asset 'assets/javascript/islands.tsx' %} in its page_js block.
import { createRoot } from 'react-dom/client';
import type { ComponentType } from 'react';
import TodayList from './islands/TodayList';

const islands: Record<string, ComponentType<any>> = { TodayList };

document.querySelectorAll<HTMLElement>('[data-island]').forEach((element: HTMLElement) => {
  const name: string = element.dataset.island ?? '';
  const Component = islands[name];
  if (!Component) {
    throw new Error(`No React island named "${name}". Register it in assets/javascript/islands.tsx.`);
  }
  const props: object = element.dataset.props ? JSON.parse(element.dataset.props) : {};
  createRoot(element).render(<Component {...props} />);
});

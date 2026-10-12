import './styles.css';
import { loadAll } from './storage/db.js';
import { bindEvents } from './tagger/events.js';
import { setStatus } from './tagger/persist.js';
import { render } from './tagger/render.js';
import { store } from './tagger/state.js';

async function init() {
  bindEvents();
  render();
  setStatus('Loading…');
  try {
    store.data = await loadAll();
    setStatus();
  } catch (e) {
    console.error(e);
    setStatus("Can't open browser storage. Changes won't be saved.");
  }
  render();
  // Ask the browser not to evict our data under storage pressure.
  if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
}

init();

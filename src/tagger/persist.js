import * as db from '../storage/db.js';
import { $ } from './dom.js';
import { store } from './state.js';

let errorMsg = '';

export function setStatus(text) {
  const el = $('#status');
  if (el) el.textContent = text || errorMsg || 'Saved in this browser';
}

async function save(promise) {
  setStatus('Saving…');
  try {
    await promise;
    errorMsg = '';
  } catch (e) {
    console.error(e);
    errorMsg = "Couldn't save. Export a backup now.";
  }
  setStatus();
}

export const saveRoster = () => save(db.putRoster(store.data.roster));

/** Persist one match, or delete it from storage if it no longer exists in memory. */
export function saveMatch(id) {
  const m = store.data.matches[id];
  return save(m ? db.putMatch(m) : db.deleteMatch(id));
}

export const saveAll = () => save(db.replaceAll(store.data));

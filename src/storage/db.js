/*
 * IndexedDB persistence. Two object stores:
 *   matches  one record per match, keyed by match.id
 *   meta     key 'roster' -> array of players
 */
const DB_NAME = 'touchline';
const DB_VERSION = 1;

let dbPromise = null;

const request = (r) =>
  new Promise((resolve, reject) => {
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });

const complete = (tx) =>
  new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });

export function openDB() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const r = indexedDB.open(DB_NAME, DB_VERSION);
      r.onupgradeneeded = () => {
        const db = r.result;
        if (!db.objectStoreNames.contains('matches')) db.createObjectStore('matches', { keyPath: 'id' });
        if (!db.objectStoreNames.contains('meta')) db.createObjectStore('meta');
      };
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
  }
  return dbPromise;
}

export async function closeDB() {
  if (!dbPromise) return;
  const db = await dbPromise;
  db.close();
  dbPromise = null;
}

/** @returns {Promise<{roster: object[], matches: Object<string, object>}>} */
export async function loadAll() {
  const db = await openDB();
  const tx = db.transaction(['matches', 'meta']);
  const [list, roster] = await Promise.all([
    request(tx.objectStore('matches').getAll()),
    request(tx.objectStore('meta').get('roster')),
  ]);
  const matches = {};
  list.forEach((m) => (matches[m.id] = m));
  return { roster: roster || [], matches };
}

export async function putMatch(m) {
  const db = await openDB();
  const tx = db.transaction('matches', 'readwrite');
  tx.objectStore('matches').put(m);
  return complete(tx);
}

export async function deleteMatch(id) {
  const db = await openDB();
  const tx = db.transaction('matches', 'readwrite');
  tx.objectStore('matches').delete(id);
  return complete(tx);
}

export async function putRoster(roster) {
  const db = await openDB();
  const tx = db.transaction('meta', 'readwrite');
  tx.objectStore('meta').put(roster, 'roster');
  return complete(tx);
}

/** Replace everything in one transaction, so a failed import leaves the old data intact. */
export async function replaceAll(data) {
  const db = await openDB();
  const tx = db.transaction(['matches', 'meta'], 'readwrite');
  const ms = tx.objectStore('matches');
  ms.clear();
  Object.values(data.matches).forEach((m) => ms.put(m));
  tx.objectStore('meta').put(data.roster, 'roster');
  return complete(tx);
}

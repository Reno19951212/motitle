// Glossary CRUD via API — uses storageState (pre-logged in as admin)
// Note: POST/PATCH /api/glossaries/<id>/entries returns the FULL updated glossary,
// not just the entry. The entry is in the returned glossary's entries array.
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("list glossaries returns glossaries array", async ({ request }) => {
  const r = await request.get(BASE + "/api/glossaries");
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body).toHaveProperty("glossaries");
  expect(Array.isArray(body.glossaries)).toBe(true);
});

test("create, add entry, and delete glossary", async ({ request }) => {
  // POST /api/glossaries returns direct glossary object (no wrapper)
  const create = await request.post(BASE + "/api/glossaries", {
    data: { name: "E2E Test Glossary", description: "Playwright test" },
  });
  expect(create.status()).toBe(201);
  const glossary = await create.json();
  expect(glossary.name).toBe("E2E Test Glossary");
  const gid = glossary.id;

  // POST entry returns the FULL updated glossary (not just the entry)
  const entry = await request.post(BASE + `/api/glossaries/${gid}/entries`, {
    data: { en: "Arsenal", zh: "阿仙奴" },
  });
  expect(entry.status()).toBe(201);
  const updatedGlossary = await entry.json();
  // The full glossary is returned with entries array containing the new entry
  expect(updatedGlossary.entries.some(e => e.en === "Arsenal" && e.zh === "阿仙奴")).toBe(true);

  // Get glossary to confirm entry exists
  const get = await request.get(BASE + `/api/glossaries/${gid}`);
  expect(get.status()).toBe(200);
  const full = await get.json();
  expect(full.entries.some(e => e.en === "Arsenal")).toBe(true);

  await request.delete(BASE + `/api/glossaries/${gid}`);
});

test("update glossary entry", async ({ request }) => {
  const create = await request.post(BASE + "/api/glossaries", {
    data: { name: "E2E Update Glossary" },
  });
  const glossary = await create.json();
  const gid = glossary.id;

  // Add entry — returns full updated glossary
  const addResp = await request.post(BASE + `/api/glossaries/${gid}/entries`, {
    data: { en: "Chelsea", zh: "車路士" },
  });
  const afterAdd = await addResp.json();
  // Find the new entry in the returned glossary
  const addedEntry = afterAdd.entries.find(e => e.en === "Chelsea");
  expect(addedEntry).toBeTruthy();
  const eid = addedEntry.id;

  // PATCH entry — returns full updated glossary
  const patch = await request.patch(BASE + `/api/glossaries/${gid}/entries/${eid}`, {
    data: { zh: "車爾西" },
  });
  expect(patch.status()).toBe(200);
  const afterPatch = await patch.json();
  const patchedEntry = afterPatch.entries.find(e => e.id === eid);
  expect(patchedEntry.zh).toBe("車爾西");

  await request.delete(BASE + `/api/glossaries/${gid}`);
});

test("delete glossary entry", async ({ request }) => {
  const create = await request.post(BASE + "/api/glossaries", {
    data: { name: "E2E Delete Entry Glossary" },
  });
  const glossary = await create.json();
  const gid = glossary.id;

  const addResp = await request.post(BASE + `/api/glossaries/${gid}/entries`, {
    data: { en: "Tottenham", zh: "熱刺" },
  });
  const afterAdd = await addResp.json();
  const addedEntry = afterAdd.entries.find(e => e.en === "Tottenham");
  const eid = addedEntry.id;

  const del = await request.delete(BASE + `/api/glossaries/${gid}/entries/${eid}`);
  expect(del.status()).toBe(200);

  const get = await request.get(BASE + `/api/glossaries/${gid}`);
  const full = await get.json();
  expect(full.entries.some(e => e.id === eid)).toBe(false);

  await request.delete(BASE + `/api/glossaries/${gid}`);
});

test("get non-existent glossary returns 404", async ({ request }) => {
  const r = await request.get(BASE + "/api/glossaries/nonexistent-glossary-id-xyz");
  expect(r.status()).toBe(404);
});

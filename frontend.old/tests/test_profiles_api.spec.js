// Profile CRUD via API — uses storageState (pre-logged in as admin)
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("list profiles returns profiles array", async ({ request }) => {
  const r = await request.get(BASE + "/api/profiles");
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body).toHaveProperty("profiles");
  expect(Array.isArray(body.profiles)).toBe(true);
});

test("create and delete profile", async ({ request }) => {
  const create = await request.post(BASE + "/api/profiles", {
    data: {
      name: "E2E Test Profile",
      asr: { engine: "whisper", model_size: "tiny" },
      translation: { engine: "mock" },
    },
  });
  expect(create.status()).toBe(201);
  // POST /api/profiles returns {"profile": {...}}
  const body = await create.json();
  const profile = body.profile;
  expect(profile.name).toBe("E2E Test Profile");
  expect(profile).toHaveProperty("id");

  const del = await request.delete(BASE + `/api/profiles/${profile.id}`);
  expect(del.status()).toBe(200);
});

test("get non-existent profile returns 404", async ({ request }) => {
  const r = await request.get(BASE + "/api/profiles/nonexistent-profile-id-xyz");
  expect(r.status()).toBe(404);
});

test("update profile name", async ({ request }) => {
  const create = await request.post(BASE + "/api/profiles", {
    data: {
      name: "Profile To Rename",
      asr: { engine: "whisper", model_size: "tiny" },
      translation: { engine: "mock" },
    },
  });
  const profile = (await create.json()).profile;

  // PATCH /api/profiles/<id> returns {"profile": {...}}
  const patch = await request.patch(BASE + `/api/profiles/${profile.id}`, {
    data: { name: "Renamed Profile" },
  });
  expect(patch.status()).toBe(200);
  const updated = (await patch.json()).profile;
  expect(updated.name).toBe("Renamed Profile");

  await request.delete(BASE + `/api/profiles/${profile.id}`);
});

test("activate profile sets it as active", async ({ request }) => {
  const create = await request.post(BASE + "/api/profiles", {
    data: {
      name: "E2E Activate Test",
      asr: { engine: "whisper", model_size: "tiny" },
      translation: { engine: "mock" },
    },
  });
  const profile = (await create.json()).profile;

  const activate = await request.post(BASE + `/api/profiles/${profile.id}/activate`);
  expect(activate.status()).toBe(200);

  const active = await request.get(BASE + "/api/profiles/active");
  expect(active.status()).toBe(200);
  const activeBody = await active.json();
  // GET /api/profiles/active returns {"profile": {...}}
  expect(activeBody.profile.id).toBe(profile.id);

  await request.delete(BASE + `/api/profiles/${profile.id}`);
});

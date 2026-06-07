# Token / License 機制設計 (Token Licensing)

**日期**：2026-06-07
**狀態**：設計已通過 brainstorming，待 user review → writing-plans
**Branch**：`feat/token-licensing`（base：`feat/glossary-v2`）
**範圍**：為 MoTitle 商業化加一個離線 license token 機制，鎖住整個 app（無有效 license = 全部功能鎖死）。

> 相關背景：研究報告（多角度 + 上網查證）已確認方向。出貨模式 = **On-prem 出貨 + air-gapped 客機** → **純離線 Ed25519 簽名 license**，無即時 revoke，靠 expiry + grace + 人手重發 + 合約審計。

---

## 1. 目標與非目標

### 目標
- 賣 MoTitle 俾客（廣播台 / 字幕公司）；客輸入 license 之後先可以用個 app。
- 支援兩種商業模式：**訂閱**（3 個月 / 1 年，有到期）同**一次性永久授權**（無到期）。
- 一律**機器綁定**（install-id），防一張 license copy 去 N 部機。
- 完全離線可驗證（air-gapped 客機 phone 唔到 home）。
- 你（owner）自己係發牌機構：手揸私鑰，用 CLI 幾秒簽一張 license，email 派發。

### 非目標（v1 YAGNI）
- 線上啟用 / heartbeat / phone-home 續期
- 即時 revocation（離線做唔到；靠 expiry + 重發 + 合約）
- Feature tier / quota / 按語言計量 / usage telemetry
- Billing 整合（v1 人手開單）
- `.lic` 檔上傳（v1 只貼字串）
- 打包/installer 時排除簽發腳本（屬另一個打包專案）

### 必須認清的現實
- **On-prem 永遠擋唔死決心夠嘅人**：代碼喺客機，可 patch 走驗證。本機制係**威懾 + 合約/審計閘**，唔係 unbreakable DRM。對低量、高信任 B2B 廣播客，呢個程度夠用。
- **永久授權 + air-gapped = 完全無法回收**（無 exp → 無 soft-kill，又離線）。屬永久授權嘅固有取捨，已接受。
- **私鑰一漏，所有 license 可被偽造** → 私鑰只放 owner 機 / 加密 backup，永不入 repo 或出貨 build。

---

## 2. 商業模式 → License 模型

| plan | exp | 用途 |
|---|---|---|
| `sub-3mo` | issued_at + 90 日 | 三個月訂閱 |
| `sub-1yr` | issued_at + 365 日 | 一年訂閱 |
| `perpetual` | `null` | 一次性永久授權 |

到期之後有 **grace 寬限期**（claim `grace_days`，預設 30 日），期間仍可用 + 紅字提醒續費，grace 過完先全鎖。

---

## 3. License Token 格式

自家 compact 格式（似 JWT 但無 alg-confusion footgun）：

```
token = base64url(payload_bytes) + "." + base64url(signature_bytes)
signature = Ed25519_sign(private_key, payload_bytes)
```

`payload_bytes` = **canonical JSON**（`json.dumps(claims, sort_keys=True, separators=(",",":"))` 的 UTF-8 bytes）：

```json
{
  "v": 1,
  "customer": "ACME Broadcast Ltd",
  "plan": "sub-1yr",
  "install_id": "8f3a2c…",
  "issued_at": 1736200000,
  "exp": 1767736000,
  "grace_days": 30,
  "features": ["ai_translation"]
}
```

- `v`：schema 版本（將來演進用）。
- `exp`：`perpetual` 時為 `null`。
- `features`：list，v1 只得 `ai_translation`，保留將來加 tier。
- 驗證次序：split `"."` → b64decode 兩段 → Ed25519 驗簽（用內嵌公鑰）→ parse JSON → 套時序 / install-id / 時鐘檢查。

---

## 4. 儲存 — `backend/config/license.json`（per-deployment，gitignore）

```json
{
  "install_id": "8f3a2c…",
  "token": "<貼入嘅 token，啟用後先有>",
  "last_seen": 1736200000,
  "activated_at": 1736200000
}
```

- `install_id`：首次運行生成（`uuid4().hex`），**無論有冇 license 都會存**。非硬件指紋（避免 VM/換機脆弱）。
- `last_seen`：防時鐘倒撥嘅 ratchet（見 §6）。
- 檔案缺失 / 壞 → 當 `none`（未啟用）。

---

## 5. 模組結構（新 package `backend/licensing/`）

| 檔案 | 職責 |
|---|---|
| `keys.py` | 內嵌**公鑰**常數（32-byte Ed25519，base64）。私鑰永不喺度。 |
| `token.py` | `sign(payload: dict, signing_key) -> str`（CLI 用）；`verify_signature(token: str) -> dict`（簽名/格式錯即 raise `InvalidToken`，成功回 claims dict）。 |
| `license_state.py` | 讀寫 `license.json`；`get_or_create_install_id()`；`read_last_seen()` / `bump_last_seen(now)`；`save_token()` / `clear_token()`。 |
| `validator.py` | `evaluate(now=None) -> LicenseStatus`：合併 簽名 + install_id 比對 + 時序(exp/grace) + 時鐘 ratchet。fail-closed。 |
| `gate.py` | `before_request` hook + allowlist；`is_unlocked(status)`。 |

每個檔案高內聚、可單獨測試。`validator.evaluate()` 係單一真相來源，gate / API / 前端狀態全部由佢驅動。

### `LicenseStatus`（dataclass / dict）
```
state: "active" | "grace" | "expired" | "wrong_machine" | "invalid" | "none"
unlocked: bool          # True 只當 state in {active, grace}
customer: str | None
plan: str | None
expires_at: int | None  # unix ts；perpetual 為 None
days_left: int | None   # 距 exp（grace 時為負到 -grace_days）
grace_days: int | None
features: list[str]
reason: str             # 給 log / UI 顯示的簡短原因
```

| state | 意思 | app 行為 |
|---|---|---|
| `active` | 有效未到期（或 perpetual） | 全解鎖 |
| `grace` | 過 exp 但喺寬限期內 | 解鎖 + 紅字「續費」橫額 |
| `expired` | grace 都過 | 鎖死 |
| `wrong_machine` | install_id 唔夾 | 鎖死（提示「license 唔屬於呢部機」） |
| `invalid` | 簽名壞 / 格式錯 / 篡改 | 鎖死 |
| `none` | 未啟用過 | 鎖死 + 顯示 install-id 等啟用 |

---

## 6. 防時鐘竄改（air-gap 信唔過客個鐘）

- `license.json.last_seen` = 歷來見過嘅最大 unix 時間。
- 每次 `evaluate()`：`now = time.time()`。
  - 若 `now < last_seen - CLOCK_SKEW`（`CLOCK_SKEW` 預設 300 秒，容 NTP 抖動）→ 判時鐘倒撥 → `state = invalid`（reason: clock rollback），鎖。
  - **有效時間 `effective_now = max(now, last_seen)`** 用嚟計 exp/grace（防撥後個鐘扮未到期）。
  - 更新 `last_seen = max(last_seen, now)`（寫返 license.json）。

---

## 7. 執行 Gate（全域 `before_request` + allowlist）

喺 `app.py` 註冊 `@app.before_request` → 調 `gate.enforce()`。

**放行清單（無需 license）：**
- 靜態：`login.html`、`license.html` + 佢哋引用嘅 `js/css`、favicon
- `GET /api/health`
- 認證：`POST /api/login`、`POST /api/logout`、`GET /api/me`
- License：`GET /api/license`、`POST /api/license/activate`、`POST /api/license/deactivate`

**其餘一律**：若 `evaluate().unlocked` 為 False →
- `/api/*` → `403 {"error":"licence required","license_state":"<state>"}`
- 頁面路由（index/proofread/Glossary/Files/user…）→ `redirect("/license.html")`
- **fail-closed**：`evaluate()` 期間任何 exception → 當鎖。

**Defense-in-depth**：背景 ASR/MT worker 派 AI job 前再 `evaluate()` 一次；唔 unlocked 就唔跑、標記 job 失敗（清楚錯誤訊息）。就算有人繞過 HTTP 層都喺 worker fail。

> 設計理由：「全部鎖死」用全域 gate 比逐個 endpoint 落 decorator 更穩陣（冇 endpoint 會漏網）。真正嘅鎖係 server gate（擋 data API）；前端 redirect 只係 UX。

---

## 8. 後端 API（新）

| Method | Path | 權限 | 作用 |
|---|---|---|---|
| GET | `/api/license` | login | 回 `LicenseStatus`：`{state, unlocked, customer, plan, expires_at, days_left, install_id, features}` |
| POST | `/api/license/activate` | **admin** | body `{token}` → `verify_signature` + install_id 夾 + 未過 grace → `save_token` → 回新狀態。失敗回乾淨 `400 {"error":"<invalid\|wrong_machine\|expired>"}`，**唔洩細節 / stack / key** |
| POST | `/api/license/deactivate` | **admin** | 清走 token（方便測試 / 轉機）→ 回 `none` 狀態 |

- 全部回 JSON，錯誤帶適當 HTTP status（跟 repo 既有 `{error:"…"}` 慣例）。
- `activate` audit log 一筆（沿用現有 `auth/audit.py`）：`license.activate`（記 customer/plan/exp，唔記全 token）。

---

## 9. 前端（vanilla JS，無 build step）

- **`frontend/license.html`（License Wall）**：登入後若 `!unlocked` 就 redirect 嚟。顯示：鎖定訊息、**install-id（一鍵複製）**、貼 token 嘅 textarea、「啟用」掣、錯誤訊息。非 admin 見 install-id + 「請聯絡管理員啟用」。
- **`user.html` 加「授權 License」分頁**：顯示狀態、到期倒數、grace 紅字、install-id、重新啟用 textarea。重用 `js/license.js`。
- **`frontend/js/license.js`**：共用模組 —— 取 `GET /api/license`、render 狀態、複製 install-id、POST activate、grace/near-exp 橫額。
- **Grace 橫額**：`state == grace` 或臨近到期（`days_left <= 14`）時，跨頁顯示持久紅字「license 已進入寬限期 / 即將到期，剩 X 日，請續費」。可由各頁 include `js/license.js` 統一注入。

---

## 10. 簽發工具 + 鎖匙（owner 機，`scripts/licensing/`）

- **`keygen.py`**（一次性）：生成 Ed25519 對。私鑰 → `~/.motitle-licensing/private_key`（owner 機，gitignore，要 backup）；公鑰 → 印出畀 owner 貼入 `backend/licensing/keys.py`。
- **`sign_license.py`**：
  ```
  python scripts/licensing/sign_license.py \
    --customer "ACME Broadcast Ltd" \
    --plan sub-1yr \            # sub-3mo | sub-1yr | perpetual
    --install-id 8f3a2c… \
    --grace-days 30 \          # 預設 30
    --features ai_translation \ # 預設 ai_translation
    --private-key ~/.motitle-licensing/private_key
  ```
  由 plan 計 exp（90 / 365 日 / null）→ canonical JSON → Ed25519 簽 → 印 token 字串。
  - **簽完自動 append `scripts/licensing/issued_licenses.csv`**（gitignore，owner 發牌帳本）。欄位：`issued_at, customer, plan, install_id, exp_human, grace_days, features, token_sha256_12`（存 token 指紋唔存全 token）。
- 私鑰**永不**入 repo / 出貨；公鑰內嵌（公開安全）。`scripts/licensing/` 出貨時應排除（下游打包處理）。

### 私鑰風險（寫入 README 運維章節）
- **唔見咗**：已發 license 照 work，但簽唔到新 / 續唔到 → 要重新 keygen + 出新版 app 換公鑰。**必須 backup**。
- **洩漏咗**：任何人可偽造 → rotate：新 keypair + 出新版 app 換公鑰 + 重發所有客 license。

---

## 11. 測試策略（TDD）

> ⚠️ 本 repo 全套 pytest 有已知 order-dependent 污染：**新測試檔要單獨跑**確認綠（`pytest tests/test_license_*.py`），唔好淨信 full-suite 紅字。

測試用一個 **test keypair** 簽 license，並 **monkeypatch `licensing.keys.PUBLIC_KEY` 做 test 公鑰**，就鑄到任意測試 license。

- `test_license_token.py`：簽/驗 roundtrip；篡改 payload → `invalid`；錯鑰 → `invalid`；爛格式 / 缺 `.` → `invalid`。
- `test_license_validator.py`：`active` / `grace`（exp 過但喺 grace_days 內）/ `expired`（過 grace）/ `wrong_machine` / `invalid` / `none`（無檔）/ `perpetual`（exp=null 永 active）/ 時鐘倒撥 → `invalid`；`effective_now` ratchet 行為。
- `test_license_gate.py`：allowlist endpoint 無 license 都通；其餘 `/api/*` 無 license → 403 帶 `license_state`；有 active/grace → 通；頁面路由 redirect `/license.html`；fail-closed。
- `test_license_api.py`：`activate` 的 valid / invalid / wrong_machine / expired（admin）；非 admin 唔 activate 得（403）；`GET /api/license` 回正確狀態；`deactivate` 清走。
- 測試沿用既有 `R5_AUTH_BYPASS` / conftest fixture 處理 login/admin。

驗收：四個新測試檔單獨跑全綠 + 既有 suite 無新增 regression（用單獨跑改到嘅檔比對）。

---

## 12. 檔案佈局（新增 / 修改）

```
新增：
  backend/licensing/__init__.py
  backend/licensing/keys.py
  backend/licensing/token.py
  backend/licensing/license_state.py
  backend/licensing/validator.py
  backend/licensing/gate.py
  backend/tests/test_license_token.py
  backend/tests/test_license_validator.py
  backend/tests/test_license_gate.py
  backend/tests/test_license_api.py
  scripts/licensing/keygen.py
  scripts/licensing/sign_license.py
  frontend/license.html
  frontend/js/license.js

修改：
  backend/app.py              # 註冊 before_request gate + 3 條 license route + worker re-check
  frontend/user.html          # 加「授權 License」分頁
  backend/requirements.txt    # + PyNaCl
  .gitignore                  # + backend/config/license.json
                              # + scripts/licensing/issued_licenses.csv
  CLAUDE.md / README.md       # 文檔（REST endpoints、運維/私鑰、發牌流程）
```

---

## 13. 實施階段（給 writing-plans 的提示）

1. **加密核心**（TDD）：`keys.py` / `token.py` / `license_state.py` / `validator.py` + 兩個測試檔。
2. **執行層**：`gate.py` + `app.py` 註冊 + worker re-check + `test_license_gate.py`。
3. **API**：3 條 route + audit + `test_license_api.py`。
4. **owner 工具**：`keygen.py` / `sign_license.py` + CSV 記錄。
5. **前端**：`license.html` / `js/license.js` / `user.html` 分頁 / grace 橫額。
6. **依賴 + 文檔 + .gitignore**：PyNaCl、CLAUDE.md、README（繁中）。

> 本改動**唔涉 ASR/MT 引擎**，所以**唔需要** Validation-First tracker。但仍要過 4 個 verification gate（pytest、curl、整合、文檔）。

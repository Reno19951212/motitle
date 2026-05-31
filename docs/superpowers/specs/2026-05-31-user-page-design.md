# User 頁（帳戶 + 改密碼 + 用戶管理 + 審計）— Design（Task B）

**日期**：2026-05-31 ｜ **狀態**：Design — 待 user review ｜ **Branch**：`fix/profile-and-v6`
**前置**：Task A（統一 5-item rail + `user.html` placeholder + `GET /user.html`）已完成。

---

## 1. 目標
將現有 admin/user 後端（`/api/admin/*` + `/api/me`）做返一個好睇嘅 **User 頁**（取代 Task A 嘅 placeholder），並加一個自助改密碼能力。`admin.html` 被吸納（redirect 去 user.html）。

## 2. 區塊（角色分區）
| 區塊 | 可見性 | 資料來源 |
|---|---|---|
| 我的帳戶（username + 角色 badge）| 所有用戶 | `/api/me` |
| 改密碼（舊→新）| 所有用戶 | **新** `POST /api/me/password` |
| 用戶管理（列表/新增/刪除/reset 密碼/toggle-admin）| admin only | `/api/admin/users` 系列（已有）|
| 審計日誌 | admin only | `/api/admin/audit`（已有）|

非 admin：只見「我的帳戶」+「改密碼」；用戶管理 + 審計區由 `is_admin` gate 隱藏。

## 3. 後端（唯一新增）
**`POST /api/me/password`**（喺 `backend/auth/routes.py` auth blueprint `bp`，mirror `/api/me` + reset_password_route pattern）：
```python
@bp.post("/api/me/password")
@login_required
@limiter.limit("10 per minute")
def change_own_password():
    data = request.get_json(silent=True) or {}
    old = data.get("old_password") or ""
    new = data.get("new_password") or ""
    if not old or not new:
        return jsonify({"error": "old_password and new_password required"}), 400
    db = current_app.config["AUTH_DB_PATH"]
    if verify_credentials(db, current_user.username, old) is None:
        log_audit(db, actor_id=current_user.id, action="password_change_failed",
                  target_kind="user", target_id=str(current_user.id))
        return jsonify({"error": "舊密碼唔啱"}), 403
    try:
        validate_password_strength(new)   # raises ValueError (太短 / 太常見)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    update_password(db, current_user.username, new)
    log_audit(db, actor_id=current_user.id, action="password_changed",
              target_kind="user", target_id=str(current_user.id))
    return jsonify({"ok": True}), 200
```
新 import（`auth/routes.py`）：`from flask import request`（若未有）、`from auth.users import update_password`、`from auth.passwords import validate_password_strength`。**只此一個新 endpoint**，其餘全用現有。屬 auth/security（非 ASR/MT → 唔涉 Validation-First）。

## 4. 前端
- **`frontend/user.html`**（取代 placeholder）：app shell（5-item rail，User active；topbar 沿用簡化版 + userchip）+ 三個 `<section>`：`#accountSection`（恆顯）、`#userMgmtSection`（admin）、`#auditSection`（admin）。改密碼 form 喺 account section。沿用既有 dark-theme CSS 變量。
- **`frontend/js/user.js`**（新）：
  - boot：`fetch('/api/me')` → render 帳戶（username + 角色 badge）；`is_admin` 為 false 就 `hidden` 兩個 admin section。
  - 改密碼：submit → `POST /api/me/password {old,new}`；200 toast 成功 + 清 form；403/400 顯示 error message。
  - 用戶管理 + 審計：**重用現有 `frontend/js/admin.js` 嘅邏輯**（`loadUsers`/`createUser`/`deleteUser`/`resetPassword`/`toggleAdmin`/`loadAudit`，打 `/api/admin/*`）。做法：將 admin.js 嗰幾個 function 搬入 user.js（或 user.js import / 內聯），對應 user.html 嘅 DOM id。
- **版面**（text mockup）：
```
我的帳戶
  👤 admin_p3   [管理員]
  改密碼：舊密碼[____] 新密碼[____] [更新密碼]
用戶管理 (admin)                         [+ 新增用戶]
  用戶名 │ 角色 │ 建立時間 │ reset│切換│刪除
審計日誌 (admin)
  時間 │ 操作者 │ 動作 │ 對象
```

## 5. admin.html 吸納
- `backend/app.py:1514` `serve_admin_page` 改為 `return redirect("/user.html")`（admin.html 入口統一去 User 頁）。
- `frontend/admin.html` + `frontend/js/admin.js`：邏輯搬入 user.js 後，admin.html 可刪（或留檔但 route 已 redirect，唔再 serve）。**Profiles / Glossaries tab 唔搬**（profiles 由 pipeline strip、glossaries 由術語表頁）。
- Task A 喺各頁加咗 `User` rail item 已連 `user.html`；admin.html 嘅 rail（Task A 加咗）變 moot（redirect 走咗），無問題。

## 6. 改動檔案
| 檔案 | 動作 |
|---|---|
| `backend/auth/routes.py` | 加 `POST /api/me/password` + import |
| `backend/app.py` | `serve_admin_page` → `redirect("/user.html")` |
| `frontend/user.html` | 換 placeholder → 完整頁（3 section + 改密碼 form）|
| `frontend/js/user.js` | **Create** — account + change-pw + (重用 admin.js)users/audit |
| `frontend/admin.html` | 刪（route 已 redirect）|
| `frontend/js/admin.js` | 邏輯搬去 user.js 後刪（或保留唔再引用）|
| `backend/tests/test_change_password.py` | **Create** |
| `frontend/tests/test_user_page.spec.js` | **Create** |

## 7. 測試
- **Backend**（`test_change_password.py`）：舊啱+新強→200 + 真改到（之後 verify_credentials 用新密碼成功）；舊錯→403 + audit `password_change_failed`；新弱（<8 / 常見）→400；缺欄→400；未登入→401；成功→audit `password_changed`。
- **Playwright**（`test_user_page.spec.js`）：admin 登入→user.html 見「我的帳戶」+「用戶管理」+「審計日誌」；非 admin 登入→只見帳戶+改密碼（兩 admin section `hidden`）；`/admin.html` GET → redirect 去 `/user.html`；改密碼 form：舊錯顯示 error、(stub 或真)成功 toast。

## 8. 範圍 / 安全 / 兼容
- 一個新 endpoint（自助改密碼），驗舊密碼 + 強度 + audit + rate-limit（10/min）。其餘重用現有 admin-only endpoints（已有 guard）。
- 純前端 + 1 endpoint + 1 redirect；無 schema / 其他 API 改動。
- 既有 dashboard / proofread / glossary / pipeline 零影響。topbar `⚙ 設定`（語言配置，Task A）不變。

## 9. 驗收標準
1. `POST /api/me/password`：舊啱新強→改到；舊錯→403；弱→400；audit 記錄。
2. user.html：admin 見 4 區、非 admin 見 2 區（帳戶+改密碼）。
3. `/admin.html` → redirect `/user.html`。
4. 用戶管理（list/create/delete/reset/toggle）+ 審計 經 user.js 運作（重用 /api/admin/*）。
5. 既有頁面零 regression。

## 10. 範圍外
- email / 頭像 / 其他 user profile 欄位（users 表只有 username/is_admin/created_at）。
- Profiles / Glossaries 管理（有自己頁面）。
- 語言配置搬入 User 頁（Task A 已放 topbar 齒輪；用戶今次冇揀 User 頁設定區）。
- 任何 ASR/MT/pipeline 邏輯。

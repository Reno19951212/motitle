# 更新交付機制設計（On-Prem 客戶軟件更新）

- **日期**：2026-06-12（討論）
- **狀態**：Design approved（待寫 implementation plan）
- **範圍**：MoTitle 出貨俾客戶嘅 on-prem macOS server appliance 嘅軟件更新功能

> 註：此處「firmware / update」係指 MoTitle **套裝軟件本身**（代碼 + Python 依賴），唔係硬件 firmware。

---

## 1. 背景與目標

客戶機係 `/opt/motitle` 嘅 git clone，以非 root 用戶身份行喺兩個 LaunchDaemon 下（`com.motitle.server` + `com.motitle.ollama`，`KeepAlive=true`），由 token licensing（Ed25519）gate 住。現時**冇任何內建更新機制** —— 更新等同人手 `git pull` + 重跑 `setup-mac.sh` + `motitle-service.sh restart`。

**目標**：畀客戶公司嘅**管理員（非技術人員）自助**喺 admin web UI 上載一個簽名更新包，一鍵安全升級，失敗自動回滾，唔使 vendor 上門。

### 決策共識（brainstorming 輸出）

| 議題 | 決策 |
|---|---|
| 網絡環境 | 兩種都要支援；**今期只做離線簽名包**（admin UI 上載），線上自動檢查留下期，但格式預留兼容 |
| 操作者 | 客戶管理員自助 → 要求全自動 + **自動回滾** |
| 更新範圍 | 代碼 + Python 依賴（offline wheels）；Ollama 模型 / Homebrew 系統依賴屬「大版本」另行人手流程 |
| 失敗處理 | **自動回滾**：新版起唔到，幾分鐘內還原舊版重啟 |
| 信任模型 | **Ed25519 簽名**（重用 licensing crypto 基建，另開 update 專用 keypair），**唔綁 license entitlement** |
| 線上來源 | 暫時唔做；feed 格式預留 |
| Server 自我更新機制 | **方案 A：root 特權 updater daemon**（執行更新嘅嘢 ≠ 被更新嘅嘢） |

---

## 2. 架構總覽

```
┌─ Vendor 端（唔出貨）──────────────────────────────────┐
│  scripts/updates/build_update.py                      │
│  git ref ──→ motitle-<version>.mtupdate（簽名更新包）  │
└───────────────────────────────────────────────────────┘
                    │ 交付（下載連結 / USB）
                    ▼
┌─ 客戶機 /opt/motitle ─────────────────────────────────┐
│  Flask server（非 root，com.motitle.server）           │
│   ├─ admin UI「系統更新」tab：上載包                    │
│   ├─ 驗簽名 + 版本門檻 → 安全解壓到 staging            │
│   └─「執行更新」→ atomic 寫 trigger 檔                 │
│                    │ WatchPaths 觸發                   │
│                    ▼                                  │
│  Updater daemon（root，com.motitle.updater）           │
│   ├─ 用自帶公鑰重新驗簽名（唔信非 root 寫嘅 staging）   │
│   ├─ 停 server → 備份舊代碼 → 裝 wheels → 換代碼        │
│   ├─ 起 server → poll /api/ready 健康檢查              │
│   ├─ fail ⇒ 還原備份 → 重啟舊版                        │
│   └─ 寫 result 檔（UI 重連後顯示結果）                  │
└───────────────────────────────────────────────────────┘
```

**核心設計原則**：updater 係「執行更新嘅嘢」，永遠唔係「被更新嘅嘢」。佢住喺 `/opt/motitle` **外面**（`/Library/Application Support/MoTitle/updater/`），代碼極少（純 shell + 一個 python 驗簽 helper），改動頻率接近零。自動回滾可靠嘅前提就係執行者本身穩定。

### 組件清單（每個單一職責，獨立可測）

| 組件 | 位置 | 職責 |
|---|---|---|
| `VERSION` 檔 | repo root | 單一版本來源；`/api/health` 加 `version` 欄位 |
| `backend/updates/package.py` | 新 module | 純邏輯：manifest 解析/驗證、Ed25519 驗簽、版本比較、tar 安全解壓 |
| `backend/updates/state.py` | 新 module | staging/trigger/result/journal 檔管理（唯一掂 `data/update/` 嘅 module，仿 `license_state.py`） |
| `backend/updates/keys.py` | 新 module | 嵌入 `UPDATE_PUBLIC_KEY_B64`（update 專用公鑰，**唔同 license key 共用**） |
| `app.py` 三條 route | 改動 | `POST /api/update/upload`、`POST /api/update/apply`、`GET /api/update/status`（全部 admin-only + audit log） |
| `packaging/macos/motitle-updater.sh` | 新 script | root updater 本體 —— 安裝時複製去 `/opt/motitle` 以外 |
| `com.motitle.updater.plist.template` | 新 plist | root daemon，`WatchPaths` 監視 trigger 目錄，平時唔行 |
| `scripts/updates/build_update.py` | 新 owner CLI | 由 git ref 砌包 + 簽名（仿 `scripts/licensing/sign_license.py`） |

---

## 3. 更新包格式 + 簽名

**檔案 `motitle-<version>.mtupdate`**（tar.gz，自定義副檔名方便 UI 過濾）：

```
motitle-4.1.0.mtupdate
├── manifest.json      # 元數據（被簽名嘅對象）
├── manifest.sig       # Ed25519 簽名（base64url，簽 canonical-JSON manifest）
└── payload.tar.gz     # 實際內容
    ├── code/          # git archive 出嚟嘅完整代碼樹
    └── wheels/        # （可選）requirements 變動時附帶嘅離線 wheels
```

**manifest.json schema：**

```json
{
  "version": "4.1.0",          // 目標版本（semver）
  "min_version": "4.0.0",      // 升級門檻：現版 < 呢個就拒裝（防跳版唔兼容）
  "payload_sha256": "…",       // payload.tar.gz hash —— 簽名經 manifest 覆蓋到成個 payload
  "created_at": 1781234567,    // 砌包時間戳
  "requires_wheels": true,     // 客戶機要唔要行 pip install
  "notes": "修復 XXX；新增 YYY" // 顯示喺 admin UI 嘅更新說明
}
```

**簽名鏈**（重用 `licensing/token.py` 嘅 canonical-JSON + Ed25519 primitives，唔重新發明）：

- `manifest.sig` 簽 manifest → manifest 內 `payload_sha256` 鎖住 payload → payload 內係全部代碼。改任何一 byte 都驗唔過。
- **獨立 keypair**：update 公鑰 `backend/updates/keys.py`，私鑰 `~/.motitle-licensing/update_private_key`（0600）。同 license key 分離 —— 任一外洩唔會連累另一邊。
- **驗兩次**：Flask（非 root）上載時驗一次（即時反饋）；root updater 執行前**用自己安裝時嵌入嗰份公鑰再驗一次**（staging 非 root 可寫，root 唔信佢）。

**tar 安全解壓**（`package.py`）：逐 member 檢查 —— 拒絕絕對路徑、`..` traversal、symlink/hardlink 出界；上載大小上限（~2GB）；解壓前檢查磁碟空間（包大小 ×3）。

**版本比較**：`min_version ≤ 現版 < version` 先准 —— 天然拒絕降級同重裝同版（降級救場屬 vendor 人手，唔開畀 admin UI）。

---

## 4. 更新執行流程 + 自動回滾

**目錄佈局（`backend/data/update/`，gitignored）：**

```
backend/data/update/
├── staged/<version>/     # Flask 解壓+初驗後嘅包內容
├── trigger.json          # Flask 寫；updater 開工指令（含 version + 申請時間）
├── journal.json          # updater 寫；行到邊一步（斷電復原用）
├── backup/code/          # 舊版代碼備份（淨保留一代）
└── result.json           # updater 寫；最後一次更新結果（UI 顯示）
```

**Updater 執行步驟（root，嚴格依序 —— 可失敗嘅步盡量排喺換代碼之前）：**

| # | 步驟 | 失敗時 |
|---|---|---|
| 1 | 讀 trigger → 自帶公鑰**重驗簽名** + 重算 payload hash + 版本門檻 | abort，server 冇停過，零影響 |
| 2 | 磁碟空間檢查 | 同上 |
| 3 | `launchctl bootout` 停 server | abort + 重啟 server |
| 4 | 備份現有代碼 → `backup/code/`（exclude：`data/` `config/` `.env` `venv/` `.git/`） | abort + 重啟舊版 |
| 5 | 有 wheels：`venv/bin/pip install --no-index --find-links wheels/ -r <新requirements.txt>` | abort + 重啟舊版（代碼未掂過，新依賴裝咗但舊代碼唔 import，無害；此排序令 venv 唔使回滾） |
| 6 | 換代碼：rsync staged → `/opt/motitle`（同一 exclude 清單 + `--delete`） | → 回滾 |
| 7 | 寫新 `VERSION`、`launchctl bootstrap` 起 server | → 回滾 |
| 8 | Poll `/api/ready` + 驗 `/api/health` version == 目標（最多 5 分鐘 —— 首 boot 要 load model） | → 回滾 |
| 9 | 成功：寫 `result.json {ok, from, to}`，清 staged + trigger，**保留 backup 一代** | — |

**回滾路徑（步驟 6–8 失敗）**：bootout → rsync `backup/code/` 還原 → bootstrap → poll `/api/ready` → 寫 `result.json {failed, rolled_back:true, error, step}`。連還原都起唔返（理論上唔應該 —— 備份就係頭先行緊嗰套）：寫 `{rolled_back:false}` + 完整 log 落 `data/logs/updater.log`，等 vendor 接手（唯一需要人手嘅情境）。

**斷電/中斷復原**：每步開始前寫 `journal.json`。updater 每次被觸發先睇 journal —— 發現上次死喺步驟 6–8 中間（代碼半換），唔理 trigger 先行回滾再報 fail。Journal 令 updater **冪等**：同一 trigger 行兩次唔疊加傷害。

**互鎖**：Flask 喺 `apply` 前檢查冇 render/rerun/transcribe job 行緊（有就 409）；trigger 寫咗後 status 變 `applying`，UI 鎖死所有更新操作。

**前端體驗**：撳「執行更新」→ confirm（「服務將重啟約 X 分鐘」）→ UI 入「更新中」，poll `/api/health`（斷線屬預期，靜默 retry）→ server 返生後比對 version + 讀 `/api/update/status` → 顯示「✓ 已更新到 4.1.0」或「✗ 更新失敗已自動還原：<error>」。

---

## 5. API、admin UI、安裝鏈

**三條新 route（admin-only + audit log，跟現有 `/api/admin/*` 模式）：**

| Route | 行為 |
|---|---|
| `POST /api/update/upload` | multipart 上載 `.mtupdate` → `package.py` 驗簽+驗版本門檻+安全解壓到 `staged/` → 回 manifest 摘要；驗唔過回 400 + error code（`bad_signature` / `version_too_old` / `min_version_unmet` / `corrupt`）。Audit：`update.upload` |
| `POST /api/update/apply` | 檢查有 staged 包 + 冇 job 行緊 → atomic 寫 trigger（`O_EXCL`）→ 202。Audit：`update.apply` |
| `GET /api/update/status` | `{current_version, staged, state: idle\|staged\|applying, last_result, updater_installed}` —— UI 單一數據源 |

**License gate 例外**：`/api/update*` 加入 `gate.py` allowlist（license 鎖咗都用到）。理由：包已 Ed25519 簽名 + admin auth 雙重把關；「license 過期客戶要裝更新先修到 licensing bug」係真實支援場景，唔可以畀 license 鎖死自救通道。

**Admin UI**（`user.html` 加「系統更新」nav tab，跟 Beta 模式 pane 模式）：顯示目前版本 + 最後更新結果 → 上載包 → 驗證後顯示「已就緒：<version> + notes + [執行更新] [取消]」→ 執行中換全 pane「更新中…服務重啟約 5 分鐘，請勿關機」+ spinner。

**安裝鏈（updater daemon 落地）：**

1. `motitle-service.sh install` 加第三個 daemon：render `com.motitle.updater.plist.template` → 複製 `motitle-updater.sh` + 驗簽 helper + **當刻 update 公鑰**去 `/Library/Application Support/MoTitle/updater/`（root-owned，目錄 0755 / script 0700）→ bootstrap。`uninstall`/`status` 同步涵蓋。
2. `setup-mac.sh` 照舊 call `motitle-service.sh install` —— 新裝客戶機自動齊。
3. **現有客戶機（雞先蛋先）**：人手跑一次 `sudo packaging/macos/motitle-service.sh install`（runbook 寫明），之後所有更新行新機制。
4. **更新 updater 自己**：更新包換 `/opt/motitle` source 後唔會自動同步去 `/Library/Application Support/`（刻意 —— 保持 updater 穩定）。真要升 updater 時 release notes 註明跑多次 `install`。

---

## 6. 錯誤處理矩陣

| 情境 | 處理 |
|---|---|
| 上載非 tar / 缺 manifest / 簽名錯 | 400 + error code，staged 唔落地（解壓去 temp，全驗過先 move） |
| 上載超大 / 磁碟唔夠 | 413 / 507 + 人話 message |
| tar 內有 `..` / absolute / symlink 出界 | 整個包拒絕（唔係跳過該 member），audit `update.upload_rejected` |
| Apply 時有 job 行緊 | 409「請等待現有任務完成」 |
| 連撳兩次 apply / 重複 trigger | atomic `O_EXCL`，第二次 409 |
| Updater 行到一半斷電 | journal 復原 —— 下次觸發先回滾再報 fail |
| 健康檢查 timeout（模型 load 慢） | 5 分鐘上限判 fail；result.json 記低 fail 喺邊步 |
| 回滾都失敗 | `{rolled_back:false}` + `updater.log` 全量 log，UI 顯示「請聯絡供應商」 |
| 客戶機未裝 updater daemon | `GET /api/update/status` 偵測（檢查 plist 存在）→ UI 提示「需先執行一次安裝指令」而唔係上載咗先死 |

---

## 7. 測試策略

- **單元測試（佔大頭，純邏輯零依賴）**：
  - `tests/test_update_package.py` —— manifest 驗證、簽名驗證（test keypair）、版本比較全 edge cases、tar 安全（惡意 tar fixtures：traversal/absolute/symlink）
  - `tests/test_update_state.py` —— staging/trigger/result 生命週期、atomic trigger、journal 狀態機（`tmp_path`）
- **API 測試**：`tests/test_api_update.py` —— 三條 route happy path + 全部 4xx 分支（跟現有 `R5_AUTH_BYPASS` / `R5_LICENSE_BYPASS` conftest 模式）
- **Updater script**：核心邏輯抽落 `--dry-run` 模式（印出將執行動作唔真行），shell 層用 pytest subprocess 驗 dry-run 輸出；真實 E2E 喺第二部 Mac 行一次完整「上載→更新→驗證→上載壞包→驗證自動回滾」（runbook 記錄）
- **唔使 Validation-First tracker** —— 此 feature 唔掂 ASR/MT

---

## 8. 文檔更新清單（完工 gate）

- `CLAUDE.md`：新 module、3 條 route、updater daemon 架構
- `README.md`（繁中）：管理員「系統更新」操作指南
- `docs/deployment/macos-server.md`：updater daemon 安裝、現有客戶機 retrofit 一次性指令、回滾失敗 vendor 救援步驟
- `docs/PRD.md`：feature status
- Vendor 私有筆記：`build_update.py` 砌包流程 + update keypair 管理（同 licensing keypair 筆記放埋）

---

## 9. 刻意唔做（YAGNI，全部留 hook）

- 線上自動檢查更新（manifest 格式已兼容，加 feed URL fetch 即得）
- Delta / 增量更新包（包通常幾十 MB，唔值複雜度）
- 多代備份 / 任選版本回滾（一代備份夠自動回滾用）
- Ollama 模型更新自動化（runbook 文檔化人手流程）
- Homebrew 系統依賴自動更新（「大版本」人手流程）

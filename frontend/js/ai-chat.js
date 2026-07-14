/* ============================================================
   MoTitle — AI 助手聊天窗（AIChat）
   浮動可拖非阻擋窗（find-replace.js 同款 pattern）：用戶自然語言指令
   → POST /ai-chat/parse（每 turn 1 個 LLM call）→ 卡片預覽 → 剔選套用
   （POST /ai-chat/apply，server-side 衝突檢查）→ session 內還原。
   Spec: docs/superpowers/specs/2026-07-14-ai-chat-window-design.md
   依賴：window.AIChatPage（每頁 inline 定義嘅 adapter）、escapeHtml、
   showToast、API_BASE。mount 做 document.body 直屬子節點 —
   index renderAll innerHTML 重建殺唔死。UI 零引擎/型號名。
   ============================================================ */
(function () {
  'use strict';

  let built = false;
  let open = false;
  let drag = null;
  let turnSeq = 0;            // stale-response identity guard
  let sending = false;
  let boundFileId = null;     // 對話綁定嘅檔案；轉檔 → divider + 舊卡作廢
  let lastTurnSummary = '';   // 機械生成 ≤300 字，下 turn 帶去 /parse
  let turns = [];             // [{who:'user'|'ai'|'sys', text, card?}] card 見 Task 10

  const CSS = `
  .ac-pop { position:fixed; top:72px; right:24px; width:420px; max-width:92vw;
    background:var(--surface, #16161f); border:1px solid var(--border-strong, #3c3c58);
    border-radius:14px; box-shadow:0 24px 70px rgba(0,0,0,.65); color:var(--text, #dcdce6);
    font-size:13px; display:flex; flex-direction:column; max-height:70vh; z-index:2600; }
  .ac-pop[hidden] { display:none; }
  .ac-head { display:flex; align-items:center; gap:10px; padding:12px 16px;
    border-bottom:1px solid var(--border, #26263a); cursor:grab; user-select:none; }
  .ac-head .t { font-weight:700; font-size:13.5px; }
  .ac-head .drag { color:var(--text-dim, #4a4a62); font-size:13px; letter-spacing:2px; }
  .ac-head .x { margin-left:auto; color:var(--text-mid, #8a8aa0); border:1px solid var(--border, #30304a);
    border-radius:6px; width:24px; height:24px; display:grid; place-items:center; cursor:pointer;
    background:none; font-size:12px; }
  .ac-head .x:hover { color:#fff; border-color:var(--accent, #6c63ff); }
  .ac-list { overflow-y:auto; flex:1; min-height:120px; padding:12px 14px;
    display:flex; flex-direction:column; gap:10px; }
  .ac-msg { max-width:88%; padding:8px 12px; border-radius:11px; line-height:1.6; word-break:break-word; }
  .ac-msg.user { align-self:flex-end; background:rgba(108,99,255,.16); color:#d6d2ff; }
  .ac-msg.ai { align-self:flex-start; background:rgba(255,255,255,.05); }
  .ac-msg.sys { align-self:center; color:var(--text-dim, #6a6a85); font-size:11px;
    background:none; padding:2px 0; }
  .ac-msg.think .dots::after { content:'…'; animation:acDots 1.2s infinite; }
  @keyframes acDots { 0%{content:'.'} 33%{content:'..'} 66%{content:'…'} }
  .ac-inrow { display:flex; gap:8px; padding:10px 14px 12px; border-top:1px solid var(--border, #26263a); }
  .ac-inrow textarea { flex:1; background:var(--bg, #0d0d14); border:1px solid var(--border-strong, #3a3a55);
    border-radius:8px; color:var(--text, #f0f0f6); font-size:13px; font-family:inherit;
    padding:8px 10px; resize:none; height:38px; min-width:0; }
  .ac-inrow textarea:focus { outline:none; border-color:var(--accent, #6c63ff); }
  .ac-send { background:rgba(108,99,255,.13); border:1px solid rgba(108,99,255,.47); color:#c4bdff;
    border-radius:8px; padding:0 16px; font-size:12.5px; font-weight:600; cursor:pointer; font-family:inherit; }
  .ac-send[disabled] { opacity:.4; pointer-events:none; }
  .ac-hint { padding:0 16px 10px; font-size:10.5px; color:var(--text-dim, #6a6a85); }
  /* Task 10 卡片 CSS 加喺呢度之下 */
  `;

  function P() { return window.AIChatPage || null; }
  function esc(s) { return (typeof escapeHtml === 'function') ? escapeHtml(s || '') : String(s || ''); }
  function toast(m, k) { if (typeof showToast === 'function') showToast(m, k || 'info'); }
  function api() { return (typeof API_BASE !== 'undefined') ? API_BASE : ''; }

  function build() {
    if (built) return;
    built = true;
    const st = document.createElement('style');
    st.textContent = CSS;
    document.head.appendChild(st);
    const el = document.createElement('div');
    el.className = 'ac-pop';
    el.id = 'acPop';
    el.hidden = true;
    el.innerHTML = `
      <div class="ac-head" id="acHead">
        <span class="t">✦ AI 助手</span><span class="drag">⠿</span>
        <button class="x" id="acClose" aria-label="關閉">✕</button>
      </div>
      <div class="ac-list" id="acList"></div>
      <div class="ac-inrow">
        <textarea id="acInput" maxlength="500"
          placeholder="例：把所有「晨操」改成「早操」"></textarea>
        <button class="ac-send" id="acSend">傳送</button>
      </div>
      <div class="ac-hint">支援批量取代／指定段落改寫；套用前一定會先預覽。Esc 關閉。</div>`;
    document.body.appendChild(el);

    document.getElementById('acClose').addEventListener('click', close);
    document.getElementById('acSend').addEventListener('click', send);
    document.getElementById('acInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });

    const head = document.getElementById('acHead');
    head.addEventListener('mousedown', (e) => {
      if (e.target.closest('#acClose')) return;
      const r = el.getBoundingClientRect();
      drag = { dx: e.clientX - r.left, dy: e.clientY - r.top };
      e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
      if (!drag) return;
      el.style.left = Math.max(8, Math.min(window.innerWidth - 60, e.clientX - drag.dx)) + 'px';
      el.style.top = Math.max(8, Math.min(window.innerHeight - 60, e.clientY - drag.dy)) + 'px';
      el.style.right = 'auto';
    });
    document.addEventListener('mouseup', () => { drag = null; });
  }

  function pushTurn(t) { turns.push(t); renderList(); }

  function renderList() {
    const list = document.getElementById('acList');
    if (!list) return;
    list.innerHTML = turns.map((t, ti) => {
      if (t.card) return renderCard(t.card, ti);           // Task 10
      const cls = t.who === 'user' ? 'user' : (t.who === 'sys' ? 'sys' : 'ai');
      const think = t.thinking ? ' think' : '';
      return `<div class="ac-msg ${cls}${think}">${esc(t.text)}${t.thinking ? '<span class="dots"></span>' : ''}</div>`;
    }).join('');
    list.scrollTop = list.scrollHeight;
  }

  /* Task 10: cards — renderCard / bindCardEvents / rescanCard */
  function renderCard() { return ''; }

  async function send() {
    const p = P();
    if (!p || sending) return;
    const input = document.getElementById('acInput');
    const msg = (input.value || '').trim();
    if (!msg) return;
    const fid = p.fileId();
    if (!fid) { toast('請先揀一個檔案', 'warning'); return; }
    if (!p.isOutputLang()) {
      pushTurn({ who: 'user', text: msg });
      pushTurn({ who: 'ai', text: '呢個檔案類型唔支援 AI 修改，可以喺校對頁人手編輯。' });
      input.value = '';
      return;
    }
    if (fid !== boundFileId) {
      boundFileId = fid;
      pushTurn({ who: 'sys', text: '— 已綁定目前檔案 —' });
      lastTurnSummary = '';
    }
    sending = true;
    const myTurn = ++turnSeq;
    pushTurn({ who: 'user', text: msg });
    input.value = '';
    const thinkT = { who: 'ai', text: '理解緊你嘅指令', thinking: true };
    pushTurn(thinkT);
    document.getElementById('acSend').disabled = true;
    try {
      const body = { message: msg, last_turn_summary: lastTurnSummary };
      const cur = p.cursorSegNo();
      if (cur) body.cursor_seg_no = cur;
      const r = await fetch(`${api()}/api/files/${fid}/ai-chat/parse`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (myTurn !== turnSeq || boundFileId !== p.fileId()) return;  // stale 棄置
      turns = turns.filter(t => t !== thinkT);
      if (r.status === 422) {
        pushTurn({ who: 'ai', text: data.reply || 'AI 一時冇明白，請講具體啲，例如：把所有「晨操」改成「早操」' });
        return;
      }
      if (!r.ok) {
        pushTurn({ who: 'ai', text: data.error || 'AI 服務暫時冇回應，請再試' });
        return;
      }
      handleParsed(data, msg);                             // Task 10 接手卡片
    } catch (e) {
      if (myTurn !== turnSeq) return;
      turns = turns.filter(t => t !== thinkT);
      pushTurn({ who: 'ai', text: 'AI 服務暫時冇回應，請再試' });
    } finally {
      sending = false;
      const btn = document.getElementById('acSend');
      if (btn) btn.disabled = false;
      renderList();
    }
  }

  /* Task 10 會取代呢個 stub：處理 ops → 卡片／澄清／唔支援 */
  function handleParsed(data) {
    pushTurn({ who: 'ai', text: data.reply || '（已解析）' });
  }

  function openPop() {
    if (!P()) { toast('AI 助手載入中…', 'info'); return; }
    build();
    document.getElementById('acPop').hidden = false;
    open = true;
    const fid = P().fileId();
    if (fid && boundFileId && fid !== boundFileId) {
      boundFileId = fid;
      pushTurn({ who: 'sys', text: '— 已切換檔案，之前嘅建議唔再適用 —' });
    }
    document.getElementById('acInput').focus();
    renderList();
  }
  function close() {
    if (!built) return;
    document.getElementById('acPop').hidden = true;
    open = false;                                          // 對話保留，重開恢復
  }
  function isOpen() { return open; }

  window.AIChat = { open: openPop, close, isOpen };
})();

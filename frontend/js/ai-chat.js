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
  let turnSummaries = [];     // rolling 記憶，最新喺前，最多 3 個（每個 ≤120 字原始摘要，未加「上一輪：」等 label）
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
  .ac-head .x { color:var(--text-mid, #8a8aa0); border:1px solid var(--border, #30304a);
    border-radius:6px; width:24px; height:24px; display:grid; place-items:center; cursor:pointer;
    background:none; font-size:12px; }
  .ac-head .nw { margin-left:auto; }
  .ac-head .x:not(.nw) { margin-left:6px; }
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
  .ac-card { align-self:stretch; border:1px solid var(--border-strong, #3a3a55);
    border-radius:11px; background:var(--bg, #0d0d14); overflow:hidden; }
  .ac-card.stale { opacity:.55; }
  .ac-ch { padding:9px 12px; font-weight:700; font-size:12.5px;
    border-bottom:1px solid var(--border, #26263a); display:flex; gap:8px; align-items:center; }
  .ac-ch .n { color:var(--accent-2, #8f88ff); }
  .ac-warn { padding:6px 12px; font-size:11px; color:#f0c66a;
    background:rgba(240,198,106,.07); border-bottom:1px solid var(--border, #26263a); }
  .ac-rows { max-height:240px; overflow-y:auto; }
  .ac-row { display:flex; gap:9px; padding:8px 12px; border-top:1px solid var(--border, #1f1f2e);
    align-items:flex-start; font-size:12px; }
  .ac-row:first-child { border-top:none; }
  .ac-row .meta { min-width:64px; cursor:pointer; }
  .ac-row .meta .seg { font-weight:700; }
  .ac-row .meta .tc { font-size:9.5px; color:var(--text-dim, #6a6a85); display:block;
    font-family:var(--font-mono, monospace); }
  .ac-row .meta .ap { font-size:9px; padding:1px 6px; border-radius:4px;
    background:rgba(34,197,94,.13); color:#8fefad; }
  .ac-row .diff { flex:1; line-height:1.55; word-break:break-word; }
  .ac-row .diff del { background:rgba(255,99,99,.14); color:#f2a1a1; text-decoration:line-through;
    border-radius:3px; padding:0 3px; }
  .ac-row .diff ins { background:rgba(34,197,94,.17); color:#8fefad; text-decoration:none;
    border-radius:3px; padding:0 3px; }
  .ac-row .st { min-width:48px; text-align:right; font-size:10.5px; }
  .ac-row .st .ok { color:#8fefad; } .ac-row .st .er { color:#f2a1a1; }
  .ac-row .st .undo { color:var(--accent-2, #8f88ff); cursor:pointer; text-decoration:underline; }
  .ac-cf { display:flex; align-items:center; gap:10px; padding:9px 12px;
    border-top:1px solid var(--border, #26263a); font-size:11.5px; flex-wrap:wrap; }
  .ac-cf label { display:flex; gap:5px; align-items:center; cursor:pointer;
    color:var(--text-mid, #9a9ab2); }
  .ac-b { border:1px solid rgba(108,99,255,.47); background:rgba(108,99,255,.13); color:#c4bdff;
    border-radius:7px; padding:6px 13px; font-size:11.5px; font-weight:600; cursor:pointer;
    font-family:inherit; }
  .ac-b[disabled] { opacity:.4; pointer-events:none; }
  .ac-b.ghost { background:none; border-color:var(--border-strong, #3a3a55);
    color:var(--text-mid, #9a9ab2); font-weight:400; }
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
        <button class="x nw" id="acNew" title="新對話" aria-label="新對話">＋</button>
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
    document.getElementById('acNew').addEventListener('click', newChat);
    document.getElementById('acSend').addEventListener('click', send);
    document.getElementById('acInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });

    const head = document.getElementById('acHead');
    head.addEventListener('mousedown', (e) => {
      if (e.target.closest('.ac-head .x')) return;   // 掣（新對話／關閉）唔拖窗
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

    document.getElementById('acList').addEventListener('click', (e) => {
      const cardEl = e.target.closest('.ac-card');
      if (!cardEl) return;
      const card = (turns[Number(cardEl.dataset.card)] || {}).card;
      if (!card) return;
      const ck = e.target.closest('[data-ck]');
      if (ck) { card.checks.set(Number(ck.dataset.ck), ck.checked); renderList(); return; }
      const apv = e.target.closest('[data-apv]');
      if (apv) { card.approveAfter = apv.checked; return; }
      const jp = e.target.closest('[data-jp]');
      if (jp) { P().jump(card.items[Number(jp.dataset.jp)].idx); return; }
      if (e.target.closest('[data-rescan]')) { rescanCard(card); return; }
      if (e.target.closest('[data-apply]')) { applySelected(card); return; }       // Task 11
      const un = e.target.closest('[data-un]');
      if (un) { undoRow(card, Number(un.dataset.un)); return; }                    // Task 11
    });
  }

  function pushTurn(t) { turns.push(t); renderList(); }

  function newChat() {
    // 新對話：清空對話 + 記憶，bump turnSeq 令任何未回應嘅舊 turn 作廢；boundFileId 唔郁（仍然係同一檔案）
    turns = [];
    turnSummaries = [];
    turnSeq++;
    renderList();
    pushTurn({ who: 'sys', text: '— 新對話 —' });
    const input = document.getElementById('acInput');
    if (input) input.focus();
  }

  function renderList() {
    const list = document.getElementById('acList');
    if (!list) return;
    // scroll 保持：非貼底時唔好搶 scroll；卡片內行清單逐張還原
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 8;
    const prevScroll = list.scrollTop;
    const rowScrolls = new Map();
    list.querySelectorAll('.ac-card').forEach((c) => {
      const rows = c.querySelector('.ac-rows');
      if (rows) rowScrolls.set(c.dataset.card, rows.scrollTop);
    });
    list.innerHTML = turns.map((t, ti) => {
      if (t.card) return renderCard(t.card, ti);           // Task 10
      const cls = t.who === 'user' ? 'user' : (t.who === 'sys' ? 'sys' : 'ai');
      const think = t.thinking ? ' think' : '';
      return `<div class="ac-msg ${cls}${think}">${esc(t.text)}${t.thinking ? '<span class="dots"></span>' : ''}</div>`;
    }).join('');
    list.querySelectorAll('.ac-card').forEach((c) => {
      const rows = c.querySelector('.ac-rows');
      if (rows && rowScrolls.has(c.dataset.card)) rows.scrollTop = rowScrolls.get(c.dataset.card);
    });
    list.scrollTop = atBottom ? list.scrollHeight : prevScroll;
  }

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
      turnSummaries = [];
    }
    sending = true;
    const myTurn = ++turnSeq;
    pushTurn({ who: 'user', text: msg });
    input.value = '';
    const thinkT = { who: 'ai', text: '理解緊你嘅指令', thinking: true };
    pushTurn(thinkT);
    document.getElementById('acSend').disabled = true;
    try {
      const body = { message: msg, last_turn_summary: composeMemory() };
      const cur = p.cursorSegNo();
      if (cur) body.cursor_seg_no = cur;
      const r = await fetch(`${api()}/api/files/${fid}/ai-chat/parse`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      turns = turns.filter(t => t !== thinkT);
      if (myTurn !== turnSeq || boundFileId !== p.fileId()) return;  // stale 棄置
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
      turns = turns.filter(t => t !== thinkT);
      if (myTurn !== turnSeq || boundFileId !== p.fileId()) return;
      pushTurn({ who: 'ai', text: 'AI 服務暫時冇回應，請再試' });
    } finally {
      sending = false;
      const btn = document.getElementById('acSend');
      if (btn) btn.disabled = false;
      renderList();
    }
  }

  /* Task 10: cards — diff / handleParsed / renderCard / rescanCard */
  function diffHtml(item) {
    // 逐字 diff 太重 — 直接 del before / ins after（match 位已由 server 換好）
    return `<del>${esc(item.before)}</del><br><ins>${esc(item.after !== undefined ? item.after : item.before)}</ins>`;
  }

  function handleParsed(data, userMsg) {
    const p = P();
    const editOps = (data.ops || []).filter(o => o.op !== 'none');
    const noneOp = (data.ops || []).find(o => o.op === 'none');
    pushTurn({ who: 'ai', text: data.reply || '收到' });
    if (noneOp && !editOps.length) {
      if (noneOp.kind === 'clarify' && noneOp.question) {
        pushTurn({ who: 'ai', text: noneOp.question });
      } else if (noneOp.kind === 'unsupported') {
        pushTurn({ who: 'ai', text: p.hasGrid
          ? '呢樣嘢我幫唔到手 — 我淨係可以修改字幕文字（批量取代／指定段落改寫）。'
          : '呢樣嘢我幫唔到手 — 我淨係可以修改字幕文字。逐段檢視可以去校對頁。' });
      }
      turnSummaries = [];
      return;
    }
    if (!data.proposal || !data.proposal.items.length) {
      pushTurn({ who: 'ai', text: '搵唔到符合嘅段落 — 可能啲字幕入面冇呢個字詞。' });
      turnSummaries.unshift(mkSummary(editOps, 0, '未套用'));
      turnSummaries = turnSummaries.slice(0, 3);
      return;
    }
    const card = {
      ops: editOps, items: data.proposal.items, truncated: data.proposal.truncated,
      totals: data.proposal.totals, gridLen: data.grid_len, fileId: boundFileId,
      rerunActive: data.rerun_active, renderActive: data.render_active,
      checks: new Map(), applied: new Map(), suggestions: new Map(),
      stale: false, applying: false, approveAfter: false, sugGen: 0,
    };
    card.items.forEach((it, i) => card.checks.set(i, !it.approved));  // 已批核預設唔剔
    pushTurn({ who: 'ai', card });
    turnSummaries.unshift(mkSummary(editOps, card.items.length, '未套用'));
    turnSummaries = turnSummaries.slice(0, 3);
    if (typeof genSuggestions === 'function') genSuggestions(card);   // Task 11
  }

  function mkSummary(ops, n, state) {
    // 原始摘要（未加「上一輪：」等 recency label — composeMemory() 先加）
    if (!ops.length) return '';
    const o = ops[0];
    const s = o.op === 'replace_term'
      ? `把「${o.from}」改成「${o.to}」，命中 ${n} 段`
      : `改寫第 ${o.seg_no} 段（${o.lang_role === 'second' ? '第二' : '第一'}語言）`;
    return `${s}，${state}`.slice(0, 120);
  }

  function composeMemory() {
    // validated safe format（2026-07-14 addendum）：key 唔可以改（「上一輪」）；
    // 深度由 value 內嘅 recency label 表達，一律前端組、server 只做整條 clamp ≤300 字。
    const labels = ['上一輪：', '前一輪：', '再前一輪：'];
    return turnSummaries.slice(0, 3).map((s, i) => labels[i] + s).join('；').slice(0, 300);
  }

  function cardStale(card) {
    const p = P();
    if (card.fileId !== p.fileId()) return true;
    if (p.hasGrid && p.cueCount() !== card.gridLen) return true;      // split/merge/rerun
    return card.stale;
  }

  function renderCard(card, ti) {
    const stale = cardStale(card);
    const sel = [...card.checks.values()].filter(Boolean).length;
    const delWarn = card.ops.some(o => o.op === 'replace_term' && o.to === '')
      ? '<div class="ac-warn">此指令會刪除字詞 — 請留意預覽（紅色刪除線＝刪走）</div>' : '';
    const warn = stale
      ? '<div class="ac-warn">段落已變動 — 請撳「重新掃描」更新預覽</div>'
      : (card.rerunActive ? '<div class="ac-warn">AI Rerun 進行中 — 暫時唔可以套用</div>'
      : (card.renderActive ? '<div class="ac-warn">渲染進行中 — 本次修改唔會反映喺該渲染</div>' : ''));
    const rows = card.items.map((it, i) => {
      const ap = card.applied.get(i);
      const sug = card.suggestions.get(i);
      let st;
      if (ap && ap.state === 'ok') st = `<span class="ok">✓</span> <span class="undo" data-un="${i}">還原</span>`;
      else if (ap && ap.state === 'err') st = `<span class="er" title="${esc(ap.error)}">✗</span>`;
      else if (ap && ap.state === 'busy') st = '…';
      else if (it.kind === 'ai_rewrite' && sug && sug.text === undefined) st = `<span class="er" title="${esc(sug.error || '')}">✗ 生成失敗</span>`;
      else if (it.kind === 'ai_rewrite' && !sug) st = '生成中…';
      else st = `<input type="checkbox" data-ck="${i}" ${card.checks.get(i) ? 'checked' : ''} ${stale || card.applying ? 'disabled' : ''}>`;
      const shown = it.kind === 'ai_rewrite'
        ? { ...it, after: (sug && sug.text) !== undefined ? sug.text : undefined }
        : it;
      const diff = shown.after === undefined
        ? (it.kind === 'ai_rewrite' && sug && sug.text === undefined
          ? `<del>${esc(it.before)}</del><br><span style="color:var(--text-dim)">（生成失敗）</span>`
          : `<del>${esc(it.before)}</del><br><span style="color:var(--text-dim)">（AI 生成中…）</span>`)
        : diffHtml(shown);
      return `<div class="ac-row">
        <div class="meta" data-jp="${i}"><span class="seg">#${it.idx + 1}</span>
          <span class="tc">${(it.start != null) ? Number(it.start).toFixed(1) + 's' : ''}</span>
          ${it.approved ? '<span class="ap">已批核</span>' : ''}</div>
        <div class="diff">${diff}</div><div class="st">${st}</div></div>`;
    }).join('');
    return `<div class="ac-card ${stale ? 'stale' : ''}" data-card="${ti}">
      <div class="ac-ch">建議修改 <span class="n">${card.items.length} 段</span>
        ${card.totals.approved ? `<span style="font-weight:400;color:var(--text-dim)">（${card.totals.approved} 段已批核，預設唔剔）</span>` : ''}</div>
      ${delWarn}
      ${card.truncated ? '<div class="ac-warn">命中超過 200 段，請縮窄範圍</div>' : ''}${warn}
      <div class="ac-rows">${rows}</div>
      <div class="ac-cf">
        <label><input type="checkbox" data-apv ${card.approveAfter ? 'checked' : ''} ${card.applying ? 'disabled' : ''}> 套用後批核</label>
        <span style="flex:1"></span>
        <button class="ac-b ghost" data-rescan ${card.applying || card.rescanning ? 'disabled' : ''}>重新掃描</button>
        <button class="ac-b" data-apply ${stale || card.applying || card.rescanning || card.rerunActive || !sel ? 'disabled' : ''}>套用選中 (${sel})</button>
      </div></div>`;
  }

  async function rescanCard(card) {
    const p = P();
    const fid = p.fileId();
    if (!fid) return;
    if (card.rescanning) return;
    card.rescanning = true;
    try {
      const r = await fetch(`${api()}/api/files/${fid}/ai-chat/expand`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ops: card.ops }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) { toast(data.error || '重新掃描失敗', 'error'); return; }
      card.items = data.proposal.items;
      card.truncated = data.proposal.truncated;
      card.totals = data.proposal.totals;
      card.gridLen = data.grid_len;
      card.fileId = fid;
      card.rerunActive = data.rerun_active;
      card.renderActive = data.render_active;
      card.stale = false;
      card.checks = new Map();
      card.applied = new Map();
      card.suggestions = new Map();
      card.sugGen = (card.sugGen || 0) + 1;   // invalidate any still-queued genSuggestions chain entries
      card.items.forEach((it, i) => card.checks.set(i, !it.approved));
      if (typeof genSuggestions === 'function') genSuggestions(card);
    } catch (e) { toast('重新掃描失敗', 'error'); }
    finally { card.rescanning = false; renderList(); }
  }

  /* Task 11: apply driver + session 還原 + 重寫兩段式 */
  let rewriteChain = Promise.resolve();   // 單一本地 LLM — 生成串行，永不並行

  function genSuggestions(card) {
    // 重寫兩段式第一步：逐個 ai_rewrite item 經現有 /ai-edit 生成（已驗證 prompt），
    // 卡片顯示實際生成文字先准套用（「預覽先」防線 — spec §2）。
    const myGen = card.sugGen;
    card.items.forEach((it, i) => {
      if (it.kind !== 'ai_rewrite' || card.suggestions.has(i)) return;
      rewriteChain = rewriteChain.then(async () => {
        if (card.sugGen !== myGen || cardStale(card)) return;
        try {
          const r = await fetch(`${api()}/api/files/${card.fileId}/ai-edit`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pos: it.idx, role: it.lang_role,
                                   instruction: it.instruction }),
          });
          const data = await r.json().catch(() => ({}));
          if (!r.ok) {
            card.suggestions.set(i, { text: undefined, error: data.error || `HTTP ${r.status}` });
            card.checks.set(i, false);
          } else {
            card.suggestions.set(i, { text: data.text });
          }
        } catch (e) {
          card.suggestions.set(i, { text: undefined, error: 'AI 服務暫時冇回應' });
          card.checks.set(i, false);
        }
        renderList();
      });
    });
  }

  function itemAfter(card, it, i) {
    if (it.kind !== 'ai_rewrite') return it.after;
    const sug = card.suggestions.get(i);
    return sug ? sug.text : undefined;
  }

  async function applySelected(card) {
    const p = P();
    if (card.applying || cardStale(card)) return;
    if (card.rescanning) return;
    let todo = card.items
      .map((it, i) => ({ it, i }))
      .filter(({ it, i }) => card.checks.get(i) && !card.applied.has(i)
                             && itemAfter(card, it, i) !== undefined);
    if (!todo.length) return;
    // 同一 (idx, lang) 喺同一批入面撞埋（例：機械取代 + AI 改寫命中同一 cue）—
    // server 一寫一衝突，淨送第一項，其餘直接標錯，唔好送去撞。
    const seenKeys = new Set();
    const rest = [];
    todo.forEach(({ it, i }) => {
      const key = `${it.idx}:${it.lang}`;
      if (seenKeys.has(key)) {
        card.applied.set(i, { state: 'err', error: '同一段同一語言軌一次只可以套用一項 — 請重新掃描後再套用' });
      } else {
        seenKeys.add(key);
        rest.push({ it, i });
      }
    });
    todo = rest;
    if (!todo.length) { renderList(); return; }
    card.applying = true;
    todo.forEach(({ i }) => card.applied.set(i, { state: 'busy' }));
    renderList();
    try {
      const items = todo.map(({ it, i }) => ({
        idx: it.idx, lang: it.lang, after: itemAfter(card, it, i),
        expected_text: it.expected_text, start: it.start, end: it.end,
      }));
      const r = await fetch(`${api()}/api/files/${card.fileId}/ai-chat/apply`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items, approve: card.approveAfter }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.status === 409) {
        todo.forEach(({ i }) => card.applied.delete(i));
        toast(data.error || 'AI Rerun 進行中，無法修改段落', 'warning');
        card.rerunActive = true;
        return;
      }
      if (!r.ok) {
        todo.forEach(({ i }) => card.applied.delete(i));
        toast(data.error || `套用失敗（HTTP ${r.status}）`, 'error');
        return;
      }
      // server 回應用 (idx, lang) 識別行；上面嘅同鍵防護保證同一批入面
      // 呢個 (idx, lang) 最多得一個 in-flight item，所以呢個 lookup 唔會撞誤配對。
      const okSet = new Set((data.applied || []).map(a => `${a.idx}:${a.lang}`));
      const prevBy = new Map((data.applied || []).map(a => [`${a.idx}:${a.lang}`, a.prev_status]));
      const failBy = new Map((data.failed || []).map(f => [`${f.idx}:${f.lang}`, f.error]));
      const skipSet = new Set((data.skipped || []).map(s => `${s.idx}:${s.lang}`));
      todo.forEach(({ it, i }) => {
        const k = `${it.idx}:${it.lang}`;
        if (okSet.has(k) || skipSet.has(k)) {
          card.applied.set(i, { state: 'ok', before: it.before,
                                after: itemAfter(card, it, i),
                                prevStatus: prevBy.get(k) || { row: 'pending', by_lang: 'pending' } });
        } else {
          card.applied.set(i, { state: 'err', error: failBy.get(k) || '未知錯誤' });
        }
      });
      const nOk = (data.applied || []).length, nSkip = (data.skipped || []).length,
            nFail = (data.failed || []).length;
      toast(`已套用 ${nOk} 項${nSkip ? `，略過 ${nSkip} 項` : ''}${nFail ? `，${nFail} 項失敗` : ''}`,
            nFail ? 'warning' : 'success');
      turnSummaries.unshift(mkSummary(card.ops, card.items.length, `已套用 ${nOk} 項`));
      turnSummaries = turnSummaries.slice(0, 3);
      try { await p.refresh(); } catch (e) { toast('列表刷新失敗，請手動重新整理', 'warning'); }
    } catch (e) {
      todo.forEach(({ i }) => { if (card.applied.get(i) &&
        card.applied.get(i).state === 'busy') card.applied.delete(i); });
      toast('套用失敗，請再試', 'error');
    } finally {
      card.applying = false;
      renderList();
    }
  }

  async function undoRow(card, i) {
    const p = P();
    const it = card.items[i];
    const ap = card.applied.get(i);
    if (!ap || ap.state !== 'ok' || card.applying) return;
    card.applied.set(i, { ...ap, state: 'busy' });
    renderList();
    try {
      // 還原經同一條衝突檢查路：expected_text = 已套用文字（之後有人手改過
      // → failed「已被再次修改」，唔會 clobber）；status_after 連批核狀態一齊還原。
      const r = await fetch(`${api()}/api/files/${card.fileId}/ai-chat/apply`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: [{ idx: it.idx, lang: it.lang, after: ap.before,
          expected_text: ap.after, start: it.start, end: it.end,
          status_after: ap.prevStatus.row }] }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok && (data.applied || []).length) {
        card.applied.delete(i);
        card.checks.set(i, false);
        toast('已還原', 'success');
        try { await p.refresh(); } catch (e) { toast('列表刷新失敗，請手動重新整理', 'warning'); }
      } else {
        card.applied.set(i, ap);
        const msg = (data.failed && data.failed[0] && data.failed[0].error)
          || data.error || '還原失敗';
        toast(msg.includes('段落已被修改') ? '段落已被再次修改，無法還原' : msg, 'warning');
      }
    } catch (e) {
      card.applied.set(i, ap);
      toast('還原失敗，請再試', 'error');
    } finally { renderList(); }
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

/* =========================================================
   Bjorn Global JS v1.2 — zero-config per page
   Injects: topbar, bottombar, quickpanel, console, launcher, settings, toasts
   Idempotent: safe to include multiple times. Works on file:// too
   ========================================================= */

/* =========================
 *  BjornUI.ConsoleSSE
 *  (wired to #logout)
 * ========================= */
window.BjornUI = window.BjornUI || {};
(function () {
  const $  = (s, r=document) => r.querySelector(s);

  BjornUI.ConsoleSSE = (function () {
    const state = {
      el: { logConsole: null, toggleImg: null, bufferIndicator: null, scrollBtn: null },
      fontSize: 12,
      maxLines: 200,
      fileColors: new Map(),
      levelClasses: {
        DEBUG: "debug", INFO: "info", WARNING: "warning",
        ERROR: "error", CRITICAL: "critical", SUCCESS: "success"
      },
      eventSource: null,
      isConsoleOn: false,
      reconnectAttempts: 0,
      maxReconnect: 5,
      reconnectDelay: 2000,
      // scroll/buffer
      isUserScrolling: false,
      autoScroll: true,
      scrollTimeout: null,
      logBuffer: [],
      maxBufferSize: 1000,
      targetSelector: '#logout',
      fontKey: 'Console.fontPx'

    };

    // ---------- helpers ----------
    function getRandomColor() {
      const letters = '89ABCDEF';
      let color = '#';
      for (let i=0;i<6;i++) color += letters[Math.floor(Math.random()*letters.length)];
      return color;
    }
    function forceBottom() {
      if (!state.el.logConsole) return;
      state.isUserScrolling = false;
      state.autoScroll = true;
      // laisse le layout se stabiliser (redim, ajout de lignes…), puis descend
      requestAnimationFrame(() => scrollToBottom());
    }
    function isAtBottom(el, threshold=50) {
      const scrollBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      return scrollBottom <= threshold;
    }
    function scrollToBottom() {
      if (!state.isUserScrolling && state.autoScroll) {
        state.el.logConsole.scrollTop = state.el.logConsole.scrollHeight;
      }
    }
    // ---------- helpers ----------
    function hueFromString(str){
      let h = 0;
      for (let i=0; i<str.length; i++) h = (h*31 + str.charCodeAt(i)) >>> 0;
      return h % 360;
    }

    // apply number highlighting only outside HTML tags
    function highlightNumbersOutsideTags(html){
      return html.split(/(<[^>]+>)/g).map((chunk, i) => {
        if (i % 2) return chunk; // it's a tag → do not touch
        chunk = chunk.replace(/^\d+/, m => `<span class="line-number">${m}</span>`);
        return chunk.replace(/\b\d+\b/g, m => `<span class="number">${m}</span>`);
      }).join('');
    }

    function processLogLine(line) {
      let modified = line;

      // 1) *.py files → colored bubble (deterministic hue)
      modified = modified.replace(/\b([A-Za-z0-9_]+\.py)\b/g, (m, fn) => {
        if (/<span[^>]*class="[^"]*logfile/.test(m)) return m; // avoid double-wrap
        const hue = hueFromString(fn);
        return `<span class="logfile" style="--h:${hue}">${fn}</span>`;
      });

      // 2) levels → bubbles
      modified = modified.replace(/\b(DEBUG|INFO|WARNING|ERROR|CRITICAL|SUCCESS|failed|Connected|SSE stream closed)\b/gi, (m) => {
        const key = m.toUpperCase();
        const cls = state.levelClasses[key] || 'info';
        return `<span class="loglvl ${cls}">${key}</span>`;
      });

      // 3) numbers → only outside tags (does not touch style="--h:246")
      modified = highlightNumbersOutsideTags(modified);

      return modified;
    }

    function updateBufferIndicator() {
      const ind = state.el.bufferIndicator;
      if (!ind) return;
      if (state.logBuffer.length > 0) {
        ind.style.display = 'block';
        ind.textContent = `${state.logBuffer.length} new logs`;
      } else {
        ind.style.display = 'none';
      }
    }
    function appendLogs(raw) {
      const clean = (raw||'').trim();
      if (!clean || !state.el.logConsole) return;

      if (state.isUserScrolling || !state.autoScroll) {
        state.logBuffer.push(clean);
        if (state.logBuffer.length > state.maxBufferSize) state.logBuffer.shift();
        updateBufferIndicator();
        return;
      }

      state.el.logConsole.innerHTML += processLogLine(clean) + '<br>';

      // keep bottom if already bottom
      if (state.autoScroll && !state.isUserScrolling) scrollToBottom();

      // cap lines
      const lines = state.el.logConsole.innerHTML.split('<br>');
      if (lines.length > state.maxLines) {
        state.el.logConsole.innerHTML = lines.slice(-state.maxLines).join('<br>');
      }
    }
    function flushBuffer() {
      if (!state.logBuffer.length || !state.el.logConsole) return;
      const buf = state.logBuffer.splice(0, state.logBuffer.length);
      for (const l of buf) {
        const s = l.trim(); if (!s) continue;
        state.el.logConsole.innerHTML += processLogLine(s) + '<br>';
      }
      scrollToBottom();
      updateBufferIndicator();
    }

    // ---------- SSE ----------
    function reconnect() {
      if (state.reconnectAttempts < state.maxReconnect) {
        setTimeout(() => {
          start(); // retry
          state.reconnectAttempts++;
        }, state.reconnectDelay);
      } else {
        state.isConsoleOn = false;
        if (state.el.toggleImg) state.el.toggleImg.src = '/web/images/off.png';
        console.error('Maximum SSE reconnection attempts reached');
      }
    }
    function start() {
      stopSSE(); // clean
      state.isConsoleOn = true;  
      try {
        state.eventSource = new EventSource('/stream_logs');
        state.eventSource.onopen = () => { state.reconnectAttempts = 0; };
        state.eventSource.onmessage = (ev) => appendLogs(ev.data);
        state.eventSource.onerror = (err) => {
          console.error('SSE Error:', err);
          if (state.eventSource && state.eventSource.readyState === EventSource.CLOSED) {
            stopSSE();
            if (state.isConsoleOn) reconnect();
          }
        };
      } catch (e) {
        console.error('Error creating EventSource:', e);
        if (state.isConsoleOn) reconnect();
      }
    }
    function stopSSE() {
      if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    }

    // ---------- public controls ----------
    function toggle() {
      state.isConsoleOn = !state.isConsoleOn;
      if (state.isConsoleOn) {
        start();
        if (state.el.toggleImg) state.el.toggleImg.src = '/web/images/on.png';
      } else {
        stop();
        if (state.el.toggleImg) state.el.toggleImg.src = '/web/images/off.png';
      }
    }
    function stop() {
      stopSSE();
      state.reconnectAttempts = 0;
      state.logBuffer = [];
      updateBufferIndicator();
    }
    function adjustFont(delta) {
      state.fontSize += delta;
      if (state.el.logConsole) state.el.logConsole.style.fontSize = state.fontSize + 'px';
    }
function setFont(px){
  const inp = document.getElementById('consoleFont');
  const min = inp ? (+inp.min || 2)  : 2;
  const max = inp ? (+inp.max || 24) : 24;

  const v = Math.max(min, Math.min(max, Math.round(px)));
  state.fontSize = v;

  if (state.el.logConsole){
    state.el.logConsole.style.fontSize = v + 'px';
    // ➜ variable pour tout ce qui doit suivre la console
    const consoleRoot = state.el.logConsole.closest('#console') || document.documentElement;
    consoleRoot.style.setProperty('--console-font', v + 'px');
  }

  try { localStorage.setItem(state.fontKey, String(v)); } catch {}

  if (inp){
    inp.value = String(v);
    const minv = +inp.min, maxv = +inp.max;
    inp.style.backgroundSize = `${((v - minv) * 100) / (maxv - minv)}% 100%`;
  }
}



    // ---------- UI extras ----------
    function addFloatingUI() {
      if (!state.el.logConsole) return;
      // "scroll to bottom" button
      const btn = document.createElement('button');
      btn.innerHTML = '⬇';
      btn.className = 'scroll-to-bottom-button';
      Object.assign(btn.style, {
        position:'fixed', bottom:'20px', right:'20px', display:'none',
        width:'40px', height:'40px', borderRadius:'50%', background:'rgba(0,0,0,.5)',
        color:'#fff', border:'none', cursor:'pointer', zIndex:'1000'
      });
      document.body.appendChild(btn);
      state.el.scrollBtn = btn;

      // buffer indicator
      const ind = document.createElement('div');
      ind.id = 'buffer-indicator';
      Object.assign(ind.style, {
        position:'fixed', bottom:'70px', right:'20px', display:'none',
        background:'rgba(0,0,0,.7)', color:'#fff', padding:'5px 10px',
        borderRadius:'15px', zIndex:'1000'
      });
      document.body.appendChild(ind);
      state.el.bufferIndicator = ind;

      btn.addEventListener('click', () => {
        state.autoScroll = true;
        state.isUserScrolling = false;
        flushBuffer();
        scrollToBottom();
        btn.style.display = 'none';
      });

      state.el.logConsole.addEventListener('scroll', () => {
        btn.style.display = isAtBottom(state.el.logConsole) ? 'none' : 'block';
      });
    }

    // ---------- listeners ----------
    function attachScrollUX() {
      const lc = state.el.logConsole;
      if (!lc) return;
      // main scroll
      lc.addEventListener('scroll', () => {
        clearTimeout(state.scrollTimeout);
        const was = state.isUserScrolling;
        state.isUserScrolling = true;

        if (isAtBottom(lc)) {
          state.autoScroll = true;
          state.isUserScrolling = false;
          if (was) flushBuffer();
        } else {
          state.autoScroll = false;
        }

        state.scrollTimeout = setTimeout(() => {
          if (isAtBottom(lc)) {
            state.isUserScrolling = false;
            state.autoScroll = true;
            flushBuffer();
          }
        }, 150);
      });

      // wheel
      lc.addEventListener('wheel', () => {
        clearTimeout(state.scrollTimeout);
        state.isUserScrolling = true;
        state.autoScroll = false;
        state.scrollTimeout = setTimeout(() => {
          if (isAtBottom(lc)) {
            state.isUserScrolling = false;
            state.autoScroll = true;
            flushBuffer();
          }
        }, 150);
      });
    }

    // ---------- lifecycle ----------
    function init(opts={}) {
      state.targetSelector = opts.targetSelector || '#logout';
      // legacy support: #log-console
      state.el.logConsole = document.querySelector(state.targetSelector) || document.querySelector('#log-console');
      state.el.toggleImg = document.querySelector('#toggle-console-image');

      if (!state.el.logConsole) {
        console.warn('[ConsoleSSE] container not found — inactive');
        return;
      }

      // mobile font
      // police par défaut (mobile léger) puis charge la valeur persistée si présente
      if (/Mobi|Android/i.test(navigator.userAgent) && !localStorage.getItem(state.fontKey)) {
        state.fontSize = 11;
      }
      try{
        const saved = parseInt(localStorage.getItem(state.fontKey)||'', 10);
        if (Number.isFinite(saved)) { setFont(saved); }
        else if (state.el.logConsole) { state.el.logConsole.style.fontSize = state.fontSize + 'px'; }
      }catch{
        if (state.el.logConsole) state.el.logConsole.style.fontSize = state.fontSize + 'px';
      }

      
      addFloatingUI();
      attachScrollUX();

      // autostart if configured
      fetch('/check_console_autostart')
        .then(r => r.text())
        .then(t => { if (t === 'True') { state.isConsoleOn = true; start(); } })
        .catch(e => console.error('check_console_autostart:', e));

      // clean on unload
      window.addEventListener('beforeunload', () => stopSSE());
    }

    return { init, start, stop, toggle, adjustFont, setFont, addUI: addFloatingUI, forceBottom  };
  })();
})();

/* =========================
 *  BjornUI.ManualMode — wired to the existing attackbar
 * ========================= */
window.BjornUI = window.BjornUI || {};
(function () {
  const $ = (s, r=document) => r.querySelector(s);

  BjornUI.ManualMode = (function () {
  const state = {
    el: {
      ip: null, port: null, action: null,
      btnScan: null, btnAttack: null, modeToggle: null, attackBar: null,
      modePill: null
    }
  };

/* =========================
 *  BjornUI.ApiActions — Orchestrator API
 * ========================= */
window.BjornUI = window.BjornUI || {};
(function () {
  function stopOrch(){
    fetch('/stop_orchestrator',{method:'POST'})
      .catch(e=>console.error('stop_orchestrator:', e));
  }
  function startOrch(){
    fetch('/start_orchestrator',{method:'POST'})
      .catch(e=>console.error('start_orchestrator:', e));
  }

  // single namespace
  BjornUI.ApiActions = { startOrch, stopOrch };

  // backwards compat for ManualMode.toggle()
  window.start_orchestrator = BjornUI.ApiActions.startOrch;
  window.stop_orchestrator  = BjornUI.ApiActions.stopOrch;
})();

    // ---- data loaders ----
    async function loadOptions() {
      try{
        const res = await fetch('/netkb_data_json');
        const data = await res.json();
        if (state.el.ip && Array.isArray(data.ips)) {
          state.el.ip.innerHTML = data.ips.map(ip=>`<option value="${ip}">${ip}</option>`).join('');
        }
        if (state.el.action && Array.isArray(data.actions)) {
          state.el.action.innerHTML = data.actions.map(a=>`<option value="${a}">${a}</option>`).join('');
        }
        await updatePorts(); // initialize ports for the selected IP
      }catch(e){ console.error('netkb options:', e); }
    }

    async function updatePorts() {
      try{
        const ip = state.el.ip?.value;
        const res = await fetch('/netkb_data_json');
        const data = await res.json();
        if (state.el.port) {
          if (ip && data.ports && Array.isArray(data.ports[ip]) && data.ports[ip].length) {
            state.el.port.innerHTML = data.ports[ip].map(p=>`<option value="${p}">${p}</option>`).join('');
          } else {
            state.el.port.innerHTML = '<option value="">Auto</option>';
          }
        }
      }catch(e){ console.error('update ports:', e); }
    }

    // ---- actions ----
    async function execScan() {
      const b = state.el.btnScan;
      b?.classList.add('scanning');
      try{
        const r = await fetch('/manual_scan', { method:'POST' });
        const d = await r.json();
        if (d.status!=='success') console.error('manual_scan:', d.message);
      }catch(e){ console.error('manual_scan:', e); }
      finally{ setTimeout(()=>b?.classList.remove('scanning'), 800); }
    }

    async function execAttack() {
      const b = state.el.btnAttack;
      b?.classList.add('attacking');
      const ip = state.el.ip?.value;
      const port = state.el.port?.value;
      const action = state.el.action?.value;

      try{
        const r = await fetch('/manual_attack', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ ip, port, action })
        });
        const d = await r.json();
        if (d.status!=='success') console.error('manual_attack:', d.message);
      }catch(e){ console.error('manual_attack:', e); }
      finally{ setTimeout(()=>b?.classList.remove('attacking'), 800); }
    }




    // ---- mode ----
    async function check() {
      try{
        const t = await fetch('/check_manual_mode').then(r=>r.text());
        updateUI(t);
      }catch(e){ console.error('check_manual_mode:', e); }
    }
    function showAttack(on){
      const consoleEl    = document.getElementById('console');
      const attackBar    = state.el.attackBar;
      const attackToggle = document.getElementById('attackToggle');
      if (!consoleEl || !attackBar) return;

      const mobile = window.innerWidth <= 700; // auto hide on mobile
      const visible = !!on && !mobile;

      consoleEl.classList.toggle('with-attack', visible);
      attackBar.style.display = visible ? 'flex' : 'none';
      attackToggle?.setAttribute('aria-expanded', String(visible));
      
      window.BjornUI?.ConsoleSSE?.forceBottom?.();

    }
  function paintModePill(isManual){
    const pill = state.el.modePill; if(!pill) return;
    pill.classList.toggle('manual', isManual);
    pill.classList.toggle('auto', !isManual);
    pill.innerHTML = `<span class="dot"></span>${isManual ? 'Manual' : 'Auto'}`;
    pill.setAttribute('aria-label', isManual ? 'Manual mode' : 'Auto mode');
  }

  function updateUI(flag) {
    const isManual = (flag === 'True');
    if (state.el.modeToggle){
      state.el.modeToggle.setAttribute('aria-pressed', String(isManual));
      state.el.modeToggle.textContent = isManual ? 'Turn on Auto' : 'Turn on Manual';
    }
    paintModePill(isManual);  // ⬅️ met à jour la bulle
    showAttack(isManual);
  }


    async function toggle() {
      const isAuto = state.el.modeToggle?.textContent.trim() === 'Turn on Manual';
      try{
        if (isAuto) {
          window.stop_orchestrator?.();   // switch to manual
          updateUI('True');               // show panel
        } else {
          window.start_orchestrator?.();  // back to auto
          updateUI('False');              // hide panel
        }
      }catch(e){ console.error('toggle manual mode:', e); }
    }

    // ---- init ----
    function init() {
      state.el.ip        = $('#selIP');
      state.el.port      = $('#selPort');
      state.el.action    = $('#selAction');
      state.el.btnScan   = $('#btnScan');
      state.el.btnAttack = $('#btnAttack');
      state.el.modeToggle= $('#modeToggle');
      state.el.attackBar = $('#attackBar');
      state.el.modePill  = $('#modePill');


      // listeners
      state.el.ip?.addEventListener('change', updatePorts);
      state.el.btnScan?.addEventListener('click', (e)=>{ e.preventDefault(); execScan(); });
      state.el.btnAttack?.addEventListener('click',(e)=>{ e.preventDefault(); execAttack(); });

      // load data + state
      loadOptions();
      check();
    }

    return { init, loadOptions, updatePorts, execScan, execAttack, check, toggle, showAttack };
  })();
})();

/* =========================
 *  BjornUI.BjornTopbar → docked in the bottombar
 * ========================= */
window.BjornUI = window.BjornUI || {};
(function () {
  const $ = (s, r=document) => r.querySelector(s);

  BjornUI.BjornTopbar = (function () {
    const state = {
      el: {
        status: null, status2: null, statusImg: null,
        say: null, character: null, dropdown: null, liveImg: null
      },
      live: { timer: null, delay: 2000, last: 0 }
    };

    // ------- liveview dropdown (docked above the character) -------
    function ensureDropdown() {
      if (state.el.dropdown) return;
      // Find the character container (now part of grid)
      const holder =
        document.querySelector('.status-center') ||
        document.querySelector('.status-character') ||
        document.body;

      const d = document.createElement('div');
      d.className = 'bjorn-dropdown';
      d.innerHTML = `<img id="screenImage_Home" src="screen.png" alt="Bjorn">`;
      // Positioned relative to the status-center container
      d.style.position='absolute';
      d.style.display='none';
      d.style.zIndex='10000';
      d.style.background='#222';
      d.style.borderRadius='8px';
      d.style.boxShadow='0 8px 24px rgba(0,0,0,.45)';
      d.style.bottom='calc(100% + 6px)';
      d.style.left='50%';
      d.style.transform='translateX(-50%)';
      holder.appendChild(d);

      state.el.dropdown = d;
      state.el.liveImg = $('#screenImage_Home', d);
      if (state.el.liveImg) state.el.liveImg.addEventListener('click', () => location.href = '/bjorn.html');

      // hover/tap handlers
      const c = state.el.character || $('#bjorncharacter') || holder;
      const show = ()=>{ d.style.display='block'; startLiveview(); };
      const hide = ()=>{ d.style.display='none';  stopLiveview(); };
      c.addEventListener('mouseenter', show);
      c.addEventListener('mouseleave', hide);
      document.addEventListener('click', (ev)=>{ if(!d.contains(ev.target) && !c.contains(ev.target)) hide(); });
      c.addEventListener('click', ()=>{ d.style.display = (d.style.display==='block' ? 'none':'block'); if(d.style.display==='block') startLiveview(); else stopLiveview(); });
    }

    function updateImageOnce() {
      const now = Date.now();
      if (now - state.live.last < state.live.delay) return;
      state.live.last = now;
      const img = state.el.liveImg; if (!img) return;
      const n = new Image();
      n.onload  = () => img.src = n.src;
      n.onerror = () => console.warn('Liveview image load failed');
      n.src = `screen.png?t=${Date.now()}`;
    }
    function startLiveview(){ updateImageOnce(); state.live.timer = setInterval(updateImageOnce, state.live.delay); }
    function stopLiveview(){ clearInterval(state.live.timer); state.live.timer = null; }

    // ------- fetchers -------
function updateStatus() {
  return fetch('/bjorn_status').then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }).then(d => {
    if (state.el.status) {
      if (d.status && d.status.trim()) {
        state.el.status.textContent = d.status;
      } else if (!state.el.status.textContent.trim()) {
        state.el.status.textContent = 'Status unavailable';
      }
    }

    if (state.el.status2) {
      if (d.status2 && d.status2.trim()) {
        state.el.status2.textContent = d.status2;
        state.el.status2.style.display = '';
      } else {
        state.el.status2.style.display = 'none';
      }
    }

    if (d.image_path && state.el.statusImg) {
      state.el.statusImg.src = `${d.image_path}?t=${Date.now()}`;
    }
  }).catch(e => {
    console.error('Bjorn status:', e);
    if (state.el.status && !state.el.status.textContent.trim()) {
      state.el.status.textContent = 'Status unavailable';
    }
  });
}

function updateSay() {
  return fetch('/bjorn_say').then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }).then(d => {
    if (state.el.say) {
      if (d.text && d.text.trim()) {
        state.el.say.textContent = d.text;
      } else if (!state.el.say.textContent.trim()) {
        state.el.say.textContent = 'Message unavailable';
      }
    }
  }).catch(e => {
    console.error('Bjorn say:', e);
    if (state.el.say && !state.el.say.textContent.trim()) {
      state.el.say.textContent = 'Message unavailable';
    }
  });
}
    function updateCharacter() {
      return fetch('/bjorn_character').then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.blob();
      }).then(b => {
        if (!state.el.character) return;
        if (state.el.character.src && state.el.character.src.startsWith('blob:')) URL.revokeObjectURL(state.el.character.src);
        state.el.character.src = URL.createObjectURL(b);
      }).catch(e => console.error('bjorn_character:', e));
    }

    // ------- lifecycle -------
    function init() {
      state.el.status    = $('#bjornStatus');
      state.el.status2   = $('#bjornStatus2');
      state.el.statusImg = $('#bjornStatusImage');
      state.el.say       = $('#bjornSay');
      state.el.character = $('#bjorncharacter');
      // Look for dropdown in the new grid structure
      state.el.dropdown  = document.querySelector('.status-center .bjorn-dropdown') ||
                           document.querySelector('.status-character .bjorn-dropdown');
      state.el.liveImg   = state.el.dropdown ? $('#screenImage_Home', state.el.dropdown) : null;

      ensureDropdown();

      updateStatus(); updateCharacter(); updateSay();
      setInterval(updateStatus, 5000);
      setInterval(updateCharacter, 5000);
      setInterval(updateSay, 5000);
    }
    function refreshAll(){ updateStatus(); updateCharacter(); updateSay(); }

    return { init, refreshAll };
  })();
})();

/* =========================
 *  Bjorn Global JS
 * ========================= */
(async function(){  // wrapper async
  // Safeguard: wait DOM if script is in <head> without "defer"
  if(!document.body){
    await new Promise(r=>document.addEventListener('DOMContentLoaded', r, {once:true}));
  }
if (window.__BJORN_QP__) return;
window.__BJORN_QP__ = true;
  // ===== Utilities
  const $  = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const el = (tag,attrs={},children=[])=>{
    const n=document.createElement(tag);
    for(const [k,v] of Object.entries(attrs)){
      if(k==='class') n.className=v;
      else if(k==='style') n.style.cssText=v;
      else if(k.startsWith('on')&&typeof v==='function') n.addEventListener(k.slice(2),v);
      else if(v!==null&&v!==undefined) n.setAttribute(k,v);
    }
    if(!Array.isArray(children)) children = children ? [children] : [];
    children.forEach(c=> n.append(c?.nodeType?c:document.createTextNode(c)));
    return n;
  };
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  const uid = (p='id')=>`${p}-${Math.random().toString(36).slice(2,9)}`;

  // ===== Config loader
  async function loadConfig(){
    if(window.BjornConfig) return window.BjornConfig;
    try{ const raw = localStorage.getItem('BjornConfig'); if(raw) return JSON.parse(raw); }catch{}
    try{
      const res = await fetch('/bjorn.config.json',{cache:'no-store'});
      if(res.ok){ const json = await res.json(); try{ localStorage.setItem('BjornConfig', JSON.stringify(json)); }catch{} return json; }
    }catch{} // ok offline/file://
    return {};
  }
  const _cfg = await loadConfig();
const toolbarItems = [
  { path: '/index.html', icon: '/web/images/index.png', alt: 'Bjorn', tooltip: 'Main Bjorn page.', title: 'Bjorn' },
  { path: '/scheduler.html', icon: '/web/images/scheduler.png', alt: 'Icon_config', tooltip: 'Manage scheduled tasks for Bjorn.', title: 'Scheduler' },
  { path: '/network.html', icon: '/web/images/network.png', alt: 'Icon_network', tooltip: 'Visualize current network discoveries.', title: 'Network' },
  { path: '/netkb.html', icon: '/web/images/netkb.png', alt: 'Icon_netkb', tooltip: 'Network Knowledge Base (Bjorn memory).', title: 'NetKB' },
  { path: '/credentials.html', icon: '/web/images/credentials.png', alt: 'Icon_cred', tooltip: 'Credentials found by Bjorn.', title: 'Credentials' },
  { path: '/loot.html', icon: '/web/images/loot.png', alt: 'Icon_loot', tooltip: 'Collected files.', title: 'Loot' },
  { path: '/files_explorer.html', icon: '/web/images/files_explorer.png', alt: 'Icon_bag', tooltip: 'Bjorn Files Explorer', title: 'Files Explorer' },
  { path: '/backup_update.html', icon: '/web/images/backup_update.png', alt: 'Icon_backup', tooltip: 'Backups, restores and updates from GitHub.', title: 'Backup & Update' },
  { path: '/attacks.html', icon: '/web/images/attacks.png', alt: 'Icon_attacks', tooltip: 'Manage comments and icons for actions.', title: 'Actions Management' },
  { path: '/actions_launcher.html', icon: '/web/images/actions_launcher.png', alt: 'Icon_about', tooltip: 'Launch and manage Actions (Experimental).', title: 'Actions Launcher' },
  { path: '/actions_studio.html', icon: '/web/images/actions_studio.png', alt: 'Icon_actions_studio', tooltip: 'Create action scenarios.', title: 'Actions Studio' },
  { path: '/vulnerabilities.html', icon: '/web/images/vulnerabilities.png', alt: 'Icon_vulnerabilities', tooltip: 'Manage vulnerabilities from the UI.', title: 'Vulnerabilities' },
  { path: '/database.html', icon: '/web/images/database.png', alt: 'Icon_settings', tooltip: 'Manage application settings.', title: 'Database' },
  { path: '/zombieland.html', icon: '/web/images/zombieland.png', alt: 'Icon_zombieland', tooltip: 'Explore the Zombieland.', title: 'Zombieland' },
  { path: '/web_enum.html', icon: '/web/images/web_enum.png', alt: 'Icon_webenum', tooltip: 'Web enumeration and attacks.', title: 'Web Enum' }


];

// --- REST endpoints réels ---
const API = {
  // Wi-Fi
  scanWifi: '/scan_wifi',
  getKnownWifi: '/get_known_wifi',
  connectKnown: '/connect_known_wifi',
  connectWifi: '/connect_wifi',
  updatePriority: '/update_wifi_priority',
  deleteKnown: '/delete_known_wifi',
  importPotfiles: '/import_potfiles',
  // Bluetooth
  scanBluetooth: '/scan_bluetooth',
  pairBluetooth: '/pair_bluetooth',
  trustBluetooth: '/trust_bluetooth',
  connectBluetooth: '/connect_bluetooth',
  disconnectBluetooth: '/disconnect_bluetooth',
  forgetBluetooth: '/forget_bluetooth'
};




  // merged cfg with toolbarItems
  const cfg = Object.assign({
    launcher: true,
    pages: toolbarItems.map(item => ({
      href: item.path,
      title: item.title,
      icon: item.icon,
      alt: item.alt,
      tooltip: item.tooltip
    })),
    shortcuts: {
      console:   { ctrl:true, key:'`' },
      quickpanel:{ ctrl:true, key:'\\' }
    }
  }, _cfg || {});

  // ===== Ensure scanlines overlay
  if(!$('.scanlines')) document.body.appendChild(el('div',{class:'scanlines'}));

// ---- Mode pill styles (Auto/Manual)
(() => {
  if (document.getElementById('modePillStyles')) return;
  const st = document.createElement('style');
  st.id = 'modePillStyles';
  st.textContent = `
  .mode-pill{
    display:inline-flex;align-items:center;gap:6px;
    padding:4px 10px;border-radius:999px;border:1px solid;
    font-size:12px;line-height:1;font-weight:600;
    letter-spacing:.2px;user-select:none;
  }
  .mode-pill .dot{width:8px;height:8px;border-radius:50%;}
  .mode-pill.auto{
    background: rgba(0,255,154,.15); border-color: rgba(0,255,154,.45); color: var(--acid,#00ff9a);
  }
  .mode-pill.auto .dot{ background: var(--acid,#00ff9a); box-shadow:0 0 8px var(--acid,#00ff9a);}
  .mode-pill.manual{
    background: rgba(24,144,255,.15); border-color: rgba(24,144,255,.45); color: #57a9ff;
  }
  .mode-pill.manual .dot{ background:#57a9ff; box-shadow:0 0 8px #57a9ff; }
  `;
  document.head.appendChild(st);
})();

(() => {
  if (document.getElementById('consoleFontStyles')) return;
  const st = document.createElement('style');
  st.id = 'consoleFontStyles';
  st.textContent = `
  .console-head{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .console-fontrow{
    flex-basis:100%;
    display:flex; justify-content:flex-end; align-items:center;
    padding-top:2px; margin-top:2px;
  }
  .console-fontrow input[type="range"]{
    width:-webkit-fill-available; height:2px; border-radius:999px; outline:0;
    -webkit-appearance:none; appearance:none;
    background:
      linear-gradient(var(--acid, #00ff9a), var(--acid, #00ff9a)) 0/50% 100% no-repeat,
      rgba(255,255,255,.08);
  }
  .console-fontrow input[type="range"]::-webkit-slider-thumb{
    -webkit-appearance:none; appearance:none;
    width:10px; height:10px; border-radius:50%;
    background:var(--acid,#00ff9a); box-shadow:0 0 8px var(--acid,#00ff9a);
    margin-top:-4px; /* centre sur piste 2px */
  }
  .console-fontrow input[type="range"]::-moz-range-thumb{
    width:10px; height:10px; border-radius:50%;
    background:var(--acid,#00ff9a); box-shadow:0 0 8px var(--acid,#00ff9a);
    border:0;
  }
  .sr-only{ position:absolute; width:1px; height:1px; padding:0; margin:-1px;
            overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
  `;
  document.head.appendChild(st);
})();
(() => {
  if (document.getElementById('consoleFontFollowStyles')) return;
  const st = document.createElement('style');
  st.id = 'consoleFontFollowStyles';
  st.textContent = `
    /* La console entière suit --console-font (fallback 12px) */
    #console .console-body, #console #logout { 
      font-size: var(--console-font, 12px);
      line-height: 1.3;
    }

    /* Les badges de niveau suivent la taille (em) */
    #console .loglvl{
      font-size: 0.92em;               /* ← suit la taille */
      line-height: 1; 
      padding: .15em .55em; 
      border-radius: .8em;
      display: inline-inline;
      vertical-align: baseline;
    }

    /* Autres spans ajoutés au vol : qu’ils héritent aussi */
    #console .logfile,
    #console .number,
    #console .line-number{
      font-size: 1em; /* hérite */
    }
  `;
  document.head.appendChild(st);
})();

/* =========================================================
   Actions Dropdown — Dynamic build + legacy actions wiring
   Language: EN
   Uses window.Bjorn.toast (fallback to global toast)
   ========================================================= */

// ---------- 1) Dropdown items ----------
const dropdownItems = [
  { action: 'restart_bjorn_service', text: 'Restart Bjorn Service 🔄', tooltip: 'Restart the Bjorn service to refresh its state.' },
  { action: 'remove_All_Actions', text: 'Delete all actions status', tooltip: 'Delete all recorded success & failed actions/attacks statuses in netkb.csv.' },
  { action: 'clear_output_folder', text: 'Clear Output folder', tooltip: 'Erase all files from the data/output folders & subdirectories.' },
  { action: 'clear_logs', text: 'Clear Logs', tooltip: 'Delete all log files from the system. (data/log/Bjorn.log)' },
  { action: 'reload_images', text: 'Reload Images (Experimental Buggy)', tooltip: 'Reload images used by the system. (Experimental feature, Bjorn service can be stuck).' },
  { action: 'reload_fonts', text: 'Reload Fonts', tooltip: 'Reload font assets for the application.' },
  { action: 'reload_generate_actions_json', text: 'Reload Generate Actions JSON', tooltip: 'Reload the Generate Actions JSON file.' },
  { action: 'initialize_csv', text: 'Initialize CSV files', tooltip: 'Recreate the CSV & JSON files: Netkb, Livestatus, Actions.' },
  { action: 'clear_livestatus', text: 'Delete Livestatus file 🔄', tooltip: 'Delete the current live status file (live stats on e-ink).' },
  { action: 'clear_actions_file', text: 'Refresh Actions file 🔄', tooltip: 'Refresh the actions file to take into account new actions.' },
  { action: 'clear_netkb', text: '⚠️ Clear Network Knowledge Base ⚠️ 🔄', tooltip: 'Clear all saved network knowledge base information.' },
  { action: 'clear_shared_config_json', text: '⚠️ Delete Shared Config JSON ⚠️ 🔄', tooltip: 'Delete the shared configuration JSON file. Defaults will be recreated.' },
  { action: 'erase_bjorn_memories', text: '⚠️ Erase Bjorn Memories ⚠️ 🔄', tooltip: 'Completely erase Bjorn memories and settings.' },
  { action: 'reboot_system', text: 'Reboot System', tooltip: 'Restart the entire system.' },
  { action: 'shutdown_system', text: 'Shutdown System', tooltip: 'Power down the system.' },
  // { action: 'logout', text: 'Logout', tooltip: 'Logout from the current session. (Upcoming in next releases)' }
];

// ---------- 2) Legacy action functions (standardized with toast) ----------
const toast = (msg, ms=2600) =>
  (typeof window.toast === 'function' ? window.toast(msg, ms) : window.Bjorn?.toast?.(msg, ms));

const actionFunctions = {
  // --- Delete/cleanup actions ---
  remove_All_Actions: function (ip) {
    const confirmRemoval = confirm(`Are you sure you want to remove all actions status?`);
    if (!confirmRemoval) return;
    fetch('/delete_all_actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip })
    })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => {
      if (d.status === 'success') {
        console.log(d.message);
        toast(d.message || 'All action statuses removed.');
        try { fetchNetkbData?.(); } catch {}
      } else {
        console.error(d.message); toast(d.message || 'Failed to remove actions.');
      }
    })
    .catch(e => { console.error(e); toast(`Error: ${e.message || e}`); });
  },

  clear_output_folder: function () {
    const confirmRemoval = confirm(`Are you sure you want to clear the data in the output folder?`);
    if (!confirmRemoval) return;
    fetch('/clear_output_folder', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
    .then(r => r.json())
    .then(d => d.status === 'success' ? toast(d.message || 'Output cleared.') : toast(d.message || 'Failed to clear output.'))
    .catch(e => { console.error(e); toast('Error clearing output folder.'); });
  },

  clear_logs: function () {
    const confirmClear = confirm(`Are you sure you want to clear the logs?`);
    if (!confirmClear) return;
    fetch('/clear_logs', { method: 'POST' })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => d.status === 'success' ? toast(d.message || 'Logs cleared.') : toast(d.message || 'Failed to clear logs.'))
    .catch(e => { console.error(e); toast('Error clearing logs.'); });
  },

  // --- Cleanup with restart suggestions ---
clear_netkb: function () {
  const confirmRemoval = confirm(
    'Warning: This will clear the entire Network Knowledge Base (NetKB). This action is irreversible. Service restart is recommended. Proceed?'
  );
  if (!confirmRemoval) return;

  fetch('/clear_netkb', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => {
      if (d.status === 'success') {
        toast(d.message || 'NetKB cleared.');
        if (confirm('Service restart is recommended. Restart now?')) actionFunctions.rst_withoutconfirm_bjorn_svc();
      } else {
        toast(d.message || 'Failed to clear NetKB.');
      }
    })
    .catch(e => { console.error(e); toast('Error clearing NetKB.'); });
},

  clear_livestatus: function () {
    const confirmClear = confirm(`Are you sure you want to clear the LiveStatus (service restart recommended)?`);
    if (!confirmClear) return;
    fetch('/clear_livestatus', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => {
      if (d.status === 'success') {
        toast(d.message || 'Livestatus cleared.');
        if (confirm(`Service restart is recommended. Restart now?`)) actionFunctions.rst_withoutconfirm_bjorn_svc();
      } else { toast(d.message || 'Failed to clear Livestatus.'); }
    })
    .catch(e => { console.error(e); toast('Error clearing Livestatus.'); });
  },

  clear_actions_file: function () {
    const confirmClear = confirm(`Are you sure you want to clear the Actions File (service restart recommended)?`);
    if (!confirmClear) return;
    fetch('/clear_actions_file', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => {
      if (d.status === 'success') {
        toast(d.message || 'Actions file cleared.');
        if (confirm(`Service restart is recommended. Restart now?`)) actionFunctions.rst_withoutconfirm_bjorn_svc();
      } else { toast(d.message || 'Failed to clear actions file.'); }
    })
    .catch(e => { console.error(e); toast('Error clearing actions file.'); });
  },

  clear_shared_config_json: function () {
    const confirmClear = confirm(`Are you sure you want to delete the Shared Config JSON (service restart recommended)?`);
    if (!confirmClear) return;
    fetch('/clear_shared_config_json', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => {
      if (d.status === 'success') {
        toast(d.message || 'Shared config JSON deleted.');
        if (confirm(`Defaults will be recreated. Restart service now?`)) actionFunctions.rst_withoutconfirm_bjorn_svc();
      } else { toast(d.message || 'Failed to delete shared config JSON.'); }
    })
    .catch(e => { console.error(e); toast('Error deleting shared config JSON.'); });
  },

  erase_bjorn_memories: function () {
    const confirmErase = confirm(`Are you sure you want to erase Bjorn's memories? This is irreversible. Restart recommended.`);
    if (!confirmErase) return;
    fetch('/erase_bjorn_memories', { method: 'POST' })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => {
      if (d.status === 'success') {
        toast(d.message || `Bjorn's memories erased.`);
        if (confirm(`Restart the service now?`)) actionFunctions.rst_withoutconfirm_bjorn_svc();
      } else { toast(d.message || 'Failed to erase memories.'); }
    })
    .catch(e => { console.error(e); toast('Error erasing memories.'); });
  },

  // --- Service actions ---
  restart_bjorn_service: function () {
    const confirmRestart = confirm(`Are you sure you want to restart the Bjorn service?`);
    if (!confirmRestart) return;
    fetch('/restart_bjorn_service', { method: 'POST' })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => d.status === 'success' ? toast(d.message || 'Service restarted.') : toast(d.message || 'Failed to restart service.'))
    .catch(e => { console.error(e); toast('Error restarting service.'); });
  },

  rst_withoutconfirm_bjorn_svc: function () {
    fetch('/restart_bjorn_service', { method: 'POST' })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => d.status === 'success' ? toast(d.message || 'Service restarted.') : toast(d.message || 'Failed to restart service.'))
    .catch(e => { console.error(e); toast('Error restarting service.'); });
  },

  // --- System actions ---
  reboot_system: function () {
    const confirmReboot = confirm(`Are you sure you want to reboot the system?`);
    if (!confirmReboot) return;
    fetch('/reboot_system', { method: 'POST' })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => d.status === 'success' ? toast(d.message || 'System rebooting...') : toast(d.message || 'Failed to reboot.'))
    .catch(e => { console.error(e); toast('Error requesting reboot.'); });
  },

  shutdown_system: function () {
    const confirmShutdown = confirm(`Are you sure you want to shutdown the system?`);
    if (!confirmShutdown) return;
    fetch('/shutdown_system', { method: 'POST' })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => d.status === 'success' ? toast(d.message || 'System shutting down...') : toast(d.message || 'Failed to shutdown.'))
    .catch(e => { console.error(e); toast('Error requesting shutdown.'); });
  },

  // logout: function () {
  //   const confirmLogout = confirm(`Are you sure you want to logout?`);
  //   if (!confirmLogout) return;
  //   fetch('/logout', { method: 'POST' })
  //   .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  //   .then(d => {
  //     if (d.status === 'success') {
  //       toast(d.message || 'Logged out.');
  //       window.location.href = '/login';
  //     } else { toast(d.message || 'Failed to logout.'); }
  //   })
  //   .catch(e => { console.error(e); toast('Error during logout.'); });
  // },

  // --- Reload/init actions ---
  initialize_csv: function () {
    fetch('/initialize_csv', { method: 'POST' })
    .then(r => r.json())
    .then(d => d.status === 'success' ? toast('CSV initialized successfully.') : toast(`Error initializing CSV: ${d.message || ''}`))
    .catch(e => { console.error(e); toast('An error occurred while initializing CSV.'); });
  },

  reload_generate_actions_json: function () {
    fetch('/reload_generate_actions_json', { method: 'POST' })
    .then(r => r.json())
    .then(d => d.status === 'success' ? toast('Generate Actions JSON reloaded successfully.') : toast(`Error reloading Generate Actions JSON: ${d.message || ''}`))
    .catch(e => { console.error(e); toast('An error occurred while reloading Generate Actions JSON.'); });
  },

  reload_images: function () {
    fetch('/reload_images', { method: 'POST' })
    .then(r => r.json())
    .then(d => d.status === 'success' ? toast('Images reloaded successfully.') : toast(`Error reloading images: ${d.message || ''}`))
    .catch(e => { console.error(e); toast('An error occurred while reloading images.'); });
  },

  reload_fonts: function () {
    fetch('/reload_fonts', { method: 'POST' })
    .then(r => r.json())
    .then(d => d.status === 'success' ? toast('Fonts reloaded successfully.') : toast(`Error reloading fonts: ${d.message || ''}`))
    .catch(e => { console.error(e); toast('An error occurred while reloading fonts.'); });
  }
};

// ---------- 3) Optional legacy API helpers (ported to toast) ----------
window.Bjorn = window.Bjorn || {};
Bjorn.ApiActions = Bjorn.ApiActions || (function () {
  const json = (url, opt = { method: 'POST' }) => fetch(url, opt).then(r => r.json());
  const alertErr = (prefix) => (e) => toast(`${prefix}: ${e.message || e}`);

  function clearFiles() { json('/clear_files').then(d => toast(d.message)).catch(alertErr('Failed to clear files')); }
  function clearFilesLight() { json('/clear_files_light').then(d => toast(d.message)).catch(alertErr('Failed to clear files')); }
  function reboot() { json('/reboot').then(d => toast(d.message)).catch(alertErr('Failed to reboot')); }
  function shutdown() { json('/shutdown').then(d => toast(d.message)).catch(alertErr('Failed to shutdown')); }
  function restartService() { json('/restart_bjorn_service').then(d => toast(d.message)).catch(alertErr('Failed to restart service')); }
  function backup() {
    json('/backup').then(d => {
      if (d.status === 'success') {
        const a = document.createElement('a'); a.href = d.url; a.download = d.filename; a.click();
        toast('Backup completed successfully');
      } else { toast('Backup failed: ' + d.message); }
    }).catch(alertErr('Backup failed'));
  }
  function restore() {
    const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.zip';
    inp.onchange = () => {
      const f = inp.files[0]; const fd = new FormData(); fd.append('file', f);
      fetch('/restore', { method: 'POST', body: fd })
        .then(r => r.json()).then(d => toast(d.message))
        .catch(alertErr('Restore failed'));
    };
    inp.click();
  }
  function stopOrch() { fetch('/stop_orchestrator', { method: 'POST' }).catch(e => console.error('stop_orchestrator:', e)); }
  function startOrch() { fetch('/start_orchestrator', { method: 'POST' }).catch(e => console.error('start_orchestrator:', e)); }
  function disconnectWifi() { json('/disconnect_wifi').then(d => toast(d.message)).catch(alertErr('Failed to disconnect')); }
  function initCSV() { json('/initialize_csv').then(d => toast(d.message)).catch(alertErr('Failed to initialize CSV')); }

  return { clearFiles, clearFilesLight, reboot, shutdown, restartService, backup, restore, startOrch, stopOrch, disconnectWifi, initCSV };
})();

// ---------- 4) Topbar (dynamic actions menu built from dropdownItems) ----------
let topbar = $('.topbar');
if (!topbar) {
  topbar = el('header', { class: 'topbar' }, [
    // Logo cliquable → /bjorn.html
    el('div', { class: 'logo', id: 'logoBtn', role: 'button', tabindex: '0', style: 'cursor:pointer' }, [
      el('img', { class: 'sig', src: '/web/images/bjornwebicon.png', alt: 'Bjorn' }),
      'BJORN'
    ]),

    $('#sidebar') && el('button', { class: 'btn', id: 'toggleSidebar' }, [
      el('span', { class: 'icon' }, '📂'),
      el('span', { class: 'label' }, 'Sidebar')
    ]),
    el('button', { class: 'btn', id: 'openSettings' }, [
      el('span', { class: 'icon' }, '⚙️'),
      el('span', { class: 'label' }, 'Settings')
    ]),
    el('button', { class: 'btn', id: 'openQuick' }, [
      el('span', { class: 'icon' }, '⚡'),
      el('span', { class: 'label' }, 'Shortcuts')
    ]),
    el('div', { class: 'spacer' }),

    (function () {
      const wrap = el('div', { class: 'actions', id: 'actionsWrap' });
      const btn = el('button', { class: 'btn', id: 'actionsBtn', 'aria-haspopup': 'true', 'aria-expanded': 'false', 'aria-controls': 'actionsMenu' }, [
        el('span', { class: 'icon' }, '🛠️'),
        el('span', { class: 'label' }, 'Actions')
      ]);
      const menu = el('div', { class: 'dropdown', id: 'actionsMenu', role: 'menu', 'aria-hidden': 'true' }, []);

      dropdownItems.forEach(it => {
        menu.append(
          el('div', {
            class: 'menuitem',
            role: 'menuitem',
            tabindex: '-1',
            'data-action': it.action,
            title: it.tooltip
          }, [
            el('span', { class: 'mi-icon' }, ''),
            it.text
          ])
        );
      });

      wrap.append(btn, menu);
      return wrap;
    })(),

    el('button', { class: 'btn', id: 'openLauncher' }, [
      el('span', { class: 'icon' }, '🧭'),
      el('span', { class: 'label' }, 'Pages')
    ])

  ].filter(Boolean)); // <<< removes null/false

  document.body.appendChild(topbar);

  // Redirection au clic (et accessibilité clavier)
  const logoBtn = topbar.querySelector('#logoBtn');
  if (logoBtn) {
    const go = () => (location.href = '/bjorn.html');
    logoBtn.addEventListener('click', go);
    logoBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
    });
  }
}

// ---------- 5) Dropdown behavior (pointer events, sticky mobile, no double tap) ----------
const actionsWrap = $('#actionsWrap');
const actionsBtn  = $('#actionsBtn');
const actionsMenu = $('#actionsMenu');
const topbarEl    = document.querySelector('.topbar');

function placeActionsMenu() {
  if (!actionsMenu) return;
  const tb  = topbarEl?.getBoundingClientRect();
  const top = Math.round((tb?.bottom ?? 0)) - 1;
  actionsMenu.style.top = top + 'px';
  actionsMenu.style.left = '50%';
  actionsMenu.style.transform = 'translateX(-50%)';
}

const isMenuOpen = () => actionsMenu?.classList.contains('show');
let actionsSticky = false;

function setActionsOpen(show, { sticky } = {}) {
  actionsSticky = !!sticky;
  actionsMenu?.classList.toggle('show', show);
  actionsMenu?.setAttribute('aria-hidden', String(!show));
  actionsBtn?.setAttribute('aria-expanded', String(show));
  if (show) {
    placeActionsMenu();
    actionsMenu.querySelector('.menuitem')?.focus();
  }
}

// 1) Hover seulement sur appareils qui *supportent* le hover (desktop)
const supportsHover = window.matchMedia('(hover: hover)').matches;
if (supportsHover) {
  let hoverTimer = null;
  actionsWrap?.addEventListener('mouseenter', () => {
    clearTimeout(hoverTimer);
    setActionsOpen(true, { sticky: false });
  });
  actionsWrap?.addEventListener('mouseleave', () => {
    if (actionsSticky) return;
    hoverTimer = setTimeout(() => setActionsOpen(false), 150);
  });
}

// 2) Toggle via *pointerup* (tactile & souris). On avale le click synthétique après un touch.
let swallowNextClick = false;
actionsBtn?.addEventListener('pointerup', (e) => {
  // Sur tactile/stylet : éviter le click synthétique qui suit le touchend
  if (e.pointerType !== 'mouse') {
    e.preventDefault();
    e.stopPropagation();
    swallowNextClick = true;
  }
  const open = !isMenuOpen();
  setActionsOpen(open, { sticky: open });
});

// Avale le click synthétique post-touch
actionsBtn?.addEventListener('click', (e) => {
  if (swallowNextClick) {
    swallowNextClick = false;
    e.preventDefault();
    e.stopPropagation();
  }
});

// 3) Fermer en *pointerdown* à l’extérieur (plus fiable que touchend/click)
document.addEventListener('pointerdown', (e) => {
  if (!isMenuOpen()) return;
  if (!actionsWrap?.contains(e.target)) setActionsOpen(false);
}, true);

// 4) Clavier (ESC + navigation)
document.addEventListener('keydown', (e) => {
  if (!isMenuOpen()) return;
  if (e.key === 'Escape') { setActionsOpen(false); return; }

  const items = [...actionsMenu.querySelectorAll('.menuitem')];
  const idx = items.indexOf(document.activeElement);
  if (e.key === 'ArrowDown') { e.preventDefault(); (items[(idx + 1 + items.length) % items.length] || items[0])?.focus(); }
  if (e.key === 'ArrowUp')   { e.preventDefault(); (items[(idx - 1 + items.length) % items.length] || items[items.length - 1])?.focus(); }
  if (e.key === 'Home') { e.preventDefault(); items[0]?.focus(); }
  if (e.key === 'End')  { e.preventDefault(); items[items.length - 1]?.focus(); }
  if (e.key === 'Enter' || e.key === ' ') {
    const el = document.activeElement;
    if (el?.classList.contains('menuitem')) el.click();
  }
});

window.addEventListener('resize', () => { if (isMenuOpen()) placeActionsMenu(); });
window.addEventListener('scroll',  () => { if (isMenuOpen()) placeActionsMenu(); }, { passive: true });




  // ===== Adaptive texts (right + left), live-resizing and content updates
  function fitTextById(id, {max=12, min=7} = {}) {
    const el = document.getElementById(id);
    if (!el) return;
    const box = el.parentElement || el;
    let size = max;
    el.style.fontSize = size + 'px';
    const maxH = parseFloat(getComputedStyle(el).maxHeight) || Infinity;

    // downscale while overflowing width or max height
    while ((el.scrollWidth > box.clientWidth || el.scrollHeight > maxH) && size > min) {
      size--;
      el.style.fontSize = size + 'px';
    }
  }
  function runFooterFit(){
    fitTextById('bjornStatus', {max:12, min:7});
    fitTextById('bjornSay',    {max:12, min:7});
    fitTextById('bjornStatus2',{max:12, min:7});
  }

  // ===== Bottombar (Grid layout for proper centering)
  let bottombar = $('.bottombar');
  if (!bottombar) {
    // 3-column grid layout: left | center | right
    bottombar = el('footer', { class: 'bottombar', id: 'bottombar' }, [

      // LEFT
// LEFT
el('div', { class: 'status-left' }, [
  el('span', { class: 'pill status-pill', style: 'display:inline-flex;align-items:center;gap:6px' }, [
    el('img', { id: 'bjornStatusImage', alt: 'Status image', style: 'width:40px;height:40px;border-radius:6px;background:#222;flex:0 0 auto' })
  ]),
  // ⬇️ wrapper that stacks the two lines
  el('div', { class: 'status-text' }, [
    el('div', { id: 'bjornStatus',  class: 'bjorn-status'  }, 'Initializing...'),
    el('div', { id: 'bjornStatus2', class: 'bjorn-status2' }, '.')
  ])
]),

      // CENTER (grid column, not absolute)
      el('div', { class: 'status-center' }, [
        el('span', { class: 'status-character' }, [
          el('img', { id: 'bjorncharacter', alt: 'Bjorn', style: 'width:50px;height:50px;border-radius:6px;cursor:pointer;flex-shrink:0' })
        ])
      ]),

      // RIGHT
      el('div', { class: 'status-right' }, [
        el('span', { id: 'bjornSay', class: 'bjorn-say' }, 'Do bots get existential crises? Asking for a friend.'),

      ])

    ]);
    document.body.appendChild(bottombar);

    // init topbar widget
    if (window.BjornUI?.BjornTopbar?.init) {
      BjornUI.BjornTopbar.init();
    }
  }

  // live fit on load & resize
  window.addEventListener('load', runFooterFit);
  window.addEventListener('resize', runFooterFit);

  // observe size changes of columns and content changes
  (function setupFooterObservers(){
    const left  = document.querySelector('.status-left');
    const right = document.querySelector('.status-right');
    const ro = new ResizeObserver(runFooterFit);
    left && ro.observe(left);
    right && ro.observe(right);
['bjornStatus','bjornSay','bjornStatus2'].forEach(id=>{
      const el = document.getElementById(id);
      if (!el) return;
      ro.observe(el);
      new MutationObserver(runFooterFit).observe(el, { childList:true, characterData:true, subtree:true });
    });
    const imgs = [document.getElementById('bjornStatusImage'), document.getElementById('bjorncharacter')];
    imgs.forEach(img=>{
      if (!img) return;
      if (img.complete) runFooterFit();
      else img.addEventListener('load', runFooterFit, { once:true });
    });
  })();

  // ===== Generic modal (for Wi-Fi/Bluetooth prompts)
  let sysBackdrop = $('#sysDialogBackdrop');
  if(!sysBackdrop){
    sysBackdrop = el('div',{class:'modal-backdrop',id:'sysDialogBackdrop','aria-hidden':'true'});
    document.body.appendChild(sysBackdrop);
  }
  const sysDialog = {
    open(contentHTML, onSubmit){
      sysBackdrop.innerHTML='';
      const content = el('div',{class:'modal',role:'dialog','aria-modal':'true','aria-label':'System dialog'});
      content.innerHTML = contentHTML;
      sysBackdrop.appendChild(content);
      sysBackdrop.style.display='flex';
      setTimeout(()=>content.classList.add('show'),0);
      sysBackdrop.setAttribute('aria-hidden','false');

      const form = content.querySelector('form');
      const cancel = content.querySelector('[data-cancel]');
      const close = ()=>{ sysBackdrop.style.display='none'; sysBackdrop.setAttribute('aria-hidden','true'); };
      cancel?.addEventListener('click',(e)=>{ e.preventDefault(); close(); });
      form?.addEventListener('submit',(e)=>{
        e.preventDefault();
        const fd = new FormData(form);
        const data = Object.fromEntries(fd.entries());
        onSubmit?.(data, close);
      });
      sysBackdrop.addEventListener('click',e=>{ if(e.target===sysBackdrop) close(); },{once:true});
      document.addEventListener('keydown',function esc(e){ if(e.key==='Escape'){ close(); document.removeEventListener('keydown',esc); }},{once:true});
    }
  };



(async function(){
  // Safeguard: wait DOM if script is in <head> without "defer"
  if(!document.body){
    await new Promise(r=>document.addEventListener('DOMContentLoaded', r, {once:true}));
  }
if (window.__BJORN_QP_INIT__) return;
window.__BJORN_QP_INIT__ = true;

  // ===== Utilities (unchanged)
  const $  = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const el = (tag,attrs={},children=[])=>{
    const n=document.createElement(tag);
    for(const [k,v] of Object.entries(attrs)){
      if(k==='class') n.className=v;
      else if(k==='style') n.style.cssText=v;
      else if(k.startsWith('on')&&typeof v==='function') n.addEventListener(k.slice(2),v);
      else if(v!==null&&v!==undefined) n.setAttribute(k,v);
    }
    if(!Array.isArray(children)) children = children ? [children] : [];
    children.forEach(c=> n.append(c?.nodeType?c:document.createTextNode(c)));
    return n;
  };
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  const uid = (p='id')=>`${p}-${Math.random().toString(36).slice(2,9)}`;

  // ===== Config loader and API setup (unchanged)
(async function(){
  // Safeguard: wait DOM if script is in <head> without "defer"
  if(!document.body){
    await new Promise(r=>document.addEventListener('DOMContentLoaded', r, {once:true}));
  }
  if(window.__BJORN_INIT__) return; window.__BJORN_INIT__ = true;

  // ===== Utilities
  const $  = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const el = (tag,attrs={},children=[])=>{
    const n=document.createElement(tag);
    for(const [k,v] of Object.entries(attrs)){
      if(k==='class') n.className=v;
      else if(k==='style') n.style.cssText=v;
      else if(k.startsWith('on')&&typeof v==='function') n.addEventListener(k.slice(2),v);
      else if(v!==null&&v!==undefined) n.setAttribute(k,v);
    }
    if(!Array.isArray(children)) children = children ? [children] : [];
    children.forEach(c=> n.append(c?.nodeType?c:document.createTextNode(c)));
    return n;
  };
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  const uid = (p='id')=>`${p}-${Math.random().toString(36).slice(2,9)}`;

  // ... [Config loader and API setup unchanged] ...

  // ===== Enhanced Modern Quickpanel with iOS/Android style =====
let qp = $('#quickpanel');
if(!qp){
  // Add modern quickpanel styles
  const qpStyles = el('style', {}, `
    /* Modern Quickpanel Styles */
    .quickpanel {
      position: fixed;
      left: 0;
      right: 0;
      width: min(720px, 92vw);
      margin: 0 auto;
      top: -88vh;
      height: 85vh;
      background: linear-gradient(180deg,
        rgba(14,23,23,.98) 0%,
        rgba(10,16,16,.98) 100%);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid rgba(0,255,154,.15);
      border-top: none;
      border-radius: 0 0 24px 24px;
      box-shadow: 0 10px 40px rgba(0,255,154,.2);
      z-index: 50;
      transition: transform .35s cubic-bezier(.4,0,.2,1);
      transform: translateY(0);
      overscroll-behavior: contain;
    }
    .quickpanel.open { transform: translateY(85vh); height: auto; }

    .qp-handle {
      position: sticky; top: 0; height: 36px;
      display: flex; align-items: center; justify-content: center;
      cursor: grab; touch-action: pan-y;
      background: rgba(0,0,0,.2);
      border-radius: 24px 24px 0 0;
    }
    .qp-handle-bar {
      width: 36px; height: 5px; border-radius: 3px;
      background: linear-gradient(90deg, transparent, rgba(0,255,154,.4), transparent);
      box-shadow: 0 0 10px rgba(0,255,154,.6);
    }

    .qp-header {
      padding: 16px 20px;
      background: rgba(0,0,0,.3);
      border-bottom: 1px solid rgba(0,255,154,.1);
    }
    .qp-title { font-size: 20px; font-weight: 600; color: var(--acid); margin: 0; }
    .qp-subtitle { font-size: 12px; color: var(--muted); margin-top: 4px; }

    /* Tabs */
    .qp-tabs {
      display: flex; gap: 8px;
      padding: 10px 16px 0 16px;
      background: rgba(0,0,0,.15);
      border-bottom: 1px solid rgba(0,255,154,.08);
    }
    .qp-tab {
      appearance: none; border: 1px solid rgba(0,255,154,.15);
      background: rgba(0,255,154,.08);
      color: var(--acid);
      padding: 8px 14px; font-size: 13px; font-weight: 600;
      border-radius: 999px; cursor: pointer;
      transition: transform .15s ease, background .2s ease, box-shadow .2s ease;
      display: inline-flex; align-items: center; gap: 8px;
    }
    .qp-tab .tab-ico { width: 16px; height: 16px; display: inline-block; }
    .qp-tab:hover { transform: translateY(-1px); background: rgba(0,255,154,.14); }
    .qp-tab[aria-selected="true"] {
      background: rgba(0,255,154,.22);
      box-shadow: 0 0 12px rgba(0,255,154,.25) inset;
      border-color: rgba(0,255,154,.35);
    }

    .qp-content {
      padding: 16px;
      height: calc(100% - 200px); /* header + tabs height */
      scrollbar-width: thin;
      scrollbar-color: rgba(0,255,154,.3) transparent;
    }
    .qp-pane { display: none; }
    .qp-pane.active { display: block; }

    /* Network Tile */
    .network-tile {
      background: rgba(18,33,33,.6);
      border: 1px solid rgba(0,255,154,.1);
      border-radius: 16px;
      padding: 16px; margin-bottom: 16px;
      transition: all .2s ease;
    }
    .network-tile:hover {
      background: rgba(18,33,33,.8);
      border-color: rgba(0,255,154,.2);
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(0,255,154,.15);
    }
    .network-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 16px;
    }
    .network-title {
      display: flex; align-items: center; gap: 12px;
      font-size: 16px; font-weight: 600; color: var(--ink);
    }
    .network-icon {
      width: 60px; height: 60px; padding: 8px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
    }

    /* iOS Toggle Switch */
    .ios-switch {
      position: relative; width: 51px; height: 31px;
      background: rgba(120,120,128,.16);
      border-radius: 31px; cursor: pointer; transition: background .3s ease;
    }
    .ios-switch.on { background: var(--acid); }
    .ios-switch::after {
      content: ''; position: absolute; top: 2px; left: 2px;
      width: 27px; height: 27px; background: white; border-radius: 27px;
      box-shadow: 0 3px 8px rgba(0,0,0,.15);
      transition: transform .3s cubic-bezier(.4,0,.2,1);
    }
    .ios-switch.on::after { transform: translateX(20px); }

    /* Auto-scan toggle */
    .auto-scan-toggle {
      display: flex; align-items: center; gap: 8px;
      padding: 6px 12px; background: rgba(0,255,154,.1);
      border: 1px solid rgba(0,255,154,.2); border-radius: 20px;
      font-size: 12px; color: var(--acid);
      cursor: pointer; transition: all .2s ease;
    }
    .auto-scan-toggle.active { background: rgba(0,255,154,.2); animation: pulse 2s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.7} }

    /* Quick Actions Bar */
    .quick-actions {
      display: flex; gap: 8px; margin-bottom: 12px;
      overflow-x: auto; padding-bottom: 4px; scrollbar-width: none; align-items: center;
    }
    .quick-actions::-webkit-scrollbar { display: none; }
    .action-btn {
      flex-shrink: 0; padding: 8px 16px;
      background: rgba(0,255,154,.1); border: 1px solid rgba(0,255,154,.2);
      border-radius: 20px; color: var(--acid); font-size: 13px; font-weight: 500;
      cursor: pointer; transition: all .2s ease; white-space: nowrap;
    }
    .action-btn:hover { background: rgba(0,255,154,.2); transform: scale(1.05); }
    .action-btn:active { transform: scale(.98); }
    .action-btn.scanning { animation: pulse 1s infinite; }

    /* Network list & cards */
    .network-list { display: flex; flex-direction: column; gap: 10px; max-height: 400px; overflow-y: auto; padding-right: 4px; }
    .net-card {
      background: rgba(10,16,16,.6); border: 1px solid rgba(0,255,154,.08);
      border-radius: 12px; padding: 20px;
      display: flex; align-items: center; justify-content: space-between;
      cursor: pointer; transition: all .2s ease; position: relative;
    }
    .net-card:hover { background: rgba(10,16,16,.8); border-color: rgba(0,255,154,.2); transform: translateX(4px); }
    .net-card.connected {
      background: linear-gradient(90deg, rgba(0,255,154,.08) 0%, rgba(0,255,154,.03) 100%);
      border-color: rgba(0,255,154,.3);
    }
    .net-card.connected::before {
      content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
      background: var(--acid); box-shadow: 0 0 10px var(--acid);
    }
    .net-card.known { border-left: 2px solid rgba(24,240,255,.5); }
    .net-info { flex: 1; display: flex; flex-direction: column; gap: 6px; }
    .net-name { font-size: 14px; font-weight: 500; color: var(--ink); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .net-meta { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--muted); }

    /* Badges */
    .badge-modern {
      padding: 2px 8px; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.1);
      border-radius: 10px; font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .5px;
    }
    .badge-open { background: rgba(0,255,154,.15); border-color: rgba(0,255,154,.4); color: var(--acid); }
    .badge-wpa,.badge-wpa2,.badge-wpa3 { background: rgba(24,240,255,.15); border-color: rgba(24,240,255,.4); color: var(--acid-2); }
    .badge-wep { background: rgba(255,209,102,.15); border-color: rgba(255,209,102,.4); color: var(--warning); }
    .badge-known { background: rgba(255,255,255,.05); border-color: rgba(255,255,255,.15); color: var(--muted); }
    .badge-priority { background: rgba(255,138,0,.15); border-color: rgba(255,138,0,.4); color: #ff8a00; font-weight: 600; }

    /* Signal indicator */
    .signal-indicator { display: flex; align-items: flex-end; gap: 2px; height: 16px; }
    .signal-bar { width: 3px; background: rgba(255,255,255,.15); border-radius: 2px; transition: all .3s ease; }
    .signal-bar:nth-child(1){height:4px} .signal-bar:nth-child(2){height:7px}
    .signal-bar:nth-child(3){height:10px} .signal-bar:nth-child(4){height:13px}
    .signal-bar:nth-child(5){height:16px}
    .signal-bar.active { background: var(--sig-color, var(--acid)); box-shadow: 0 0 4px var(--sig-color, var(--acid)); }
    .sig-excellent{--sig-color:#00ff9a} .sig-good{--sig-color:#18f0ff}
    .sig-fair{--sig-color:#ffd166} .sig-poor{--sig-color:#ff8a00} .sig-weak{--sig-color:#ff3b3b}

    /* Actions */
    .net-action {
      padding: 6px 12px; background: rgba(0,255,154,.1);
      border: 1px solid rgba(0,255,154,.2); border-radius: 8px;
      color: var(--acid); font-size: 12px; font-weight: 500; cursor: pointer; transition: all .2s ease;
    }
    .net-action:hover { background: rgba(0,255,154,.2); transform: scale(1.05); }
    .net-action:disabled { opacity: .4; cursor: not-allowed; }
    .net-action.danger { background: rgba(255,59,59,.1); border-color: rgba(255,59,59,.2); color: var(--danger); }
    .net-action.danger:hover { background: rgba(255,59,59,.2); }

    /* Bluetooth status dots */
    .bt-status { display: flex; align-items: center; gap: 6px; }
    .bt-indicator { width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,.2); }
    .bt-indicator.connected { background: var(--acid); box-shadow: 0 0 8px var(--acid); }
    .bt-indicator.paired { background: var(--acid-2); box-shadow: 0 0 8px var(--acid-2); }
    .bt-indicator.trusted { background: var(--warning); box-shadow: 0 0 8px var(--warning); }

    /* Modal enhanced */
    .modal-enhanced {
      background: linear-gradient(180deg, rgba(14,23,23,.98) 0%, rgba(10,16,16,.98) 100%);
      backdrop-filter: blur(16px); border: 1px solid rgba(0,255,154,.2);
      border-radius: 16px; padding: 20px; max-width: 500px; margin: 0 auto;
      box-shadow: 0 20px 60px rgba(0,255,154,.3);
    }
    .modal-enhanced h3 { color: var(--acid); margin-bottom: 16px; }
    .modal-enhanced input {
      width: 100%; padding: 10px; background: rgba(18,33,33,.6);
      color: var(--ink); border: 1px solid rgba(0,255,154,.2); border-radius: 8px; margin: 8px 0 16px;
    }
    .modal-enhanced input:focus { outline: none; border-color: var(--acid); box-shadow: 0 0 10px rgba(0,255,154,.3); }

    /* Mobile tweaks */
    @media (max-width: 768px) {
      .quickpanel { height: 75vh; }
      .quickpanel.open {  height:auto; }
      .network-tile { padding: 12px; }
      .quick-actions { gap: 6px; }
      .action-btn { padding: 6px 12px; font-size: 12px; }
      .quickpanel { width: 100vw; margin: 0; }
    }
  `);
  document.head.appendChild(qpStyles);

  // Panel structure with Tabs
  qp = el('section',{class:'quickpanel',id:'quickpanel'},[
    el('div',{class:'qp-handle',id:'qpHandle'},[
      el('div',{class:'qp-handle-bar'})
    ]),
    el('div',{class:'qp-header'},[
      el('div',{class:'qp-head-left'},[
        el('h2',{class:'qp-title', id:'qpTitle'},'Network Control'),
        el('div',{class:'qp-subtitle'},'Manage your connections')
      ]),
      el('button',{
        class:'qp-close',
        id:'qpClose',
        'aria-label':'Close network panel',
        title:'Close (Esc)'
      }, '✕')
    ]),

    // Tabs bar
    el('div',{class:'qp-tabs',role:'tablist','aria-label':'Network tabs'},[
      el('button',{class:'qp-tab', id:'tabWifi', role:'tab','aria-selected':'true','aria-controls':'pane-wifi', tabindex:'0'},[
        el('img',{class:'tab-ico', src:'/web/images/wifi.png', alt:''}),
        'Wi-Fi'
      ]),
      el('button',{class:'qp-tab', id:'tabBt', role:'tab','aria-selected':'false','aria-controls':'pane-bt', tabindex:'-1'},[
        el('img',{class:'tab-ico', src:'/web/images/bluetooth.png', alt:''}),
        'Bluetooth'
      ])
    ]),

    el('div',{class:'qp-content'},[
      // Wi-Fi pane (default active)
      el('div',{class:'qp-pane active', id:'pane-wifi', role:'tabpanel','aria-labelledby':'tabWifi'},[
        el('div',{class:'network-tile',id:'wifiTile'},[
          el('div',{class:'network-header'},[
            el('div',{class:'network-title'},[
              el('div',{class:'network-icon'},[
                el('img',{src:'/web/images/wifi.png',alt:'Wi-Fi',width:'50',height:'50'})
              ]),
              'Wi-Fi'
            ]),
                        el('div',{class:'auto-scan-toggle',id:'wifiAutoScan'},[
              el('span',{},'Auto-scan'),
              el('span',{id:'wifiAutoScanStatus'},'OFF')
            ]),
            el('div',{class:'ios-switch on',id:'wifiSwitch',role:'switch','aria-label':'Wi-Fi'})
          ]),
          el('div',{class:'quick-actions'},[
            el('button',{class:'action-btn',id:'wifiScan'},'Scan'),
            el('button',{class:'action-btn',id:'wifiKnown'},'Saved Networks'),
            el('button',{class:'action-btn',id:'wifiPot'},'Import Potfiles'),
            el('button',{class:'action-btn',id:'wifiUp',title:'Increase priority'},'Priority ↑'),
            el('button',{class:'action-btn',id:'wifiDown',title:'Decrease priority'},'Priority ↓'),

          ]),
          el('div',{class:'network-list',id:'wifiList'})
        ])
      ]),

      // Bluetooth pane
      el('div',{class:'qp-pane', id:'pane-bt', role:'tabpanel','aria-labelledby':'tabBt'},[
        el('div',{class:'network-tile',id:'btTile'},[
          el('div',{class:'network-header'},[
            el('div',{class:'network-title'},[
              el('div',{class:'network-icon'},[
                el('img',{src:'/web/images/bluetooth.png',alt:'Bluetooth',width:'50',height:'50'})
              ]),
              'Bluetooth'
            ]),
            el('div',{class:'ios-switch',id:'btSwitch',role:'switch','aria-label':'Bluetooth'})
          ]),
          el('div',{class:'quick-actions'},[
            el('button',{class:'action-btn',id:'btScan'},'Discover'),
            el('div',{class:'auto-scan-toggle',id:'btAutoScan'},[
              el('span',{},'Auto-scan'),
              el('span',{id:'btAutoScanStatus'},'OFF')
            ])
          ]),
          el('div',{class:'network-list',id:'btList'})
        ])
      ])
    ])
  ]);
  document.body.appendChild(qp);
}
document.getElementById('qpClose')?.addEventListener('click', () => qpShow(false));

/* ==== Tabs wiring (Wi-Fi default) ==== */
(function wireQpTabs(){
  const wifiTab  = document.getElementById('tabWifi');
  const btTab    = document.getElementById('tabBt');
  const wifiPane = document.getElementById('pane-wifi');
  const btPane   = document.getElementById('pane-bt');

  if (!wifiTab || !btTab || !wifiPane || !btPane) return;

  function setTab(which){
    const isWifi = which === 'wifi';

    // selected states
    wifiTab.setAttribute('aria-selected', String(isWifi));
    btTab.setAttribute('aria-selected', String(!isWifi));
    wifiTab.tabIndex = isWifi ? 0 : -1;
    btTab.tabIndex   = isWifi ? -1 : 0;

    // panes
    wifiPane.classList.toggle('active', isWifi);
    btPane.classList.toggle('active', !isWifi);

    // focus for accessibility
    (isWifi ? wifiTab : btTab).focus({preventScroll:true});

    // trigger scans when switching
    try{
      if (isWifi) {
        if (typeof scanWifi === 'function') scanWifi();
      } else {
        if (typeof scanBt === 'function') scanBt();
      }
    }catch{}
  }

  wifiTab.addEventListener('click', () => setTab('wifi'));
  btTab.addEventListener('click',   () => setTab('bt'));

  // Keyboard navigation for tabs (Left/Right/Home/End)
  const onKey = (e)=>{
    const keys = ['ArrowLeft','ArrowRight','Home','End'];
    if (!keys.includes(e.key)) return;
    e.preventDefault();
    const curIsWifi = wifiTab.getAttribute('aria-selected') === 'true';
    if (e.key === 'ArrowRight' || e.key === 'End') setTab(curIsWifi ? 'bt' : 'bt');
    if (e.key === 'ArrowLeft'  || e.key === 'Home') setTab(curIsWifi ? 'wifi' : 'wifi');
  };
  wifiTab.addEventListener('keydown', onKey);
  btTab.addEventListener('keydown', onKey);

  // Default tab: Wi-Fi
  setTab('wifi');
})();


function enableQpOutsideClose(){
  const qp = document.getElementById('quickpanel');
  const openBtn = document.getElementById('openQuick');
  if (!qp) return;

  const shouldClose = (target) => {
    if (!qp.classList.contains('open')) return false;
    if (qp.contains(target)) return false;
    if (openBtn && openBtn.contains(target)) return false;
    return true;
  };

  // Gestionnaire unique pour éviter les conflits
  const handleOutsideClick = (e) => {
    if (shouldClose(e.target)) {
      e.preventDefault();
      e.stopPropagation();
      qpShow(false);
    }
  };

  document.addEventListener('click', handleOutsideClick, true);
  document.addEventListener('touchend', handleOutsideClick, { passive: false, capture: true });
}

// Remplacez l'appel existant par :
document.getElementById('qpClose')?.addEventListener('click', (e) => {
  e.preventDefault();
  qpShow(false);
});

enableQpOutsideClose();

  // ======= Enhanced Wi-Fi & Bluetooth Management =======
  const wifiList = $('#wifiList');
  const btList   = $('#btList');
  const wifiSwitch = $('#wifiSwitch');
  const btSwitch   = $('#btSwitch');
  const wifiState = { 
    enabled: true, 
    current: null, 
    known: new Map(), // Map for priority tracking
    networks: [],
    autoScan: false,
    autoScanInterval: null
  };
  const btState = { 
    enabled: false, 
    devices: [],
    autoScan: false,
    autoScanInterval: null
  };

  // Enhanced toast function
  const toast = (msg, type = 'info', duration = 2600) => {
    const toastEl = el('div',{
      class:`toast toast-${type}`,
      style:`background: ${
        type === 'success' ? 'rgba(0,255,154,.2)' :
        type === 'error' ? 'rgba(255,59,59,.2)' :
        type === 'warning' ? 'rgba(255,209,102,.2)' :
        'rgba(24,240,255,.2)'
      }; border-color: ${
        type === 'success' ? 'rgba(0,255,154,.5)' :
        type === 'error' ? 'rgba(255,59,59,.5)' :
        type === 'warning' ? 'rgba(255,209,102,.5)' :
        'rgba(24,240,255,.5)'
      };`
    });
    toastEl.innerHTML = msg;
    const toastBox = $('#toasts') || document.body;
    toastBox.appendChild(toastEl);
    setTimeout(()=> {
      toastEl.style.transition='transform .2s ease, opacity .2s';
      toastEl.style.transform='translateY(10px)';
      toastEl.style.opacity='0';
      setTimeout(()=>toastEl.remove(),220);
    }, duration);
  };

  // Signal strength calculation with proper color coding
  const getSignalInfo = (dbm) => {
    if (dbm === undefined || dbm === null) return { bars: 1, strength: 'weak', color: 'var(--danger)' };
    
    const level = parseInt(dbm);
    if (level >= -50) return { bars: 5, strength: 'excellent', color: '#00ff9a' };
    if (level >= -60) return { bars: 4, strength: 'good', color: '#18f0ff' };
    if (level >= -70) return { bars: 3, strength: 'fair', color: '#ffd166' };
    if (level >= -80) return { bars: 2, strength: 'poor', color: '#ff8a00' };
    return { bars: 1, strength: 'weak', color: '#ff3b3b' };
  };

  // Create signal indicator element
  const createSignalIndicator = (dbm) => {
    const info = getSignalInfo(dbm);
    const indicator = el('div', { 
      class: `signal-indicator sig-${info.strength}`,
      style: `--sig-color: ${info.color}`,
      title: `Signal: ${dbm || '?'} dBm`
    });
    
    for (let i = 1; i <= 5; i++) {
      indicator.appendChild(
        el('div', { class: `signal-bar ${i <= info.bars ? 'active' : ''}` })
      );
    }
    
    return indicator;
  };

  // Parse security string properly
  const parseSecurityType = (security) => {
    if (!security) return { type: 'OPEN', badge: 'badge-open', label: 'OPEN' };
    
    const upper = security.toUpperCase();
    if (upper.includes('WPA3')) return { type: 'WPA3', badge: 'badge-wpa3', label: 'WPA3' };
    if (upper.includes('WPA2')) return { type: 'WPA2', badge: 'badge-wpa2', label: 'WPA2' };
    if (upper.includes('WPA')) return { type: 'WPA', badge: 'badge-wpa', label: 'WPA' };
    if (upper.includes('WEP')) return { type: 'WEP', badge: 'badge-wep', label: 'WEP' };
    if (upper === 'OPEN' || upper === '--') return { type: 'OPEN', badge: 'badge-open', label: 'OPEN' };
    
    return { type: 'UNKNOWN', badge: 'badge-wpa', label: security };
  };

  // Fetch known Wi-Fi networks with priorities
  async function fetchKnownWifi(){
    try {
      const r = await fetch('/get_known_wifi', {cache:'no-store'});
      const j = await r.json();
      wifiState.known.clear();
      (j.known_networks||[]).forEach(n => {
        wifiState.known.set(n.ssid, n.priority || 0);
      });
    } catch(e){ 
      console.error('getKnownWifi', e);
    }
  }

  // Enhanced Wi-Fi scan with proper sorting
const scanWifi = async () => {
    if (!wifiState.enabled) {
      toast('Wi-Fi is disabled', 'warning');
      return;
    };
    
    const btn = $('#wifiScan');
    btn?.classList.add('scanning');
    
    try {
      await fetchKnownWifi();
      const r = await fetch('/scan_wifi', { cache: 'no-store' });
      const j = await r.json();
      wifiState.current = j.current_ssid || null;
      wifiState.networks = j.networks || [];
      
      wifiList.innerHTML = '';
      
      // Sort networks by: 1. Connected, 2. Priority (known), 3. Signal strength
      const sortedNetworks = wifiState.networks
        .map(net => ({
          ...net,
          isKnown: wifiState.known.has(net.ssid),
          priority: wifiState.known.get(net.ssid) || 0,
          isCurrent: wifiState.current === net.ssid
        }))
        .sort((a, b) => {
          // Connected network always first
          if (a.isCurrent) return -1;
          if (b.isCurrent) return 1;
          
          // Then by priority (higher first)
          if (a.priority !== b.priority) return b.priority - a.priority;
          
          // Then by signal strength
          return (b.signal_level || -100) - (a.signal_level || -100);
        });
      
      sortedNetworks.forEach((net, index) => {
        const ssid = net.ssid || '(hidden)';
        const security = parseSecurityType(net.security);
        
        const card = el('div', { 
          class: `net-card ${net.isCurrent ? 'connected' : ''} ${net.isKnown ? 'known' : ''}`,
          'data-ssid': ssid,
          'data-index': index
        });
        
        const info = el('div', { class: 'net-info' });
        const nameRow = el('div', { class: 'net-name' });
        
        nameRow.appendChild(document.createTextNode(ssid));
        
        if (net.isCurrent) {
          nameRow.appendChild(el('span', { 
            class: 'badge-modern',
            style: 'background: rgba(0,255,154,.2); border-color: rgba(0,255,154,.5); color: var(--acid)' 
          }, '● Connected'));
        }
        
        const metaRow = el('div', { class: 'net-meta' });
        
        // Security badge
        metaRow.appendChild(el('span', { 
          class: `badge-modern ${security.badge}` 
        }, security.label));
        
        // Known badge with priority
        if (net.isKnown) {
          metaRow.appendChild(el('span', { 
            class: 'badge-modern badge-known' 
          }, 'Saved'));
          
          if (net.priority > 0) {
            metaRow.appendChild(el('span', { 
              class: 'badge-modern badge-priority' 
            }, `P${net.priority}`));
          }
        }
        
        // Channel info
        if (net.channel) {
          metaRow.appendChild(el('span', { 
            class: 'badge-modern' 
          }, `CH ${net.channel}`));
        }
        
        // BSSID
        if (net.bssid) {
          metaRow.appendChild(el('span', { 
            class: 'badge-modern',
            style: 'font-size: 9px; opacity: 0.7;'
          }, net.bssid));
        }
        
        info.appendChild(nameRow);
        info.appendChild(metaRow);
        card.appendChild(info);
        
        // Signal indicator with proper level
        card.appendChild(createSignalIndicator(net.signal_level));
        
        // Action button
        const actionBtn = el('button', { 
          class: 'net-action',
          disabled: !wifiState.enabled 
        }, net.isCurrent ? 'Connected' : 'Connect');
        
        if (!net.isCurrent) {
          actionBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await connectToWifi(net);
          });
        }
        
        card.appendChild(actionBtn);
        wifiList.appendChild(card);
      });
      
      toast(`Found ${sortedNetworks.length} networks`, 'success', 1800);
      
    } catch (e) {
      console.error('scanWifi', e);
      toast('Wi-Fi scan failed', 'error');
    } finally {
      btn?.classList.remove('scanning');
    }
  }

  // Connect to Wi-Fi with improved flow
  async function connectToWifi(net) {
    const ssid = net.ssid;
    const security = parseSecurityType(net.security);
    
    try {
      // Try known network first
      if (net.isKnown) {
        const rk = await fetch('/connect_known_wifi', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ssid })
        });
        const jk = await rk.json();
        if (jk.status === 'success') {
          toast(`Connected to ${ssid}`, 'success');
          scanWifi();
          return;
        }
      }

      // If secured, ask for password
      if (security.type !== 'OPEN') {
        const dialog = el('div',{class:'modal-enhanced'});
        dialog.innerHTML = `
          <form>
            <h3>Connect to Wi-Fi</h3>
            <div style="margin-bottom:12px;">
              <strong>Network:</strong> ${ssid}<br>
              <strong>Security:</strong> ${security.label}
            </div>
            <label style="display:block; margin-bottom:8px; color:var(--muted);">Password</label>
            <input name="password" type="password" required placeholder="Enter password..." 
                   autocomplete="off" minlength="8"/>
            <div style="display:flex; gap:8px; justify-content:flex-end;">
              <button class="net-action danger" type="button" data-cancel>Cancel</button>
              <button class="net-action" type="submit">Connect</button>
            </div>
          </form>
        `;
        
        const backdrop = $('#sysDialogBackdrop') || el('div',{class:'modal-backdrop',id:'sysDialogBackdrop'});
        backdrop.innerHTML = '';
        backdrop.appendChild(dialog);
        backdrop.style.display = 'flex';
        document.body.appendChild(backdrop);
        
        const form = dialog.querySelector('form');
        const input = dialog.querySelector('input');
        const cancelBtn = dialog.querySelector('[data-cancel]');
        
        const closeDialog = () => {
          backdrop.style.display = 'none';
        };
        
        cancelBtn.addEventListener('click', closeDialog);
        
        form.addEventListener('submit', async (e) => {
          e.preventDefault();
          const password = input.value;
          
          if (password.length < 8) {
            toast('Password must be at least 8 characters', 'warning');
            return;
          }
          
          try {
            const r = await fetch('/connect_wifi', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ ssid, password })
            });
            const j = await r.json();
            
            if (j.status === 'success') {
              toast(`Connected to ${ssid}`, 'success');
              closeDialog();
              scanWifi();
            } else {
              toast(j.message || 'Connection failed', 'error');
            }
          } catch (err) {
            toast('Connection error', 'error');
          }
        });
        
        setTimeout(() => input.focus(), 100);
        
      } else {
        // Open network
        const r = await fetch('/connect_wifi', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ssid })
        });
        const j = await r.json();
        
        if (j.status === 'success') {
          toast(`Connected to ${ssid}`, 'success');
          scanWifi();
        } else {
          toast(j.message || 'Connection failed', 'error');
        }
      }
    } catch (e) {
      console.error('connectToWifi', e);
      toast('Connection error', 'error');
    }
  }

  // Priority management
  async function wifiPriorityUpDown(dir) {
    if (!wifiState.current) {
      toast('No network connected', 'warning');
      return;
    }
    
    const currentPriority = wifiState.known.get(wifiState.current) || 0;
    const newPriority = Math.max(0, currentPriority + dir);
    
    try {
      const r = await fetch('/update_wifi_priority', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          ssid: wifiState.current, 
          priority: newPriority 
        })
      });
      const j = await r.json();
      
      if (j.status === 'success') {
        toast(`Priority ${dir > 0 ? 'increased' : 'decreased'} to ${newPriority}`, 'success');
        scanWifi();
      } else {
        toast(j.message || 'Priority update failed', 'error');
      }
    } catch (e) {
      console.error('update_priority', e);
      toast('Priority update error', 'error');
    }
  }

  // Enhanced Bluetooth scan with device states
const scanBt = async () => {
    if (!btState.enabled) {
      toast('Bluetooth is disabled', 'warning');
      return;
    };
    
    const btn = $('#btScan');
    btn?.classList.add('scanning');
    
    try {
      const r = await fetch('/scan_bluetooth', { cache: 'no-store' });
      const j = await r.json();
      btState.devices = j.devices || [];
      
      btList.innerHTML = '';
      
      // Sort devices: connected first, then paired, then by name
      const sortedDevices = btState.devices.sort((a, b) => {
        if (a.connected !== b.connected) return a.connected ? -1 : 1;
        if (a.paired !== b.paired) return a.paired ? -1 : 1;
        if (a.trusted !== b.trusted) return a.trusted ? -1 : 1;
        return (a.name || '').localeCompare(b.name || '');
      });
      
      sortedDevices.forEach(dev => {
        const { name = 'Unknown Device', address, paired, trusted, connected, rssi } = dev;
        
        const card = el('div', { 
          class: `net-card ${connected ? 'connected' : ''}`,
          'data-address': address 
        });
        
        const info = el('div', { class: 'net-info' });
        const nameRow = el('div', { class: 'net-name' });
        
        // Device name with status
        nameRow.appendChild(document.createTextNode(name));
        
        // Status indicators
        const statusDiv = el('div', { class: 'bt-status' });
        
        if (connected) {
          statusDiv.appendChild(el('div', { 
            class: 'bt-indicator connected',
            title: 'Connected'
          }));
        }
        if (paired) {
          statusDiv.appendChild(el('div', { 
            class: 'bt-indicator paired',
            title: 'Paired'
          }));
        }
        if (trusted) {
          statusDiv.appendChild(el('div', { 
            class: 'bt-indicator trusted',
            title: 'Trusted'
          }));
        }
        
        nameRow.appendChild(statusDiv);
        
        const metaRow = el('div', { class: 'net-meta' });
        metaRow.appendChild(el('span', { class: 'badge-modern' }, address));
        
        if (connected) {
          metaRow.appendChild(el('span', { 
            class: 'badge-modern',
            style: 'background: rgba(0,255,154,.2); border-color: rgba(0,255,154,.5); color: var(--acid)'
          }, 'Connected'));
        } else if (paired) {
          metaRow.appendChild(el('span', { 
            class: 'badge-modern badge-known' 
          }, 'Paired'));
        }
        
        if (trusted) {
          metaRow.appendChild(el('span', { 
            class: 'badge-modern badge-priority' 
          }, 'Trusted'));
        }
        
        info.appendChild(nameRow);
        info.appendChild(metaRow);
        card.appendChild(info);
        
        // Signal indicator for Bluetooth RSSI
        card.appendChild(createSignalIndicator(rssi || -70));
        
        // Action buttons based on device state
        const actionsDiv = el('div', { 
          style: 'display:flex; gap:6px;' 
        });
        
        if (connected) {
          actionsDiv.appendChild(el('button', { 
            class: 'net-action danger',
            onclick: () => doDisconnect(address, name)
          }, 'Disconnect'));
        } else if (paired && trusted) {
          actionsDiv.appendChild(el('button', { 
            class: 'net-action',
            onclick: () => doConnect(address, name)
          }, 'Connect'));
        } else if (paired && !trusted) {
          actionsDiv.appendChild(el('button', { 
            class: 'net-action',
            onclick: () => doTrust(address, name)
          }, 'Trust'));
        } else {
          actionsDiv.appendChild(el('button', { 
            class: 'net-action',
            onclick: () => doPair(address, name)
          }, 'Pair'));
        }
        
        if (paired || trusted) {
          actionsDiv.appendChild(el('button', { 
            class: 'net-action danger',
            onclick: () => doForget(address, name)
          }, 'Forget'));
        }
        
        card.appendChild(actionsDiv);
        btList.appendChild(card);
      });
      
      toast(`Found ${sortedDevices.length} devices`, 'success', 1800);
      
    } catch (e) {
      console.error('scanBluetooth', e);
      toast('Bluetooth scan failed', 'error');
    } finally {
      btn?.classList.remove('scanning');
    }
  }

  // Bluetooth actions with proper error handling
  async function doPair(address, name) {
    try {
      toast(`Pairing with ${name}...`, 'info');
      
      const r = await fetch('/pair_bluetooth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address })
      });
      const j = await r.json();
      
      if (j.status === 'needs_pin') {
        const pin = prompt(`Enter PIN for ${name}:`);
        if (!pin) return;
        
        const rp = await fetch('/pair_bluetooth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ address, pin })
        });
        const jp = await rp.json();
        
        if (jp.status === 'success' || jp.status === 'partial') {
          toast(`Paired with ${name}`, 'success');
          await doTrust(address, name);
        } else {
          toast(jp.message || 'Pairing failed', 'error');
        }
      } else if (j.status === 'needs_confirmation') {
        if (confirm(`Accept pairing with ${name}?`)) {
          const rc = await fetch('/pair_bluetooth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address, confirm: true })
          });
          const jc = await rc.json();
          
          if (jc.status === 'success') {
            toast(`Paired with ${name}`, 'success');
            await doTrust(address, name);
          } else {
            toast(jc.message || 'Pairing failed', 'error');
          }
        }
      } else if (j.status === 'success') {
        toast(`Paired with ${name}`, 'success');
        await doTrust(address, name);
      } else {
        toast(j.message || 'Pairing failed', 'error');
      }
      
      scanBt();
    } catch (e) {
      console.error('pair', e);
      toast('Pairing error', 'error');
    }
  }

  async function doTrust(address, name) {
    try {
      const r = await fetch('/trust_bluetooth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address })
      });
      const j = await r.json();
      
      if (j.status === 'success') {
        toast(`${name} is now trusted`, 'success');
      } else {
        toast(j.message || 'Trust failed', 'error');
      }
      
      scanBt();
    } catch (e) {
      console.error('trust', e);
      toast('Trust error', 'error');
    }
  }

  async function doConnect(address, name) {
    try {
      toast(`Connecting to ${name}...`, 'info');
      
      const r = await fetch('/connect_bluetooth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address })
      });
      const j = await r.json();
      
      if (j.status === 'success') {
        toast(`Connected to ${name}`, 'success');
      } else {
        toast(j.message || 'Connection failed', 'error');
      }
      
      scanBt();
    } catch (e) {
      console.error('connect', e);
      toast('Connection error', 'error');
    }
  }

  async function doDisconnect(address, name) {
    try {
      const r = await fetch('/disconnect_bluetooth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address })
      });
      const j = await r.json();
      
      if (j.status === 'success') {
        toast(`Disconnected from ${name}`, 'success');
      } else {
        toast(j.message || 'Disconnect failed', 'error');
      }
      
      scanBt();
    } catch (e) {
      console.error('disconnect', e);
      toast('Disconnect error', 'error');
    }
  }

  async function doForget(address, name) {
    if (!confirm(`Forget ${name}?`)) return;
    
    try {
      const r = await fetch('/forget_bluetooth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address })
      });
      const j = await r.json();
      
      if (j.status === 'success') {
        toast(`${name} forgotten`, 'success');
      } else {
        toast(j.message || 'Forget failed', 'error');
      }
      
      scanBt();
    } catch (e) {
      console.error('forget', e);
      toast('Forget error', 'error');
    }
  }

  // Auto-scan functionality
  function toggleWifiAutoScan() {
    wifiState.autoScan = !wifiState.autoScan;
    const toggle = $('#wifiAutoScan');
    const status = $('#wifiAutoScanStatus');
    
    if (wifiState.autoScan) {
      toggle.classList.add('active');
      status.textContent = 'ON';
      
      // Start auto-scanning every 30 seconds
      wifiState.autoScanInterval = setInterval(() => {
        if (wifiState.enabled) scanWifi();
      }, 30000);
      
      toast('Wi-Fi auto-scan enabled (30s)', 'success');
      scanWifi(); // Initial scan
    } else {
      toggle.classList.remove('active');
      status.textContent = 'OFF';
      
      if (wifiState.autoScanInterval) {
        clearInterval(wifiState.autoScanInterval);
        wifiState.autoScanInterval = null;
      }
      
      toast('Wi-Fi auto-scan disabled', 'info');
    }
  }

  function toggleBtAutoScan() {
    btState.autoScan = !btState.autoScan;
    const toggle = $('#btAutoScan');
    const status = $('#btAutoScanStatus');
    
    if (btState.autoScan) {
      toggle.classList.add('active');
      status.textContent = 'ON';
      
      // Start auto-scanning every 30 seconds
      btState.autoScanInterval = setInterval(() => {
        if (btState.enabled) scanBt();
      }, 30000);
      
      toast('Bluetooth auto-scan enabled (30s)', 'success');
      scanBt(); // Initial scan
    } else {
      toggle.classList.remove('active');
      status.textContent = 'OFF';
      
      if (btState.autoScanInterval) {
        clearInterval(btState.autoScanInterval);
        btState.autoScanInterval = null;
      }
      
      toast('Bluetooth auto-scan disabled', 'info');
    }
  }

  // Known Wi-Fi management dialog
  async function openKnownWifi() {
    try {
      const r = await fetch('/get_known_wifi', { cache: 'no-store' });
      const j = await r.json();
      
      const dialog = el('div', { class: 'modal-enhanced', style: 'max-width: 600px;' });
      
      const rows = (j.known_networks || [])
        .sort((a, b) => (b.priority || 0) - (a.priority || 0))
        .map(k => `
          <tr>
            <td style="color:var(--ink)">${k.ssid}</td>
            <td>
              <input type="number" value="${k.priority || 0}" min="0" max="999" 
                     style="width:80px; background:rgba(18,33,33,.6); color:var(--ink); 
                            border:1px solid rgba(0,255,154,.2); border-radius:6px; 
                            padding:4px 8px;" data-ssid="${k.ssid}">
            </td>
            <td style="text-align:right">
              <button class="net-action" data-act="connect" data-ssid="${k.ssid}">Connect</button>
              <button class="net-action" data-act="save" data-ssid="${k.ssid}">Save</button>
              <button class="net-action danger" data-act="del" data-ssid="${k.ssid}">Delete</button>
            </td>
          </tr>`).join('');
      
      dialog.innerHTML = `
        <h3>Saved Wi-Fi Networks</h3>
        <div style="max-height:400px; overflow:auto;">
          <table style="width:100%; border-collapse:collapse;">
            <thead>
              <tr style="border-bottom:1px solid rgba(0,255,154,.2)">
                <th style="text-align:left; padding:8px; color:var(--acid)">SSID</th>
                <th style="padding:8px; color:var(--acid)">Priority</th>
                <th style="text-align:right; padding:8px; color:var(--acid)">Actions</th>
              </tr>
            </thead>
            <tbody>${rows || '<tr><td colspan="3" style="text-align:center; padding:20px; color:var(--muted)">No saved networks</td></tr>'}</tbody>
          </table>
        </div>
        <div style="display:flex; gap:8px; margin-top:16px; justify-content:space-between;">
          <button class="net-action" id="btnImportPot">Import Potfiles</button>
          <button class="net-action danger" data-cancel>Close</button>
        </div>
      `;
      
      const backdrop = $('#sysDialogBackdrop') || el('div',{class:'modal-backdrop',id:'sysDialogBackdrop'});
      backdrop.innerHTML = '';
      backdrop.appendChild(dialog);
      backdrop.style.display = 'flex';
      document.body.appendChild(backdrop);
      
      // Event handlers
      dialog.querySelector('#btnImportPot')?.addEventListener('click', async () => {
        try {
          const r = await fetch('/import_potfiles', { method: 'POST' });
          const j = await r.json();
          toast(j.message || 'Potfiles imported', j.status === 'success' ? 'success' : 'error');
          if (j.status === 'success') {
            backdrop.style.display = 'none';
            openKnownWifi(); // Refresh
          }
        } catch (e) {
          toast('Import failed', 'error');
        }
      });
      
      dialog.querySelectorAll('[data-act="connect"]').forEach(b => {
        b.addEventListener('click', async () => {
          const ssid = b.dataset.ssid;
          const r = await fetch('/connect_known_wifi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ssid })
          });
          const j = await r.json();
          
          if (j.status === 'success') {
            toast(`Connected to ${ssid}`, 'success');
            backdrop.style.display = 'none';
            scanWifi();
          } else {
            toast(j.message || 'Connection failed', 'error');
          }
        });
      });
      
      dialog.querySelectorAll('[data-act="save"]').forEach(b => {
        b.addEventListener('click', async () => {
          const ssid = b.dataset.ssid;
          const input = dialog.querySelector(`input[data-ssid="${CSS.escape(ssid)}"]`);
          const priority = parseInt(input.value, 10) || 0;
          
          const r = await fetch('/update_wifi_priority', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ssid, priority })
          });
          const j = await r.json();
          
          toast(j.message || 'Priority updated', j.status === 'success' ? 'success' : 'error');
        });
      });
      
      dialog.querySelectorAll('[data-act="del"]').forEach(b => {
        b.addEventListener('click', async () => {
          const ssid = b.dataset.ssid;
          if (!confirm(`Delete "${ssid}"?`)) return;
          
          const r = await fetch('/delete_known_wifi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ssid })
          });
          const j = await r.json();
          
          if (j.status === 'success') {
            toast('Network deleted', 'success');
            backdrop.style.display = 'none';
            openKnownWifi(); // Refresh
          } else {
            toast(j.message || 'Delete failed', 'error');
          }
        });
      });
      
      dialog.querySelector('[data-cancel]')?.addEventListener('click', () => {
        backdrop.style.display = 'none';
      });
      
    } catch (e) {
      console.error('known_wifi', e);
      toast('Error loading saved networks', 'error');
    }
  }

  // Wire up switches and buttons
  wifiSwitch?.addEventListener('click', () => {
    wifiSwitch.classList.toggle('on');
    wifiState.enabled = wifiSwitch.classList.contains('on');
    
    if (!wifiState.enabled) {
      wifiState.current = null;
      wifiList.innerHTML = '<div style="text-align:center; color:var(--muted); padding:20px;">Wi-Fi is disabled</div>';
      
      // Stop auto-scan if running
      if (wifiState.autoScan) {
        toggleWifiAutoScan();
      }
    } else {
      scanWifi();
    }
  });

  btSwitch?.addEventListener('click', () => {
    btSwitch.classList.toggle('on');
    btState.enabled = btSwitch.classList.contains('on');
    
    if (!btState.enabled) {
      btList.innerHTML = '<div style="text-align:center; color:var(--muted); padding:20px;">Bluetooth is disabled</div>';
      
      // Stop auto-scan if running
      if (btState.autoScan) {
        toggleBtAutoScan();
      }
    } else {
      scanBt();
    }
  });

  // Action buttons
  $('#wifiScan')?.addEventListener('click', scanWifi);
  $('#wifiKnown')?.addEventListener('click', openKnownWifi);
  $('#wifiPot')?.addEventListener('click', async () => {
    try {
      const r = await fetch('/import_potfiles', { method: 'POST' });
      const j = await r.json();
      toast(j.message || 'Potfiles imported', j.status === 'success' ? 'success' : 'error');
      if (j.status === 'success') scanWifi();
    } catch (e) {
      toast('Import failed', 'error');
    }
  });
  
  $('#wifiUp')?.addEventListener('click', () => wifiPriorityUpDown(+1));
  $('#wifiDown')?.addEventListener('click', () => wifiPriorityUpDown(-1));
  $('#wifiAutoScan')?.addEventListener('click', toggleWifiAutoScan);
  
  $('#btScan')?.addEventListener('click', scanBt);
  $('#btAutoScan')?.addEventListener('click', toggleBtAutoScan);

  // Quickpanel mechanics with smooth animations
  let qpOpen = false;
  let qpStartY = 0;
  let qpDragY = 0;
  
function qpShow(show) {
  qpOpen = !!show;
  
  // Nettoyer tout style inline avant de changer les classes
  qp.style.transform = '';
  qp.style.transition = '';
  
  // Toggle la classe avec un petit délai pour assurer la transition
  requestAnimationFrame(() => {
    qp.classList.toggle('open', show);
    
    if (show && !qp.dataset.initialized) {
      qp.dataset.initialized = 'true';
      setTimeout(() => {
        if (wifiState.enabled) scanWifi();
        if (btState.enabled) scanBt();
      }, 300);
    }
  });
}
window.Bjorn = window.Bjorn || {};
window.Bjorn.qpShow = qpShow;


  // Touch and mouse drag handling
const qpHandle = $('#qpHandle');

function qpRatio(){
  const h = qp.getBoundingClientRect().height || (window.innerHeight * 0.85);
  return h / window.innerHeight;
}

const drag = {
  onStart(y) {
    qp.style.transition = 'none';
    qpStartY = y;
    const rect = qp.getBoundingClientRect();
    qpDragY = rect.top;
  },
  onMove(y) {
    const dy = y - qpStartY;
    const r = qpRatio();
    const limitTop = -window.innerHeight * r;
    const newY = Math.max(limitTop, Math.min(0, qpDragY + dy));
    qp.style.transform = `translateY(${newY * -1}px)`;
  },
  onEnd(y) {
    // IMPORTANT: Toujours nettoyer le transform à la fin
    qp.style.transition = '';
    qp.style.transform = ''; // ← Réinitialise le transform
    
    const dy = y - qpStartY;
    const threshold = 50; // pixels de seuil pour déclencher l'ouverture/fermeture
    
    if (qpOpen) {
      // Si ouvert, fermer seulement si drag vers le haut > threshold
      qpShow(dy > -threshold);
    } else {
      // Si fermé, ouvrir seulement si drag vers le bas > threshold
      qpShow(dy > threshold);
    }
  }
};


  qpHandle?.addEventListener('touchstart', e => drag.onStart(e.touches[0].clientY), { passive: true });
  qpHandle?.addEventListener('touchmove', e => drag.onMove(e.touches[0].clientY), { passive: true });
  qpHandle?.addEventListener('touchend', e => drag.onEnd(e.changedTouches[0].clientY));
  
  qpHandle?.addEventListener('mousedown', e => {
    drag.onStart(e.clientY);
    const mm = ev => drag.onMove(ev.clientY);
    const mu = ev => {
      drag.onEnd(ev.clientY);
      window.removeEventListener('mousemove', mm);
      window.removeEventListener('mouseup', mu);
    };
    window.addEventListener('mousemove', mm);
    window.addEventListener('mouseup', mu);
  });

  // Open quickpanel button
$('#openQuick')?.addEventListener('click', () => {
  console.debug('[Quickpanel] openQuick clicked');
  qpShow(true);
});
  // Raccourcis clavier (ESC, Ctrl+` console, Ctrl+\ quickpanel)
document.addEventListener('keydown', (e) => {
  // ESC -> ferme tout ce qui doit l'être
  if (e.key === 'Escape') {
    try { closeSettings?.(); } catch {}
    try { qpShow(false); } catch {}
    try { closeConsole?.(); } catch {}
    try {
      launcher?.classList?.remove('show');
      launcher?.setAttribute?.('aria-hidden','true');
      document.getElementById('actionsMenu')?.classList?.remove('show');
    } catch {}
  }

  // Raccourci Console
  const kc = (window.cfg && window.cfg.shortcuts && window.cfg.shortcuts.console) || { ctrl:true, key:'`' };
  if (kc.ctrl && e.ctrlKey && e.key === kc.key) {
    e.preventDefault();
    try { openConsole?.(); } catch {}
  }

  // Raccourci Quickpanel
  const kq = (window.cfg && window.cfg.shortcuts && window.cfg.shortcuts.quickpanel) || { ctrl:true, key:'\\' };
  if (kq.ctrl && e.ctrlKey && e.key === kq.key) {
    e.preventDefault();
    try { qpShow(!qpOpen); } catch {}
  }
});

})();
  

})();


  

  // ===== Toasts container
  let toastBox = $('#toasts'); if(!toastBox){ toastBox = el('div',{class:'toasts',id:'toasts'}); document.body.appendChild(toastBox); }
  const _innerToast=(html,ms=2600)=>{ const t=el('div',{class:'toast'}); t.innerHTML=html; toastBox.appendChild(t); setTimeout(()=>{ t.style.transition='transform .2s ease, opacity .2s'; t.style.transform='translateY(10px)'; t.style.opacity='0'; setTimeout(()=>t.remove(),220); }, ms); };
  // bridge: make a generic global toast and ensure Bjorn.toast points to it
  window.Bjorn = window.Bjorn || {};
  if (!window.Bjorn.toast) window.Bjorn.toast = _innerToast;
  if (!window.toast) window.toast = (msg, ms=2600) => window.Bjorn.toast(msg, ms);

  // ===== Console
// ===== Console
let consoleEl = $('#console');
if(!consoleEl){
  consoleEl = el('section',{class:'console',id:'console'},[
    el('div',{class:'console-resize',id:'consoleResize',title:'Resize'}),
    (function(){
      const bar = el('div',{class:'attackbar',id:'attackBar'});
      bar.append(
        el('select',{id:'selIP'},[
          el('option',{},'192.168.1.10'),
          el('option',{},'192.168.1.75'),
          el('option',{},'10.0.0.42')
        ]),
        el('select',{id:'selPort'},[
          el('option',{},'Auto'),
          el('option',{},'22'),
          el('option',{},'80'),
          el('option',{},'443'),
          el('option',{},'8080')
        ]),
        el('select',{id:'selAction'},[
          el('option',{},'ARPspoof'),
          el('option',{},'PortScan'),
          el('option',{},'BruteSSH'),
          el('option',{},'HTTPProbe')
        ]),
        el('button',{class:'btn',id:'btnScan'},'Scanning'),
        el('button',{class:'btn',id:'btnAttack'},'Attack')
      );
      return bar;
    })(),

    el('div',{class:'console-head'},[
            el('span',{id:'modePill', class:'pill mode-pill manual', title:'Current mode'},[
        el('span',{class:'dot'}), 'Manual'
      ]),
     

      // Bulle d’état


      // Boutons existants
      el('button',{class:'btn',id:'modeToggle','aria-pressed':'true'},'Auto'),
      el('button',{class:'btn',id:'attackToggle'},'Attack ▾'),
      el('button',{class:'btn',id:'clearLogs'},'Clear'),
      el('button',{class:'btn',id:'closeConsole'},'X'),
      // Slider de police
      el('div',{id:'consoleFontRow', class:'console-fontrow'},[
        el('label',{'for':'consoleFont',class:'sr-only'},'Console font size'),
        el('input',{
          id:'consoleFont', type:'range', min:'2', max:'24', step:'1',
          value:'11', title:'Console font',
          'aria-label':'Console font size'
        })
      ]),
    ]),

    // SSE writes directly into #logout
    el('div',{class:'console-body',id:'logout'})
  ]);
  document.body.appendChild(consoleEl);
}




// ---- Chip Edit Sheet (reuses .sheet / .sheet-backdrop from global.css)
(function(){
  if (window.ChipsEditor) return;

  const html = `
    <div class="sheet-backdrop" id="chipEditBackdrop" aria-hidden="true">
      <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="chipEditTitle">
        <div class="sheet-head">
          <strong id="chipEditTitle">Edit value</strong>
          <span class="spacer"></span>
          <button class="btn" id="chipEditClose" aria-label="Close">✕</button>
        </div>
        <div class="sheet-body">
          <label class="field" style="gap:8px">
            <span id="chipEditLabel" class="helper">Value</span>
            <input id="chipEditInput" class="input" type="text" autocomplete="off" />
            <textarea id="chipEditTextarea" class="input" style="display:none;height:120px;resize:vertical"></textarea>
          </label>
        </div>
        <div class="sheet-foot">
          <button class="btn" id="chipEditCancel">Cancel</button>
          <button class="btn" id="chipEditSave">Save</button>
        </div>
      </div>
    </div>`;
  const wrap = document.createElement('div');
  wrap.innerHTML = html;
  document.body.appendChild(wrap.firstElementChild);

  const backdrop = document.getElementById('chipEditBackdrop');
  const title    = document.getElementById('chipEditTitle');
  const label    = document.getElementById('chipEditLabel');
  const input    = document.getElementById('chipEditInput');
  const ta       = document.getElementById('chipEditTextarea');
  const btnSave  = document.getElementById('chipEditSave');
  const btnCancel= document.getElementById('chipEditCancel');
  const btnClose = document.getElementById('chipEditClose');

  let resolver = null;
  function show(){ backdrop.classList.add('show'); requestAnimationFrame(()=> (input.offsetParent ? input : ta).focus()); }
  function hide(){ backdrop.classList.remove('show'); resolver = null; }

  function currentValue(){
    return (input.offsetParent ? input.value : ta.value).trim();
  }

  function resolve(val){ if (resolver){ resolver(val); hide(); } }
  function save(){ resolve(currentValue()); }
  function cancel(){ resolve(null); }

  btnSave.addEventListener('click', save);
  btnCancel.addEventListener('click', cancel);
  btnClose.addEventListener('click', cancel);
  backdrop.addEventListener('click', (e)=>{ if (e.target === backdrop) cancel(); });
  document.addEventListener('keydown', (e)=>{
    if (!backdrop.classList.contains('show')) return;
    if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    if (e.key === 'Enter' && e.target.closest('#chipEditBackdrop') && e.target.id !== 'chipEditTextarea') {
      // Enter confirms (except in textarea)
      e.preventDefault(); save();
    }
  });

  // Public API
  window.ChipsEditor = {
    /**
     * Open editor and resolve with string or null (cancel).
     * @param {Object} opts
     *  - value        : initial text
     *  - title        : modal title
     *  - label        : field label
     *  - placeholder  : placeholder text
     *  - multiline    : use textarea
     *  - maxLength    : optional maxlength
     *  - confirmLabel : Save button text
     */
    open(opts={}){
      const { value='', title:ttl='Edit value', label:lab='Value', placeholder='', multiline=false, maxLength, confirmLabel='Save' } = opts;
      title.textContent = ttl;
      label.textContent = lab;
      btnSave.textContent = confirmLabel;
      if (multiline) {
        ta.style.display = '';
        input.style.display = 'none';
        ta.value = value;
        ta.placeholder = placeholder;
        ta.removeAttribute('maxlength');
        if (maxLength) ta.setAttribute('maxlength', String(maxLength));
      } else {
        input.style.display = '';
        ta.style.display = 'none';
        input.value = value;
        input.placeholder = placeholder;
        input.removeAttribute('maxlength');
        if (maxLength) input.setAttribute('maxlength', String(maxLength));
      }
      show();
      return new Promise(res => { resolver = res; });
    }
  };
})();

 
// ===== Settings modal (tabs) — unchanged visually
let backdrop = $('#settingsBackdrop');
if(!backdrop){
  backdrop = el('div',{class:'modal-backdrop',id:'settingsBackdrop','aria-hidden':'true'},[
    el('div',{class:'modal',role:'dialog','aria-modal':'true','aria-label':'Settings'},[
      (function(){ const nav = el('nav',{class:'tabs',id:'settingsTabs'}); nav.append(
        el('button',{class:'tabbtn active','data-tab':'general'},'General'),
        el('button',{class:'tabbtn','data-tab':'theme'},'Theme') ); return nav; })(),
      el('section',{class:'tabpanel',id:'tab-general'},[
        el('h3',{},'General'),
        el('div',{class:'row'},[el('label',{},'Notifications'), el('div',{class:'switch',id:'switchNotifs'})]),
      ]),
    el('section',{class:'tabpanel',id:'tab-theme',hidden:''},[
      el('h3',{},'Theme'),
      el('div',{class:'row'},[
        el('button',{class:'btn','data-theme':'acid'},'Acid'),
        el('button',{class:'btn','data-theme':'cyan'},'Cyan'),
        el('button',{class:'btn','data-theme':'amber'},'Amber')
      ])
    ]),

    ])
  ]);
  document.body.appendChild(backdrop);
}

/* ========= Bjorn.SettingsConfig — mount generateConfigForm into Settings ========= */
(function () {
  const $  = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));

  // -------- Generic Chips system with in-app editor --------
  if (!window.Chips) {
    const makeChip = (text) => {
      const b = document.createElement('div');
      b.className = 'chip';
      b.innerHTML = `<span>${text}</span><button class="chip-close" aria-label="Remove">×</button>`;
      return b;
    };

    // Add via Enter or comma (,)
    document.addEventListener('keydown', (e)=>{
      const inp = e.target;
      if (!(inp instanceof HTMLInputElement)) return;
      const host = inp.closest('.chips-input');
      if (!host) return;

      if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        const raw = inp.value.trim().replace(/,$/,'');
        if (!raw) return;
        const values = raw.split(',').map(v=>v.trim()).filter(Boolean);
        const list = host.parentElement.querySelector('.chips, .chip-list') || host.parentElement;
        const existing = new Set(Array.from(list.querySelectorAll('.chip span')).map(s=>s.textContent));

        values.forEach(v=>{
          if (existing.has(v)) { toast(`"${v}" already exists`); return; }
          list.insertBefore(makeChip(v), host);
        });
        inp.value = '';
      }
    });

    // Remove chip
    document.addEventListener('click',(e)=>{
      const btn = e.target.closest('.chip-close');
      if (btn) btn.closest('.chip')?.remove();
    });

    // Edit chip (using ChipsEditor)
    document.addEventListener('click', async (e)=>{
      const chip = e.target.closest('.chip');
      if (!chip || e.target.closest('.chip-close')) return;

      const span = chip.querySelector('span');
      const cur  = span.textContent;
      const list = chip.parentElement; // .chips/.chip-list
      const isSingle = !!chip.closest('.chip-field');

      const neu = await window.ChipsEditor.open({
        value: cur,
        title: 'Edit value',
        label: 'Value',
        placeholder: 'Type a value…',
        multiline: false
      });
      if (neu === null) return;            // cancelled
      const val = neu.trim();
      if (!val) { chip.remove(); return; } // empty => remove

      // dedupe in same container
      const exists = Array.from(list.querySelectorAll('.chip span'))
        .some(s => s !== span && s.textContent === val);
      if (exists) { toast(`"${val}" already exists`); return; }

      span.textContent = val;

      if (isSingle) {
        Array.from(list.querySelectorAll('.chip'))
          .filter(c => c !== chip).forEach(c => c.remove());
      }
    });

    // Single-value: Enter replaces existing chip
    document.addEventListener('keydown',(e)=>{
      const inp = e.target;
      if (!(inp instanceof HTMLInputElement)) return;
      const field = inp.closest('.chip-field');
      if (!field || e.key !== 'Enter') return;
      e.preventDefault();
      const v = inp.value.trim();
      if(!v) return;
      const list = field.querySelector('.chip-list') || field;
      const old = list.querySelector('.chip');
      if (old) old.remove();
      list.appendChild(makeChip(v));
      inp.value = '';
    });

    window.Chips = {
      values: (root) => Array.from(root.querySelectorAll('.chip span')).map(s=>s.textContent),
      setValues: (root, arr=[]) => {
        Array.from(root.querySelectorAll('.chip')).forEach(c=>c.remove());
        const list = root.querySelector('.chips, .chip-list') || root;
        arr.forEach(v=>list.appendChild(makeChip(v)));
      }
    };
  }

  // 1) Insert “Config” tab if missing
  const tabs = $('#settingsTabs');
  const modal = $('#settingsBackdrop .modal');
  if (tabs && !tabs.querySelector('[data-tab="config"]')) {
    const btn = document.createElement('button');
    btn.className = 'tabbtn';
    btn.dataset.tab = 'config';
    btn.textContent = 'Config';
    const aboutBtn = tabs.querySelector('[data-tab="about"]');
    tabs.insertBefore(btn, aboutBtn || null);

    const panel = document.createElement('section');
    panel.className = 'tabpanel';
    panel.id = 'tab-config';
    panel.hidden = true;
    panel.innerHTML = `
      <div style="display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-bottom:8px">
        <button class="btn" id="cfgReload">Reload</button>
        <button class="btn" id="cfgRestore">Restore Defaults</button>
        <button class="btn" id="cfgSave">Save</button>
      </div>
      <div id="configFormHost" class="grid-stack" style="max-height:55vh;overflow:auto;"></div>
    `;
    modal?.appendChild(panel);
  }

  // 2) API + helpers
  const SEL = {
    host: '#configFormHost',
    save: '#cfgSave',
    restore: '#cfgRestore',
    reload: '#cfgReload',
    tabs: '#settingsTabs',
  };
  const API = {
    load: '/load_config',
    save: '/save_config',
    restore: '/restore_default_config'
  };
  const _el = (tag, attrs={}, children=[]) => {
    const n = document.createElement(tag);
    for (const [k,v] of Object.entries(attrs)) {
      if (k==='class') n.className = v;
      else if (k==='style' && typeof v==='object') Object.assign(n.style, v);
      else if (k==='style') n.style.cssText = v;
      else n.setAttribute(k, v);
    }
    (Array.isArray(children)?children:[children]).filter(Boolean).forEach(c=>{
      n.append(c.nodeType?c:document.createTextNode(c));
    });
    return n;
  };

  // 3) UI builders (generalized)
  function createCard(title) {
    const card = _el('div', { class: 'card' });
    const header = _el('div', { class: 'card-header' });
    header.innerHTML = `<h3 class="card-title">${String(title).replace('__title_','').replace('__','')}</h3>`;
    card.append(header, _el('div', { style: 'height:8px' }));
    return card;
  }

  function createSwitchItem(key, value){
    const wrap = _el('div', { class: 'row-toggle' });
    wrap.innerHTML = `
      <label for="${key}">${key}</label>
      <label class="toggle">
        <input type="checkbox" id="${key}" name="${key}" ${value ? 'checked' : ''}>
        <span class="slider"></span>
      </label>`;
    return wrap;
  }
// 1) Presets by key (exact) + by pattern (regex)
// --- Constraints by key (min/max/step) ---
// 1) ranges (unchanged)
const RANGES = {
  // delays & timings
  web_delay:                  { min: 0,    max: 10000, step: 1     },
  screen_delay:               { min: 0,    max: 10,    step: 0.1   },
  startup_delay:              { min: 0,    max: 600,   step: 0.1   },
  startup_splash_duration:    { min: 0,    max: 60,    step: 0.1   },
  fullrefresh_delay:          { min: 0,    max: 3600,  step: 1     },
  image_display_delaymin:     { min: 0,    max: 600,   step: 0.1   },
  image_display_delaymax:     { min: 0,    max: 600,   step: 0.1   },
  comment_delaymin:           { min: 0,    max: 600,   step: 0.1   },
  comment_delaymax:           { min: 0,    max: 600,   step: 0.1   },
  shared_update_interval:     { min: 1,    max: 86400, step: 1     },
  livestatus_delay:           { min: 0,    max: 600,   step: 0.1   },

  // sizes / ports
  ref_width:                  { min: 32,   max: 1024,  step: 1     },
  ref_height:                 { min: 32,   max: 1024,  step: 1     },
  vuln_max_ports:             { min: 1,    max: 65535, step: 1     },
  portstart:                  { min: 0,    max: 65535, step: 1     },
  portend:                    { min: 0,    max: 65535, step: 1     },

  // timelines
  frise_default_x:            { min: 0,    max: 2000,  step: 1     },
  frise_default_y:            { min: 0,    max: 2000,  step: 1     },
  frise_epd2in7_x:            { min: 0,    max: 2000,  step: 1     },
  frise_epd2in7_y:            { min: 0,    max: 2000,  step: 1     },

  // misc
  semaphore_slots:            { min: 1,    max: 128,   step: 1     },
  line_spacing:               { min: 0,    max: 10,    step: 0.1   },
  vuln_update_interval:       { min: 1,    max: 86400, step: 1     }
};

// fallback
const DEFAULT_RANGE = { min: 0, max: 100, step: 1 };

// 2) simple resolution (known key → range; else friendly fallback)
function getRangeForKey(key, value){
  if (RANGES[key]) return RANGES[key];

  const v = Number(value);
  if (Number.isFinite(v)){
    if (v <= 10)   return { min: 0, max: 10,     step: 1 };
    if (v <= 100)  return { min: 0, max: 100,    step: 1 };
    if (v <= 1000) return { min: 0, max: 1000,   step: 1 };
    return { min: 0, max: Math.ceil(v * 2), step: Math.max(1, Math.round(v/100)) };
  }
  return DEFAULT_RANGE;
}

// 3) component: text (accepts comma) + slider (bounded)
function createNumberInputWithButtons(key, value) {
  const r = getRangeForKey(key, value);
  const id = key;

  const c = _el('div', { class: 'form-field' });
  c.innerHTML = `
    <label for="${id}">${key}</label>
    <div class="input-number-w-slider" data-min="${r.min}" data-max="${r.max}" data-step="${r.step}">
      <input type="range" min="${r.min}" max="${r.max}" step="${r.step}">
      <div class="updown">
        <button class="btn" type="button" data-act="dec" aria-label="Decrease">−</button>
        <!-- TEXT + inputmode=decimal for comma -->
        <input
          class="input input-number"
          type="text"
          id="${id}"
          name="${id}"
          inputmode="decimal"
          autocomplete="off"
          spellcheck="false"
        >
        <button class="btn" type="button" data-act="inc" aria-label="Increase">+</button>
      </div>
    </div>
  `;

  const wrap  = c.querySelector('.input-number-w-slider');
  const range = wrap.querySelector('input[type="range"]');
  const num   = wrap.querySelector('input[type="text"]');

  const step  = +wrap.dataset.step || 1;
  const min   = +wrap.dataset.min;
  const max   = +wrap.dataset.max;

  const clamp = (v)=> Math.min(max, Math.max(min, v));
  const parseNum = (raw) => {
    const s = String(raw ?? '').trim().replace(',', '.');
    if (s === '' || s === '-' || s === '.' || s === '-.') return NaN;
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : NaN;
  };
  const fmt = (n) => String(n).replace('.', ','); // FR display

  const paint = () => {
    const p = ((+range.value - min) * 100) / (max - min || 1);
    wrap.style.setProperty('--_fill', `${p}%`);
  };

  // init values
  (function init(){
    const v = parseNum(value);
    const cl = Number.isFinite(v) ? clamp(v) : min;
    num.value = Number.isFinite(v) ? fmt(v) : fmt(cl);
    range.value = cl;
    paint();
  })();

  // soft filter: digits, comma, dot, minus
  num.addEventListener('beforeinput', (e) => {
    if (!e.data) return;
    if (!/[\d.,\-]/.test(e.data)) e.preventDefault();
  });

  // input → update slider (clamped) but keep raw value (may overflow)
  const emit = (rawVal, clampedVal) => {
    wrap.dispatchEvent(new CustomEvent('valuechange', {
      detail: { value: rawVal, clamped: clampedVal }
    }));
  };

  const syncFromInput = () => {
    const v = parseNum(num.value);
    const cl = Number.isFinite(v) ? clamp(v) : clamp(0);
    range.value = cl;
    paint();
    emit(v, cl);
  };

  num.addEventListener('input', syncFromInput);
  num.addEventListener('change', () => {
    const v = parseNum(num.value);
    if (Number.isFinite(v)) num.value = fmt(v);  // normalize 0,3 etc.
    syncFromInput();
  });

  // slider → update field (always bounded)
  range.addEventListener('input', () => {
    num.value = fmt(parseFloat(range.value));
    paint();
    emit(parseNum(num.value), +range.value);
  });

  // +/- buttons (press & hold) — act on raw value
  const incBtn = wrap.querySelector('[data-act="inc"]');
  const decBtn = wrap.querySelector('[data-act="dec"]');

  const nudge = (dir) => {
    const v = parseNum(num.value);
    const base = Number.isFinite(v) ? v : +range.value;
    const nextRaw = +(base + dir * step).toFixed(10); // avoid float artifacts
    const nextCl  = clamp(nextRaw);
    num.value = fmt(nextRaw); // can exceed max
    range.value = nextCl;
    paint();
    emit(nextRaw, nextCl);
  };

  const hold = (btn, dir) => {
    let t; const go = () => nudge(dir);
    const down = (e) => { e.preventDefault(); go(); t = setInterval(go, 100); };
    const up   = () => clearInterval(t);
    btn.addEventListener('mousedown', down);
    btn.addEventListener('touchstart', down, { passive: false });
    ['mouseup','mouseleave','touchend','touchcancel'].forEach(ev => btn.addEventListener(ev, up));
  };
  hold(incBtn, +1);
  hold(decBtn, -1);

  return c;
}


  // Single-value chips field
  function createSingleValueField(key, value) {
    const c = _el('div', { class: 'chip-field' });
    c.innerHTML = `
      <label>${key}</label>
      <div class="chip-list">${(value??'')!=='' ? `<div class="chip"><span>${value}</span><button class="chip-close" aria-label="Remove">×</button></div>` : ''}</div>
      <div class="chips-input"><input type="text" placeholder="Set value…"></div>`;
    return c;
  }

  // Multi-values chips list
  function createListInput(key, values) {
    const c = _el('div', { class: 'form-list' });
    c.innerHTML = `
      <label>${key}</label>
      <div class="chips">
        ${(values||[]).map(v=>`<div class="chip"><span>${v}</span><button class="chip-close" aria-label="Remove">×</button></div>`).join('')}
      </div>
      <div class="chips-input"><input type="text" placeholder="Add values, comma-separated…"></div>
      <div class="align-end">
        <button type="button" class="btn" data-clear>Clear</button>
      </div>`;
    c.querySelector('[data-clear]')?.addEventListener('click', ()=>{
      $$('.chip', c).forEach(n=>n.remove());
    });
    return c;
  }

  // 4) render
  function render(cfg) {
    const host = $(SEL.host); if (!host) return;
    host.innerHTML = '';

    // Toggles card
    const togglesCard = createCard('Toggles');
    const togglesGrid = _el('div', { class: 'grid-auto-260' });
    // Other cards
    const cardsWrap = _el('div', { class: 'grid-auto-320' });
    let currentCard = null;

    for (const [key, value] of Object.entries(cfg)) {
      if (key.startsWith('__title_')) {
        if (currentCard) cardsWrap.appendChild(currentCard);
        currentCard = createCard(value);
        continue;
      }
      if (typeof value === 'boolean') {
        togglesGrid.appendChild(createSwitchItem(key, value));
      } else if (Array.isArray(value)) {
        currentCard && currentCard.appendChild(createListInput(key, value));
      } else if (typeof value === 'number') {
        currentCard && currentCard.appendChild(createNumberInputWithButtons(key, value));
      } else {
        currentCard && currentCard.appendChild(createSingleValueField(key, value));
      }
    }
    if (currentCard) cardsWrap.appendChild(currentCard);

    togglesCard.appendChild(togglesGrid);
    host.appendChild(togglesCard);
    host.appendChild(cardsWrap);
  }

  // 5) collect & persist (aligned with new classes)
  function collect() {
    const root = $(SEL.host);
    const data = {};
    // toggles
    $$('.row-toggle input[type="checkbox"]', root).forEach(cb => data[cb.id] = cb.checked);
    // multi lists
    $$('.form-list', root).forEach(cont => {
      const key = cont.querySelector('label')?.textContent?.trim();
      if (!key) return;
      data[key] = Chips.values(cont);
    });
    // single value
    $$('.chip-field', root).forEach(cont => {
      const key = cont.querySelector('label')?.textContent?.trim();
      if (!key) return;
      const vals = Chips.values(cont);
      if (vals[0] !== undefined) data[key] = vals[0];
    });
    // numbers
    $$('.form-field input[type="number"]', root).forEach(inp => {
      data[inp.id] = parseFloat(inp.value);
    });
    return data;
  }

  async function load() {
    try{
      const r = await fetch(API.load, { cache: 'no-store' });
      const j = await r.json();
      render(j);
      Bjorn?.setupNumberWithSlider?.(document);

    }catch(e){
      console.error('SettingsConfig.load', e);
      toast('Error loading config');
    }
  }
  async function save() {
    try{
      const payload = collect();
      const r = await fetch(API.save, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      await r.json();
      toast('Configuration saved');
    }catch(e){
      console.error('SettingsConfig.save', e);
      toast('Error saving configuration');
    }
  }
  async function restore() {
    try{
      const r = await fetch(API.restore);
      const j = await r.json();
      render(j);
      Bjorn?.setupNumberWithSlider?.(document);

      toast('Defaults restored');
    }catch(e){
      console.error('SettingsConfig.restore', e);
      toast('Error restoring defaults');
    }
  }

  // 6) Wiring
  $('#cfgSave')?.addEventListener('click', save);
  $('#cfgRestore')?.addEventListener('click', restore);
  $('#cfgReload')?.addEventListener('click', load);

  $('#settingsTabs')?.addEventListener('click', (e)=>{
    const b = e.target.closest('.tabbtn'); if(!b) return;
    if (b.dataset.tab === 'config') setTimeout(load, 0);
  });
  const openBtn = $('#openSettings');
  openBtn?.addEventListener('click', ()=>{
    const btn = $('#settingsTabs .tabbtn.active');
    const isConfig = btn && btn.dataset.tab === 'config';
    if (isConfig) setTimeout(load, 0);
  });

  // Expose
  window.Bjorn = window.Bjorn || {};
  window.Bjorn.SettingsConfig = { load, save, restore, render };
})();


  // ===== Sidebar buttons
  const sidebar = $('#sidebar');
  $('#toggleSidebar')?.addEventListener('click',()=> sidebar?.classList.toggle('hidden'));
  $('#hideSidebar')?.addEventListener('click',()=> sidebar?.classList.add('hidden'));

  // ===== Console behavior
  const logBadge = $('#logBadge');
  const toggleConsoleBtn = $('#bottombar');
  const attackBar = $('#attackBar');
  const attackToggle = $('#attackToggle');
  const modeToggle = $('#modeToggle');
  let unread = 0;

  const openConsole = ()=>{ 
    consoleEl.classList.add('open'); 
    unread = 0; 
    if (logBadge) logBadge.hidden = true;

    // align Attack panel with current mode
    (async () => {
      try {
        const t = await fetch('/check_manual_mode').then(r=>r.text());
        const isManual = (t === 'True');
        window.BjornUI?.ManualMode?.showAttack?.(isManual);
      } catch {
        const isManual =
          modeToggle?.textContent.trim() === 'Manual' ||
          modeToggle?.getAttribute('aria-pressed') === 'true';
        window.BjornUI?.ManualMode?.showAttack?.(!!isManual);
      }
    })();

    // start SSE on open
    window.BjornUI?.ConsoleSSE?.start?.();
  };

  const closeConsole = ()=>{ 
    consoleEl.classList.remove('open'); 
    // stop SSE on close
    window.BjornUI?.ConsoleSSE?.stop?.();
  };

  toggleConsoleBtn?.addEventListener('click',()=> 
    consoleEl.classList.contains('open') ? closeConsole() : openConsole()
  );
  $('#closeConsole')?.addEventListener('click', closeConsole);
  $('#clearLogs')?.addEventListener('click', ()=> { $('#logout').innerHTML=''; });

  (function setupConsoleFontSlider(){
    const inp = document.getElementById('consoleFont');
    if (!inp) return;

    // valeur initiale = ce que ConsoleSSE connaît
    const cur = (window.BjornUI?.ConsoleSSE ? undefined : undefined); // noop, on lit depuis storage
    try{
      const saved = parseInt(localStorage.getItem('Console.fontPx')||'',10);
      const base  = Number.isFinite(saved) ? saved : 11;
      inp.value = String(base);
      const min = +inp.min, max = +inp.max;
      inp.style.backgroundSize = `${((base - min) * 100) / (max - min)}% 100%`;
    }catch{}

    const apply = (v)=>{
      window.BjornUI?.ConsoleSSE?.setFont?.(v);
      // on reste en bas si la console est ouverte
      window.BjornUI?.ConsoleSSE?.forceBottom?.();
    };

    inp.addEventListener('input', e => apply(parseInt(e.target.value,10)));
  })();

  // delegate to ManualMode
  modeToggle?.addEventListener('click', (e)=>{
    e.preventDefault();
    window.BjornUI?.ManualMode?.toggle?.();
  });

  // user can force show/hide attack bar
  attackToggle?.addEventListener('click',()=>{
    const on = !consoleEl.classList.contains('with-attack');
    consoleEl.classList.toggle('with-attack', on);
    if(attackBar) attackBar.style.display = on ? 'flex' : 'none';
    attackToggle?.setAttribute('aria-expanded', String(on));
  });

  function log(msg){
    const out=$('#logout'); if(!out) return;
    const line=el('div',{class:'logline'});
    line.innerHTML=`[${new Date().toLocaleTimeString()}] ${msg}`;
    out.appendChild(line);
    out.scrollTop=out.scrollHeight;
    if(!consoleEl.classList.contains('open')){
      unread++; if(logBadge){ logBadge.textContent=String(unread); logBadge.hidden=false; }
    }
  }

// Resize console height by dragging
(function () {
  const res = $('#consoleResize'); if (!res) return;
  let startY = 0, startH = 0;

  const onMove = (e) => {
    const y = e.touches ? e.touches[0].clientY : e.clientY;
    const dy = startY - y;
    const nh = Math.min(window.innerHeight * 0.9,
                Math.max(window.innerHeight * 0.2, startH + dy));
    consoleEl.style.height = nh + 'px';
  };

  const onEnd = (e) => {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onEnd);
    window.removeEventListener('touchmove', onMove);
    window.removeEventListener('touchend', onEnd);

    // Laisse le layout se stabiliser, puis force le bas
    requestAnimationFrame(() => {
      window.BjornUI?.ConsoleSSE?.forceBottom?.();
    });
  };

  res.addEventListener('mousedown', (e) => {
    startY = e.clientY;
    startH = consoleEl.getBoundingClientRect().height;
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onEnd);
  });

  res.addEventListener('touchstart', (e) => {
    startY = e.touches[0].clientY;
    startH = consoleEl.getBoundingClientRect().height;
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('touchend', onEnd);
  }, { passive: true });


})();


// ===== Launcher (built from cfg)
// ===== Launcher (built from cfg)
// function buildLauncher() {
//   if (!cfg.launcher) return;

//   let launcher = document.getElementById('launcher');
//   if (!launcher) {
//     launcher = el('aside', { class: 'launcher', id: 'launcher', 'aria-hidden': 'true' });
//     const scroll = el('div', { class: 'launcher-scroll' });
//     launcher.appendChild(scroll);
//     document.body.appendChild(launcher);
//   }

//   const scroll = launcher.querySelector('.launcher-scroll');
//   scroll.innerHTML = '';

//   (cfg.pages || []).forEach(p => {
//     const a = el('a', {
//       class: 'lbtn',
//       href: p.href,
//       'data-tooltip': p.tooltip || ''
//     }, [
//       el('img', { src: p.icon, alt: p.alt || '' })
//     ]);
//     scroll.appendChild(a);
//   });
// }
// buildLauncher();
function buildLauncher() {
  if (!cfg.launcher) return;

  let launcher = document.getElementById('launcher');
  if (!launcher) {
    launcher = el('aside', { class: 'launcher', id: 'launcher', 'aria-hidden': 'true' });
    const scroll = el('div', { class: 'launcher-scroll' });
    launcher.appendChild(scroll);
    document.body.appendChild(launcher);
  }

  const scroll = launcher.querySelector('.launcher-scroll');
  scroll.innerHTML = '';

  (cfg.pages || []).forEach(p => {
    const a = el('a', {
      class: 'lbtn',
      href: p.href,
      'data-tooltip': p.tooltip || ''
    });

    // image
    const img = el('img', { src: p.icon, alt: p.alt || '' });

    // label sous l'image
    const label = el('div', { class: 'lbtn-label' }, [p.title || '']);

    // structure : image au-dessus, texte dessous
    a.appendChild(img);
    a.appendChild(label);

    scroll.appendChild(a);
  });
}
buildLauncher();



// Plus besoin de supprimer les attributs title car on n'en crée plus

// ===== Launcher: sticky, se ferme seulement sur clic/tap à l’extérieur =====
// ===== Launcher: sticky, se ferme uniquement au clic/tap à l'extérieur =====
(function () {
  const btn = document.getElementById('openLauncher');
  const launcher = document.getElementById('launcher');
  if (!btn || !launcher) return;

  // État
  let isOpen = launcher.classList.contains('show');
  let touchStartY = null;
  let touchMoved = false;
  let lastTouchEndTs = 0;

  function setOpen(v) {
    isOpen = !!v;
    launcher.classList.toggle('show', isOpen);
    launcher.setAttribute('aria-hidden', String(!isOpen));
  }
  function closeIfOutside(target) {
    if (!isOpen) return;
    if (!launcher.contains(target) && !btn.contains(target)) setOpen(false);
  }

  // Toggle manuel → ouvre en "sticky"
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    setOpen(!isOpen);
  });

  // --- Gestion tactile : ne pas fermer lors d'un scroll + tuer le ghost-click
  document.addEventListener('touchstart', (e) => {
    touchStartY = e.touches[0].clientY;
    touchMoved = false;
  }, { passive: true });

  document.addEventListener('touchmove', (e) => {
    if (touchStartY !== null) {
      const dy = Math.abs(e.touches[0].clientY - touchStartY);
      if (dy > 8) touchMoved = true; // seuil anti-tap
    }
  }, { passive: true });

  document.addEventListener('touchend', (e) => {
    lastTouchEndTs = Date.now();

    if (!isOpen) {
      touchStartY = null;
      touchMoved = false;
      return;
    }

    // si on a scrollé → ne ferme pas et évite le click synthétique
    if (touchMoved && e.cancelable) {
      e.preventDefault();
    } else {
      closeIfOutside(e.target);
    }

    touchStartY = null;
    touchMoved = false;
  }, { capture: true });

  // --- Click souris/stylet : fermeture à l’extérieur seulement
  document.addEventListener('click', (e) => {
    // avale le "ghost click" qui suit un touchend
    if (Date.now() - lastTouchEndTs < 350) return;
    closeIfOutside(e.target);
  }, true);

  // Neutralisations : ne JAMAIS fermer sur hover/focus
  launcher.addEventListener('mouseleave', () => { /* no-op: sticky */ });
  btn.addEventListener('mouseleave', () => { /* no-op: sticky */ });

  // ESC → fermer si ouvert
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen) setOpen(false);
  });
})();




  // ===== Settings modal + tabs
  // const openSettings=()=>{ backdrop.style.display='flex'; setTimeout(()=>$('.modal').classList.add('show'),0); backdrop.setAttribute('aria-hidden','false'); };
//  const openSettings = () => {
//    backdrop.style.display = 'flex';
//    cibler UNIQUEMENT la modale des Settings
//    const modal = backdrop.querySelector('.modal');
//    setTimeout(() => modal?.classList.add('show'), 0);
//    backdrop.setAttribute('aria-hidden', 'false');
//  };
const openSettings = () => {
  const backdrop = document.getElementById('settingsBackdrop');
  const modal = backdrop?.querySelector('.modal');
  
  if (!backdrop || !modal) {
    console.error('Settings backdrop or modal not found');
    return;
  }
  
  backdrop.style.display = 'flex';
  backdrop.style.zIndex = '90'; // Force z-index
  backdrop.setAttribute('aria-hidden', 'false');
  
  // Trigger animation après render
  requestAnimationFrame(() => {
    modal.classList.add('show');
  });
};
  // const closeSettings=()=>{ backdrop.style.display='none'; backdrop.setAttribute('aria-hidden','true'); };
 const closeSettings = () => {
   const modal = backdrop.querySelector('.modal');
   modal?.classList.remove('show');
   backdrop.style.display = 'none';
   backdrop.setAttribute('aria-hidden','true');
 };
  $('#openSettings')?.addEventListener('click',openSettings);
  $('#closeSettings')?.addEventListener('click',closeSettings);
  backdrop?.addEventListener('click',e=>{ if(e.target===backdrop) closeSettings(); });
  $('#settingsTabs')?.addEventListener('click', e=>{ const btn = e.target.closest('.tabbtn'); if(!btn) return; $$('.tabbtn').forEach(b=>b.classList.toggle('active', b===btn)); const name=btn.dataset.tab; $$('.tabpanel').forEach(p=>p.hidden=!p.id.endsWith(name)); });
  $('#tab-theme')?.addEventListener('click', e=>{ const b=e.target.closest('[data-theme]'); if(!b) return; const root=document.documentElement.style; if(b.dataset.theme==='acid'){ root.setProperty('--acid','#00ff9a'); root.setProperty('--acid-2','#18f0ff'); } else if(b.dataset.theme==='cyan'){ root.setProperty('--acid','#00e5ff'); root.setProperty('--acid-2','#6df7ff'); } else if(b.dataset.theme==='amber'){ root.setProperty('--acid','#ffc400'); root.setProperty('--acid-2','#ff8a00'); } toast(`Theme → ${b.dataset.theme}`); });

  // ===== Gestures + keyboard for panels
  let touchStartY=null;
  document.addEventListener('touchstart', e=>{ const t=e.touches[0]; touchStartY=t.clientY; },{passive:true});
  document.addEventListener('touchend', e=>{
    if(touchStartY==null) return;
    const y=e.changedTouches[0].clientY; const dy=y-touchStartY;
    const nearTop = touchStartY<24; const nearBottom = touchStartY>window.innerHeight-24;
    if(nearTop && dy>40) qpShow(true);
    if(nearBottom && dy<-40) openConsole();
    touchStartY=null;
  });

(function setupBackdropLiveMode(){
  const backdrop = document.getElementById('settingsBackdrop');
  const tabs = document.getElementById('settingsTabs');

  function applyLive(on){ backdrop?.classList.toggle('live', !!on); }

  // Au clic sur les tabs
  tabs?.addEventListener('click', (e)=>{
    const b = e.target.closest('.tabbtn');
    if(!b) return;
    applyLive(b.dataset.tab === 'ui');
  });

  // À l’ouverture des settings
  document.getElementById('openSettings')?.addEventListener('click', ()=>{
    const active = tabs?.querySelector('.tabbtn.active');
    applyLive(active?.dataset.tab === 'ui');
  });
})();



  closeConsole();

  // ===== Notifications gate (persisted) =====
  (function setupNotificationsGateAndSwitch(){
    const NOTIF_KEY = 'Bjorn.Notifs';
    function readFlag(){
      try{ const v = localStorage.getItem(NOTIF_KEY); return v===null ? true : v==='1'; }catch{ return true; }
    }
    function writeFlag(on){
      try{ localStorage.setItem(NOTIF_KEY, on ? '1' : '0'); }catch{}
    }

    // state + wrapper
    window.Bjorn = window.Bjorn || {};
    Bjorn.notificationsEnabled = readFlag();

    // keep original impl
    const _impl = window.Bjorn.toast;
    // redefine global generic toast to honor gate
    window.toast = function(msg, ms=2600){
      if (!Bjorn.notificationsEnabled) return;
      (_impl || _innerToast)(msg, ms);
    };
    // also ensure Bjorn.toast goes through gate
    Bjorn.toast = window.toast;

    // wire settings switch
    const sw = document.getElementById('switchNotifs');
    if (sw){
      sw.classList.toggle('on', !!Bjorn.notificationsEnabled);
      sw.addEventListener('click', () => {
        const on = !Bjorn.notificationsEnabled;
        Bjorn.notificationsEnabled = on;
        writeFlag(on);
        sw.classList.toggle('on', on);
        // tiny feedback that ignores the gate so user gets confirmation:
        (_impl || _innerToast)(on ? 'Notifications ON' : 'Notifications OFF', 1400);
      });
    }
  })();

  // ===== Public API (merged, keeps previous members)
  window.Bjorn = Object.assign({}, window.Bjorn || {}, {
    openConsole,
    closeConsole,
    log: (m) => log(m),
    setTheme: (name) => {
      const root = document.documentElement.style;
      if (name === 'cyan') {
        root.setProperty('--acid', '#00e5ff');
        root.setProperty('--acid-2', '#6df7ff');
      } else if (name === 'amber') {
        root.setProperty('--acid', '#ffc400');
        root.setProperty('--acid-2', '#ff8a00');
      } else {
        root.setProperty('--acid', '#00ff9a');
        root.setProperty('--acid-2', '#18f0ff');
      }
      toast(`Theme → ${name}`);
    },
    addLauncherItem: (icon, title, href) => {
      const a = el('a', { class: 'lbtn', href, title }, icon);
      $('#launcher')?.appendChild(a);
    },
    reloadConfig: async () => {
      try { localStorage.removeItem('BjornConfig'); } catch {}
      const fresh = await (async () => {
        try {
          const r = await fetch('/bjorn.config.json', { cache: 'no-store' });
          if (r.ok) return await r.json();
        } catch {}
        return null;
      })();
      if (fresh) {
        Object.assign(cfg, fresh);
        try { localStorage.setItem('BjornConfig', JSON.stringify(fresh)); } catch {}
        buildLauncher();
        toast('Config reloaded');
      }
    },
    // expose SSE controls without losing SettingsConfig already defined
    consoleSSE: BjornUI.ConsoleSSE,
    version: '1.2.0'
  });






// ===== Bjorn.UIVars — collecter/apply/export/import des custom properties =====
window.Bjorn = window.Bjorn || {};
(function () {
  if (Bjorn.UIVars) return; // idempotent

  const STORE_KEY = 'Bjorn.UI.Vars';

  // Retourne { "--acid":"#00ff9a", "--console-font":"12px", ... }
  function collectFromStylesheets({ hrefIncludes = ['global.css'] } = {}) {
    const out = {};
    const sheets = Array.from(document.styleSheets || []);
    for (const sh of sheets) {
      // Filtrage facultatif : uniquement les feuilles ciblées (ou inline si href null)
      const isTarget = !hrefIncludes?.length ||
                       !sh.href || hrefIncludes.some(s => (sh.href || '').includes(s));

      if (!isTarget) continue;
      let rules;
      try { rules = sh.cssRules; } catch (e) {
        // CORS : si cross-origin → cssRules inaccessible
        continue;
      }
      if (!rules) continue;

      for (const r of rules) {
        if (!(r.style && r.selectorText)) continue;
        if (!/(^|,)\s*(?:\:root|html|body)\s*(,|$)/i.test(r.selectorText)) continue;

        // Récupère toutes les props qui commencent par --
        for (let i = 0; i < r.style.length; i++) {
          const prop = r.style[i];
          if (prop.startsWith('--')) out[prop] = r.style.getPropertyValue(prop).trim();
        }
      }
    }
    return out;
  }

  // Applique un dict { "--var":"val" } sur :root (inline style → priorité)
  function apply(vars) {
    const root = document.documentElement;
    Object.entries(vars || {}).forEach(([k, v]) => {
      if (String(k).startsWith('--')) root.style.setProperty(k, String(v));
    });
  }

  // Lecture/écriture storage
  function saveLocal(vars) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(vars || {})); } catch {}
  }
  function loadLocal() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY) || '{}'); } catch { return {}; }
  }

  // Fusion : local override > CSS initial
  function current({ hrefIncludes } = {}) {
    const base = collectFromStylesheets({ hrefIncludes });
    const overrides = loadLocal();
    return Object.assign({}, base, overrides);
  }

  // Export JSON (téléchargement)
  function exportJSON(vars) {
    const blob = new Blob([JSON.stringify(vars || loadLocal(), null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'bjorn-ui-config.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // Import JSON (fichier ou texte)
  async function importJSON(src) {
    let obj = {};
    if (src instanceof File) {
      obj = JSON.parse(await src.text());
    } else if (typeof src === 'string') {
      obj = JSON.parse(src);
    } else if (src && typeof src === 'object') {
      obj = src;
    }
    // Filtrer uniquement les clés --var
    const clean = {};
    Object.entries(obj).forEach(([k, v]) => { if (String(k).startsWith('--')) clean[k] = v; });
    apply(clean);
    saveLocal(Object.assign(loadLocal(), clean));
    return clean;
  }

  // Auto-apply au démarrage (si overrides existent)
  (function autoApply() {
    const overrides = loadLocal();
    if (overrides && Object.keys(overrides).length) apply(overrides);
  })();

  Bjorn.UIVars = { collectFromStylesheets, apply, exportJSON, importJSON, current, loadLocal, saveLocal, STORE_KEY };
})();


// ===== Settings → UI tab =====
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  if (document.getElementById('tab-ui')) return; // idempotent

  const tabs = document.getElementById('settingsTabs');
  const modal = $('#settingsBackdrop .modal');
  if (!tabs || !modal) return;

  // 1) Tab bouton
  const btn = document.createElement('button');
  btn.className = 'tabbtn';
  btn.dataset.tab = 'ui';
  btn.textContent = 'UI';
  const aboutBtn = tabs.querySelector('[data-tab="about"]');
  tabs.insertBefore(btn, aboutBtn || null);

  // 2) Panel contenu
  const panel = document.createElement('section');
  panel.className = 'tabpanel';
  panel.id = 'tab-ui';
  panel.hidden = true;
  panel.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-bottom:8px">
      <button class="btn" id="uiExport">Export JSON</button>
      <button class="btn" id="uiImport">Import JSON</button>
      <button class="btn" id="uiCopy">Copier JSON</button>
      <button class="btn" id="uiReset">Reset (retirer overrides)</button>
    </div>
    <div id="uiVarsHost" class="grid-auto-320" style="max-height:55vh;overflow:auto"></div>
    <input type="file" id="uiImportFile" accept="application/json" hidden>
  `;
  modal.appendChild(panel);

  // Petit style de champ
  const css = document.createElement('style');
  css.textContent = `
    .ui-var-card{border:1px solid rgba(0,255,154,.15);background:rgba(0,0,0,.2);border-radius:12px;padding:12px;display:flex;gap:10px;align-items:center}
    .ui-var-name{font-family:monospace;font-size:12px;min-width:160px;word-break:break-all;color:var(--acid)}
    .ui-var-input{flex:1;display:flex;gap:8px;align-items:center}
    .ui-var-input input[type="text"]{width:100%}
    .ui-var-actions{display:flex;gap:6px}
    .ui-dot{width:20px;height:20px;border-radius:6px;border:1px solid rgba(255,255,255,.15)}
  `;
  document.head.appendChild(css);
  // ---- Helpers de typage ----------------------------------------------------
  function isHexColor(v){ return /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(v.trim()); }
  function isRgb(v){ return /^rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}(?:\s*,\s*(0|1|0?\.\d+))?\s*\)$/i.test(v.trim()); }
  function isHsl(v){ return /^hsla?\(\s*\d+(?:deg|turn|rad)?\s*,\s*\d+%\s*,\s*\d+%(?:\s*,\s*(0|1|0?\.\d+))?\s*\)$/i.test(v.trim()); }
  function isColorMix(v){ return /^color-mix\(/i.test(v.trim()); }
  function isGradient(v){ return /(repeating-)?(linear|radial|conic)-gradient\(/i.test(v.trim()); }
  function isShadow(v){ return /\b(?:inset\s+)?-?\d*\.?\d+(px|rem|em)\s+-?\d*\.?\d+(px|rem|em)\s+-?\d*\.?\d+(px|rem|em)/i.test(v.trim()); }
  function isUrl(v){ return /^url\(/i.test(v.trim()); }
  function isLength(v){ return /^-?\d*\.?\d+\s*(px|vh|vw|rem|em|%|vmin|vmax|ch)$/i.test(v.trim()); }
  function isNumberOnly(v){ return /^-?\d*\.?\d+$/.test(v.trim()); }

  const LEN_UNITS = ['px','vh','vw','rem','em','%','vmin','vmax','ch'];

  function splitLength(raw){
    const s = String(raw||'').trim();
    const m = s.match(/^(-?\d*\.?\d+)\s*(px|vh|vw|rem|em|%|vmin|vmax|ch)$/i);
    if(!m) return { num: NaN, unit: 'px' };
    return { num: parseFloat(m[1]), unit: m[2] };
  }

  function clamp(n, min, max){ return Math.min(max, Math.max(min, n)); }

  // Heuristiques min/max selon nom + unité
  function rangeFor(name, unit, num){
    const n = Number(num);
    const byUnit = {
      px:  {min:0, max: (n>0? Math.max(64, n*3) : 512), step:1},
      rem: {min:0, max: (n>0? Math.max(2, n*3) : 10), step:0.1},
      em:  {min:0, max: (n>0? Math.max(2, n*3) : 10), step:0.1},
      vh:  {min:0, max:100, step:1},
      vw:  {min:0, max:100, step:1},
      '%': {min:0, max:100, step:1},
      vmin:{min:0, max:100, step:1},
      vmax:{min:0, max:100, step:1},
      ch:  {min:0, max:(n>0? Math.max(10, n*3) : 60), step:1},
    };
    const r = byUnit[unit] || {min:0, max:(n>0? n*3 : 100), step:1};
    // ajustements par nom courant
    if (/radius/i.test(name)) return {min:0, max:64, step:1};
    if (/gap|pad|space/i.test(name) && unit==='px') return {min:0, max:48, step:1};
    if (/h-|height/i.test(name) && unit==='px') return {min:20, max:200, step:1};
    return r;
  }

  // Conversion couleur hex <-> rgba pour le color input
  function rgbaToHex(r,g,b){ return '#'+[r,g,b].map(n=>Math.max(0,Math.min(255,Math.round(n))).toString(16).padStart(2,'0')).join(''); }
  function parseRgba(str){
    const m = str.match(/^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*(\d*\.?\d+))?\s*\)$/i);
    if(!m) return null;
    return { r:+m[1], g:+m[2], b:+m[3], a:(m[4]==null?1:+m[4]) };
  }

  // ---- Render d’une ligne de variable ---------------------------------------
  function rowWrap(name){
    const card = document.createElement('div');
    card.className = 'ui-var-card';
    const left = document.createElement('div');
    left.className = 'ui-var-name';
    left.textContent = name;
    const body = document.createElement('div');
    body.className = 'ui-var-input';
    const actions = document.createElement('div');
    actions.className = 'ui-var-actions';
    const resetBtn = document.createElement('button');
    resetBtn.className = 'btn';
    resetBtn.textContent = 'Reset';
    actions.appendChild(resetBtn);
    card.append(left, body, actions);
    return { card, body, resetBtn };
  }

  function updateVar(name, value){
    document.documentElement.style.setProperty(name, value);
    const local = Bjorn.UIVars.loadLocal();
    local[name] = value;
    Bjorn.UIVars.saveLocal(local);
  }

  function removeOverride(name){
    document.documentElement.style.removeProperty(name);
    const local = Bjorn.UIVars.loadLocal();
    delete local[name];
    Bjorn.UIVars.saveLocal(local);
  }

  // ---- Contrôles spécialisés -------------------------------------------------
  function renderColorControl(name, value){
    const { card, body, resetBtn } = rowWrap(name);

    // picker + champ texte (pour rgba/hsl/colormix)
    const swatch = document.createElement('div');
    swatch.className = 'ui-dot';
    swatch.style.background = value;

    const picker = document.createElement('input');
    picker.type = 'color';
    // si rgba/hsl → approx hex pour le picker
    if (isHexColor(value)) picker.value = value;
    else if (isRgb(value)){
      const {r,g,b} = parseRgba(value);
      picker.value = rgbaToHex(r,g,b);
    } else {
      // fallback: essaie computed
      try {
        const tmp = document.createElement('div');
        tmp.style.color = value; // force parse
        document.body.appendChild(tmp);
        const cs = getComputedStyle(tmp).color;
        document.body.removeChild(tmp);
        const {r,g,b} = parseRgba(cs) || {r:0,g:0,b:0};
        picker.value = rgbaToHex(r,g,b);
      } catch { picker.value = '#00ff9a'; }
    }

    const text = document.createElement('input');
    text.type = 'text';
    text.value = value;
    text.placeholder = 'hex, rgb(), hsl(), color-mix()…';

    function paint(v){
      swatch.style.background = v;
      text.value = v;
      updateVar(name, v);
    }

    picker.addEventListener('input', ()=> {
      // si original était rgba/hsla → garder alpha en 1 par défaut
      const hex = picker.value;
      paint(hex);
    });

    text.addEventListener('change', ()=>{
      const v = text.value.trim();
      paint(v);
    });

    resetBtn.addEventListener('click', ()=>{ removeOverride(name); text.value = value; swatch.style.background = value; });

    body.append(swatch, picker, text);
    return card;
  }

  function renderLengthControl(name, value){
    const { card, body, resetBtn } = rowWrap(name);
    const { num, unit } = splitLength(value);
    const select = document.createElement('select');
    LEN_UNITS.forEach(u=>{
      const o = document.createElement('option');
      o.value = u; o.textContent = u;
      if (u.toLowerCase() === unit.toLowerCase()) o.selected = true;
      select.appendChild(o);
    });

    const input = document.createElement('input');
    input.type = 'range';
    const r = rangeFor(name, unit, num);
    input.min = String(r.min);
    input.max = String(r.max);
    input.step = String(r.step);
    input.value = String(isFinite(num) ? clamp(num, r.min, r.max) : r.min);

    const box = document.createElement('input');
    box.type = 'number';
    box.value = String(isFinite(num) ? num : r.min);
    box.min = String(r.min);
    box.max = String(r.max);
    box.step = String(r.step);
    box.style.width = '90px';

    const pretty = () => `${box.value}${select.value}`;

    function apply(){
      updateVar(name, pretty());
    }

    input.addEventListener('input', ()=> { box.value = input.value; apply(); });
    box.addEventListener('input', ()=> {
      const n = parseFloat(box.value);
      if (isFinite(n)) input.value = String(clamp(n, +input.min, +input.max));
      apply();
    });
    select.addEventListener('change', ()=> {
      // re-range si unité change
      const r2 = rangeFor(name, select.value, parseFloat(box.value));
      input.min = String(r2.min); input.max = String(r2.max); input.step = String(r2.step);
      box.min = String(r2.min); box.max = String(r2.max); box.step = String(r2.step);
      apply();
    });

    resetBtn.addEventListener('click', ()=> {
      removeOverride(name);
      const { num:n2, unit:u2 } = splitLength(value);
      select.value = u2;
      const rr = rangeFor(name, u2, n2);
      input.min = String(rr.min); input.max = String(rr.max); input.step = String(rr.step);
      input.value = String(isFinite(n2) ? clamp(n2, rr.min, rr.max) : rr.min);
      box.min = String(rr.min); box.max = String(rr.max); box.step = String(rr.step);
      box.value = String(isFinite(n2) ? n2 : rr.min);
    });

    body.append(input, box, select);
    return card;
  }

  function renderTextAreaPreview(name, value, kind){ // kind: 'gradient' | 'shadow' | 'other'
    const { card, body, resetBtn } = rowWrap(name);
    const preview = document.createElement('div');
    preview.style.width = '140px';
    preview.style.height = '40px';
    preview.style.border = '1px solid rgba(255,255,255,.12)';
    preview.style.borderRadius = '8px';
    preview.style.flex = '0 0 auto';

    const ta = document.createElement('textarea');
    ta.value = value;
    ta.style.flex = '1 1 auto';
    ta.style.minHeight = '64px';
    ta.style.resize = 'vertical';

    function paint(v){
      try{
        if (kind==='gradient') {
          preview.style.background = v;
          preview.style.boxShadow = 'none';
        } else if (kind==='shadow') {
          preview.style.background = 'var(--panel, #111)';
          preview.style.boxShadow = v;
        } else {
          preview.style.background = 'var(--panel, #111)';
          preview.style.boxShadow = 'none';
        }
      }catch{}
    }
    paint(value);

    ta.addEventListener('input', ()=>{
      const v = ta.value.trim();
      paint(v);
      updateVar(name, v);
    });
    resetBtn.addEventListener('click', ()=>{ removeOverride(name); ta.value = value; paint(value); });

    body.append(preview, ta);
    return card;
  }

  function renderSimpleText(name, value){
    const { card, body, resetBtn } = rowWrap(name);
    const inp = document.createElement('input');
    inp.type = 'text';
    inp.value = value;
    inp.addEventListener('change', ()=> updateVar(name, inp.value.trim()));
    resetBtn.addEventListener('click', ()=>{ removeOverride(name); inp.value = value; });
    body.append(inp);
    return card;
  }

  // ---- Rendu global ----------------------------------------------------------
  function renderUIVars(){
    const host = document.getElementById('uiVarsHost');
    if(!host) return;
    host.innerHTML = '';

    // Toutes les variables courantes (CSS + overrides)
    const vars = Bjorn.UIVars.current(); // { --acid: '#00ff9a', ... }

    // Optionnel: classer par famille (couleurs / tailles / autres)
    const entries = Object.entries(vars)
      .filter(([k]) => k.startsWith('--')) // par sécurité
      .sort(([a],[b]) => a.localeCompare(b));

    for (const [name, valRaw] of entries) {
      const value = String(valRaw || '').trim();

      // 1) Couleurs (hex/rgb/hsl/color-mix)
      if (isHexColor(value) || isRgb(value) || isHsl(value) || isColorMix(value)) {
        host.appendChild(renderColorControl(name, value));
        continue;
      }
      // 2) Longueurs avec unité
      if (isLength(value)) {
        host.appendChild(renderLengthControl(name, value));
        continue;
      }
      // 3) Gradients / Shadows (avec preview)
      if (isGradient(value)) {
        host.appendChild(renderTextAreaPreview(name, value, 'gradient'));
        continue;
      }
      if (isShadow(value)) {
        host.appendChild(renderTextAreaPreview(name, value, 'shadow'));
        continue;
      }
      // 4) Nombres bruts (sans unité) => slider simple + input
      if (isNumberOnly(value)) {
        const unitized = `${value}px`; // pour profiter du composant longueur
        host.appendChild(renderLengthControl(name, unitized));
        continue;
      }
      // 5) Fallback: textarea/texte
      host.appendChild(renderSimpleText(name, value));
    }
  }

  // ---- Boutons (export / import / reset / copy) ------------------------------
  $('#uiExport')?.addEventListener('click', ()=> Bjorn.UIVars.exportJSON(Bjorn.UIVars.loadLocal()));
  $('#uiCopy')?.addEventListener('click', async ()=>{
    const txt = JSON.stringify(Bjorn.UIVars.loadLocal(), null, 2);
    try { await navigator.clipboard.writeText(txt); toast('JSON copié'); } catch { toast('Impossible de copier'); }
  });
  $('#uiImport')?.addEventListener('click', ()=> $('#uiImportFile')?.click());
  $('#uiImportFile')?.addEventListener('change', async (e)=>{
    const f = e.target.files?.[0]; if(!f) return;
    try { await Bjorn.UIVars.importJSON(f); toast('Import OK'); renderUIVars(); } catch(err){ console.error(err); toast('Import invalide'); }
    e.target.value = '';
  });
  $('#uiReset')?.addEventListener('click', ()=>{
    const local = Bjorn.UIVars.loadLocal();
    Object.keys(local).forEach(k => document.documentElement.style.removeProperty(k));
    Bjorn.UIVars.saveLocal({});
    toast('Overrides retirés');
    renderUIVars();
  });

  // Rendre quand l’onglet UI est affiché
  $('#settingsTabs')?.addEventListener('click', (e)=>{
    const b = e.target.closest('.tabbtn'); if(!b) return;
    if (b.dataset.tab === 'ui') setTimeout(renderUIVars, 0);
  });
  // Si on ouvre les settings et qu'on est déjà sur UI
  $('#openSettings')?.addEventListener('click', ()=>{
    const active = $('#settingsTabs .tabbtn.active');
    if (active?.dataset.tab === 'ui') setTimeout(renderUIVars, 0);
  });

  // Expose si besoin
  window.Bjorn = window.Bjorn || {};
  window.Bjorn.renderUIVars = renderUIVars;
})();







  // ===== Number+Slider enhancer (kept compatible)
  (function(){
    function clamp(v, min, max){ return Math.min(max, Math.max(min, v)); }
    function pct(val, min, max){ return ( (val - min) * 100 ) / (max - min || 1); }

    function setup(root){
      document.querySelectorAll('.input-number-w-slider').forEach(wrap=>{
        const r = wrap.querySelector('input[type="range"]');
        const n = wrap.querySelector('input[type="number"]');
        if(!r || !n) return;

        const min = +(r.min || n.min || wrap.dataset.min || 0);
        const max = +(r.max || n.max || wrap.dataset.max || 100);
        const step = +(r.step || n.step || wrap.dataset.step || 1);

        [r, n].forEach(el => { el.min = min; el.max = max; el.step = step; });

        // init value
        const start = Number.isFinite(+n.value) ? +n.value : (Number.isFinite(+r.value) ? +r.value : min);
        r.value = n.value = clamp(start, min, max);

        // update track fill (WebKit)
        const paint = () => {
          const p = pct(+r.value, min, max);
          wrap.style.setProperty('--_fill', p + '%');
        };
        paint();

        // events
        r.addEventListener('input', ()=>{
          n.value = r.value;
          paint();
          wrap.dispatchEvent(new CustomEvent('valuechange', { detail:{ value:+r.value } }));
        });
        n.addEventListener('input', ()=>{
          const v = clamp(+n.value || 0, min, max);
          r.value = v;
          n.value = v;
          paint();
          wrap.dispatchEvent(new CustomEvent('valuechange', { detail:{ value:v } }));
        });

        // optional: wheel to step on the number field
        n.addEventListener('wheel', (e)=>{
          if(!n.matches(':focus')) return;
          e.preventDefault();
          const dir = e.deltaY > 0 ? -1 : 1;
          const next = clamp((+n.value || 0) + dir*step, min, max);
          n.value = next;
          r.value = next;
          paint();
          wrap.dispatchEvent(new CustomEvent('valuechange', { detail:{ value:next } }));
        }, { passive:false });
      });
    }

    // auto-setup now; expose for dynamic content
    document.readyState !== 'loading' ? setup(document) : document.addEventListener('DOMContentLoaded', ()=>setup(document));
    window.Bjorn = Object.assign({}, window.Bjorn || {}, { setupNumberWithSlider: setup });
  })();

  // ===== Init Console SSE & ManualMode after DOM is ready
  if (window.BjornUI?.ConsoleSSE) {
    BjornUI.ConsoleSSE.init({ targetSelector: '#logout' });
  }
  if (window.BjornUI?.ManualMode) {
    BjornUI.ManualMode.init();
  }

  window.addEventListener('beforeunload', ()=> window.BjornUI?.ConsoleSSE?.stop?.());

})();


// =====================================================================
// Added: value-type detection & parsing helpers (colors, gradients, var)
// =====================================================================

// rgb()/hsl() detection as a single predicate
function isRgbOrHslColor(v){
  return /\b(?:rgb|hsl)a?\s*\(/i.test(String(v||''));
}
function isColorToken(v){
  return isHexColor(v) || isRgbOrHslColor(v);
}
function isGradient(v){
  return /^\s*(?:linear|radial|conic)-gradient\(/i.test(String(v||''));
}

// linear-gradient angle helpers
function parseLinearAngle(v){
  const m = String(v||'').match(/linear-gradient\(\s*([0-9.\-]+)deg/i);
  return m ? parseFloat(m[1]) : 180; // default browser angle
}
function setLinearAngle(v, deg){
  const s = String(v||'');
  if (/linear-gradient\(/i.test(s)){
    if (/linear-gradient\(\s*[0-9.\-]+deg/i.test(s)){
      return s.replace(/linear-gradient\(\s*[0-9.\-]+deg/i, `linear-gradient(${deg}deg`);
    } else {
      return s.replace(/linear-gradient\(/i, `linear-gradient(${deg}deg,`);
    }
  }
  return s;
}

// color tokens inside gradients
function extractGradientColors(v){
  // capture #hex / rgb[a] (...) / hsl[a] (...)
  return String(v||'').match(/#([0-9a-f]{3}|[0-9a-f]{6})\b|(?:rgb|hsl)a?\([^)]*\)/ig) || [];
}
function replaceGradientColorAt(v, index, newColor){
  let i = -1;
  return String(v||'').replace(/#([0-9a-f]{3}|[0-9a-f]{6})\b|(?:rgb|hsl)a?\([^)]*\)/ig, (m) => {
    i++; return (i === index) ? newColor : m;
  });
}

// var() helpers
function parseVarRef(v){
  // var(--name, fallback)
  const m = String(v||'').match(/^\s*var\(\s*(--[a-z0-9\-_]+)\s*(?:,\s*([^)]+))?\)\s*$/i);
  if(!m) return null;
  return { ref: m[1], fallback: m[2]?.trim() ?? null };
}
function resolveCssVar(varName){
  // reads effective value from :root (inherited + overrides)
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}


// =====================================================================
// Added: Gradient Editor (preview + angle for linear + stops editor)
// =====================================================================
function createGradientEditor(name, value){
  const card = document.createElement('div');
  card.className = 'ui-var-card';
  card.dataset.name = name;

  const title = document.createElement('div');
  title.className = 'ui-var-name';
  title.textContent = name;

  const preview = document.createElement('div');
  preview.style.width = '140px';
  preview.style.height = '36px';
  preview.style.borderRadius = '8px';
  preview.style.border = '1px solid rgba(255,255,255,.15)';
  preview.style.flex = '0 0 auto';
  preview.style.background = value;

  const body = document.createElement('div');
  body.style.flex = '1';
  body.style.display = 'grid';
  body.style.gap = '8px';

  let current = String(value||'');

  // angle editor for linear-gradient(...)
  const angleWrap = document.createElement('div');
  if (/^linear-gradient/i.test(current)){
    const label = document.createElement('label');
    label.textContent = 'Angle';
    const range = document.createElement('input');
    range.type = 'range'; range.min = '0'; range.max = '360'; range.step = '1';
    range.value = String(parseLinearAngle(current));
    range.addEventListener('input', ()=>{
      current = setLinearAngle(current, parseInt(range.value,10));
      preview.style.background = current;
      const cur = Bjorn.UIVars.loadLocal(); cur[name] = current; Bjorn.UIVars.saveLocal(cur);
      document.documentElement.style.setProperty(name, current);
    });
    angleWrap.append(label, range);
  }

  // color stops
  const colors = extractGradientColors(current);
  const stopsWrap = document.createElement('div');
  stopsWrap.style.display = 'flex';
  stopsWrap.style.flexWrap = 'wrap';
  stopsWrap.style.gap = '8px';

  colors.forEach((tok, idx)=>{
    let ctrl;
    if (isHexColor(tok)){
      // normalize #abc → #aabbcc for <input type=color>
      const norm = tok.length === 4
        ? ('#' + tok[1]+tok[1]+tok[2]+tok[2]+tok[3]+tok[3]).toLowerCase()
        : tok.toLowerCase();
      ctrl = document.createElement('input');
      ctrl.type = 'color';
      ctrl.value = norm;
      ctrl.title = `Stop ${idx+1}`;
      ctrl.addEventListener('input', ()=>{
        current = replaceGradientColorAt(current, idx, ctrl.value);
        preview.style.background = current;
        const cur = Bjorn.UIVars.loadLocal(); cur[name] = current; Bjorn.UIVars.saveLocal(cur);
        document.documentElement.style.setProperty(name, current);
      });
    } else {
      // rgb()/hsl() → free text input
      ctrl = document.createElement('input');
      ctrl.type = 'text';
      ctrl.value = tok;
      ctrl.style.minWidth = '160px';
      ctrl.addEventListener('change', ()=>{
        const v = ctrl.value.trim();
        if (!v) return;
        current = replaceGradientColorAt(current, idx, v);
        preview.style.background = current;
        const cur = Bjorn.UIVars.loadLocal(); cur[name] = current; Bjorn.UIVars.saveLocal(cur);
        document.documentElement.style.setProperty(name, current);
      });
    }

    const group = document.createElement('div');
    group.style.display = 'flex';
    group.style.alignItems = 'center';
    group.style.gap = '6px';
    const lbl = document.createElement('span');
    lbl.textContent = `Stop ${idx+1}`;
    lbl.style.fontSize = '11px';
    lbl.style.opacity = '.7';
    group.append(lbl, ctrl);
    stopsWrap.appendChild(group);
  });

  // raw textarea
  const raw = document.createElement('textarea');
  raw.value = current;
  raw.rows = 2;
  raw.style.width = '100%';
  raw.style.resize = 'vertical';
  raw.addEventListener('change', ()=>{
    const v = raw.value.trim();
    if (!v) return;
    current = v;
    preview.style.background = current;
    const cur = Bjorn.UIVars.loadLocal(); cur[name] = current; Bjorn.UIVars.saveLocal(cur);
    document.documentElement.style.setProperty(name, current);
  });

  // Reset
  const btnReset = document.createElement('button');
  btnReset.className = 'btn';
  btnReset.textContent = 'Reset';
  btnReset.addEventListener('click', ()=>{
    const overrides = Bjorn.UIVars.loadLocal();
    delete overrides[name];
    Bjorn.UIVars.saveLocal(overrides);
    document.documentElement.style.removeProperty(name);
    const base = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || value;
    current = base;
    preview.style.background = base;
    raw.value = base;
  });

  body.append(angleWrap, stopsWrap, raw);
  card.append(title, preview, body, btnReset);
  return card;
}


// =====================================================================
// Added: var(--xxx) Editor (follow + dereference + reset)
// =====================================================================
function createVarEditor(name, value){
  const ref = parseVarRef(value);
  if (!ref) return null;

  const resolved = resolveCssVar(ref.ref) || ref.fallback || '';
  const card = document.createElement('div');
  card.className = 'ui-var-card';
  card.dataset.name = name;

  const title = document.createElement('div');
  title.className = 'ui-var-name';
  title.textContent = name;

  const info = document.createElement('div');
  info.style.display = 'grid';
  info.style.gap = '8px';
  info.style.flex = '1';

  // row1: reference + resolved value (+ color swatch if suitable)
  const row1 = document.createElement('div');
  row1.style.display = 'flex';
  row1.style.alignItems = 'center';
  row1.style.gap = '8px';

  const refBadge = document.createElement('span');
  refBadge.className = 'badge-modern';
  refBadge.textContent = `ref: ${ref.ref}`;

  const resolvedBox = document.createElement('div');
  resolvedBox.textContent = `resolved: ${resolved || '(empty)'}`;
  resolvedBox.style.fontSize = '12px';
  resolvedBox.style.opacity = '.8';

  if (isGradient(resolved) || isColorToken(resolved)){
    const sw = document.createElement('div');
    sw.style.width = '28px'; sw.style.height = '18px';
    sw.style.borderRadius = '6px';
    sw.style.border = '1px solid rgba(255,255,255,.15)';
    sw.style.background = isGradient(resolved) ? resolved : resolved;
    row1.appendChild(sw);
  }

  row1.append(refBadge, resolvedBox);

  // row2: actions
  const row2 = document.createElement('div');
  row2.style.display = 'flex';
  row2.style.gap = '8px';

  const btnFollow = document.createElement('button');
  btnFollow.className = 'btn';
  btnFollow.textContent = 'Follow →';
  btnFollow.addEventListener('click', ()=>{
    const target = document.querySelector(`.ui-var-card[data-name="${CSS.escape(ref.ref)}"]`);
    if (target){
      target.scrollIntoView({behavior:'smooth', block:'center'});
      target.animate([{outline:'2px solid var(--acid)'},{outline:'none'}], {duration:900});
    } else {
      window.toast?.(`Variable ${ref.ref} not found in the list`);
    }
  });

  const btnDereference = document.createElement('button');
  btnDereference.className = 'btn';
  btnDereference.textContent = 'Dereference';
  btnDereference.title = 'Replace this var() with its resolved value';
  btnDereference.addEventListener('click', ()=>{
    const val = resolved || ref.fallback || '';
    if (!val) return;
    document.documentElement.style.setProperty(name, val);
    const cur = Bjorn.UIVars.loadLocal(); cur[name] = val; Bjorn.UIVars.saveLocal(cur);
    window.toast?.(`\`${name}\` ← ${val}`);
  });

  const btnReset = document.createElement('button');
  btnReset.className = 'btn';
  btnReset.textContent = 'Reset';
  btnReset.addEventListener('click', ()=>{
    const overrides = Bjorn.UIVars.loadLocal();
    delete overrides[name];
    Bjorn.UIVars.saveLocal(overrides);
    document.documentElement.style.removeProperty(name);
  });

  row2.append(btnFollow, btnDereference, btnReset);
  info.append(row1, row2);

  card.append(title, info);
  return card;
}


// =====================================================================
// Override: renderUIVars() routing with var/gradient/color support
// =====================================================================
function renderUIVars(){
  const host = document.getElementById('uiVarsHost');
  if(!host) return;
  host.innerHTML = '';

  // Merge current CSS + local overrides
  const vars = Bjorn.UIVars.current(); // { --acid: '#00ff9a', ... }

  // Sort and iterate
  const entries = Object.entries(vars)
    .filter(([k]) => k.startsWith('--'))
    .sort(([a],[b]) => a.localeCompare(b));

  for (const [name, valRaw] of entries) {
    const value = String(valRaw || '').trim();

    // 1) var(--xxx) → dedicated card
    const varRef = parseVarRef(value);
    if (varRef){
      const c = createVarEditor(name, value);
      if (c) { host.appendChild(c); continue; }
    }

    // 2) gradients → specialized editor
    if (typeof value === 'string' && isGradient(value)){
      host.appendChild(createGradientEditor(name, value));
      continue;
    }

    // 3) direct colors (hex/rgb/hsl/color-mix if you had it)
    if (typeof value === 'string' &&
        (isHexColor(value) || isRgbOrHslColor(value) || (typeof isColorMix === 'function' && isColorMix(value)))) {
      if (typeof renderColorControl === 'function') {
        host.appendChild(renderColorControl(name, value));
      } else {
        // simple fallback: text box
        host.appendChild(renderSimpleText(name, value));
      }
      continue;
    }

    // 4) lengths
    if (typeof isLength === 'function' && isLength(value)) {
      host.appendChild(renderLengthControl(name, value));
      continue;
    }

    // 5) shadows
    if (typeof isShadow === 'function' && isShadow(value)) {
      host.appendChild(renderTextAreaPreview(name, value, 'shadow'));
      continue;
    }

    // 6) numbers → treat as px
    if (typeof isNumberOnly === 'function' && isNumberOnly(value)) {
      const unitized = `${value}px`;
      host.appendChild(renderLengthControl(name, unitized));
      continue;
    }

    // 7) fallback
    if (typeof renderSimpleText === 'function') {
      host.appendChild(renderSimpleText(name, value));
    }
  }
}




/* ==========================================================================
   UI Variables — Gradient & var() integrated editor
   - Adds: color stop pickers for gradients, angle slider for linear-gradient
   - Adds: var(--x) inspector with follow/dereference/reset
   - Non-invasive: enhances existing .ui-var-card in the UI tab at runtime
   - Persists via Bjorn.UIVars.saveLocal and applies on :root immediately
   ========================================================================== */
(function(){
  if (window.__BJORN_UI_GRAD_ADDON__) return;
  window.__BJORN_UI_GRAD_ADDON__ = true;

  // -------------------- helpers: type detection & parsing --------------------
  function isHexColor(v){ return /^#([0-9a-f]{3}|[0-9a-f]{6})\b$/i.test(String(v||'')); }
  function isRgbOrHslColor(v){ return /\b(?:rgb|hsl)a?\s*\(/i.test(String(v||'')); }
  function isColorToken(v){ return isHexColor(v) || isRgbOrHslColor(v); }
  function isGradient(v){ return /^\s*(?:linear|radial|conic)-gradient\(/i.test(String(v||'')); }
  function parseLinearAngle(v){
    const m = String(v||'').match(/linear-gradient\(\s*([0-9.\-]+)deg/i);
    return m ? parseFloat(m[1]) : 180; // browser default
  }
  function setLinearAngle(v, deg){
    v = String(v||'');
    if (/linear-gradient\(/i.test(v)){
      if (/linear-gradient\(\s*[0-9.\-]+deg/i.test(v)){
        return v.replace(/linear-gradient\(\s*[0-9.\-]+deg/i, `linear-gradient(${deg}deg`);
      } else {
        return v.replace(/linear-gradient\(/i, `linear-gradient(${deg}deg,`);
      }
    }
    return v;
  }
  function extractGradientColors(v){
    // capture #hex / rgb[a] (...) / hsl[a] (...)
    return String(v||'').match(/#([0-9a-f]{3}|[0-9a-f]{6})\b|(?:rgb|hsl)a?\([^)]*\)/ig) || [];
  }
  function replaceGradientColorAt(v, index, newColor){
    let i = -1;
    return String(v||'').replace(/#([0-9a-f]{3}|[0-9a-f]{6})\b|(?:rgb|hsl)a?\([^)]*\)/ig, (m) => {
      i++; return (i === index) ? newColor : m;
    });
  }
  // --- var() ---
  function parseVarRef(v){
    // var(--name, fallback)
    const m = String(v||'').match(/^\s*var\(\s*(--[a-z0-9\-_]+)\s*(?:,\s*([^)]+))?\)\s*$/i);
    if(!m) return null;
    return { ref: m[1], fallback: m[2]?.trim() ?? null };
  }
  function resolveCssVar(varName){
    // read effective value on :root
    return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  }

  // ------------------------------ UI builders --------------------------------
  function createGradientEditor(name, value){
    const card = document.createElement('div');
    card.className = 'ui-var-card';
    card.dataset.name = name;

    const title = document.createElement('div');
    title.className = 'ui-var-name';
    title.textContent = name;

    const preview = document.createElement('div');
    preview.style.width = '140px';
    preview.style.height = '36px';
    preview.style.borderRadius = '8px';
    preview.style.border = '1px solid rgba(255,255,255,.15)';
    preview.style.flex = '0 0 auto';
    preview.style.background = value;

    const body = document.createElement('div');
    body.style.flex = '1';
    body.style.display = 'grid';
    body.style.gap = '8px';

    // angle if linear-gradient(...)
    let current = value;
    const angleWrap = document.createElement('div');
    if (/^linear-gradient/i.test(value)){
      const label = document.createElement('label');
      label.textContent = 'Angle';
      const range = document.createElement('input');
      range.type = 'range'; range.min = '0'; range.max = '360'; range.step = '1';
      range.value = String(parseLinearAngle(value));
      range.addEventListener('input', ()=>{
        current = setLinearAngle(current, parseInt(range.value,10));
        preview.style.background = current;
        const cur = Bjorn.UIVars.loadLocal(); cur[name] = current; Bjorn.UIVars.saveLocal(cur);
        document.documentElement.style.setProperty(name, current);
      });
      angleWrap.append(label, range);
    }

    // color stops
    const colors = extractGradientColors(value);
    const stopsWrap = document.createElement('div');
    stopsWrap.style.display = 'flex'; stopsWrap.style.flexWrap = 'wrap'; stopsWrap.style.gap = '8px';

    colors.forEach((tok, idx)=>{
      let ctrl, init = tok;

      if (isHexColor(tok)){
        const norm = tok.length === 4
          ? ('#' + tok[1]+tok[1]+tok[2]+tok[2]+tok[3]+tok[3]).toLowerCase()
          : tok.toLowerCase();

        ctrl = document.createElement('input');
        ctrl.type = 'color';
        ctrl.value = norm;
        ctrl.title = `Stop ${idx+1}`;

        ctrl.addEventListener('input', ()=>{
          current = replaceGradientColorAt(current, idx, ctrl.value);
          preview.style.background = current;
          const cur = Bjorn.UIVars.loadLocal(); cur[name] = current; Bjorn.UIVars.saveLocal(cur);
          document.documentElement.style.setProperty(name, current);
        });
      } else {
        // rgb()/hsl() → text field (avoid fragile conversion)
        ctrl = document.createElement('input');
        ctrl.type = 'text';
        ctrl.value = init;
        ctrl.style.minWidth = '160px';
        ctrl.addEventListener('change', ()=>{
          const v = ctrl.value.trim();
          if (!v) return;
          current = replaceGradientColorAt(current, idx, v);
          preview.style.background = current;
          const cur = Bjorn.UIVars.loadLocal(); cur[name] = current; Bjorn.UIVars.saveLocal(cur);
          document.documentElement.style.setProperty(name, current);
        });
      }

      const group = document.createElement('div');
      group.style.display = 'flex'; group.style.alignItems = 'center'; group.style.gap = '6px';
      const lbl = document.createElement('span'); lbl.textContent = `Stop ${idx+1}`;
      lbl.style.fontSize = '11px'; lbl.style.opacity = '.7';
      group.append(lbl, ctrl);
      stopsWrap.appendChild(group);
    });

    // raw textarea (edit full gradient)
    const raw = document.createElement('textarea');
    raw.value = value;
    raw.rows = 2;
    raw.style.width = '100%';
    raw.style.resize = 'vertical';
    raw.addEventListener('change', ()=>{
      const v = raw.value.trim();
      if (!v) return;
      current = v;
      preview.style.background = current;
      const cur = Bjorn.UIVars.loadLocal(); cur[name] = current; Bjorn.UIVars.saveLocal(cur);
      document.documentElement.style.setProperty(name, current);
    });

    // Reset button (remove override → fallback to CSS initial)
    const btnReset = document.createElement('button');
    btnReset.className = 'btn';
    btnReset.textContent = 'Reset';
    btnReset.addEventListener('click', ()=>{
      const overrides = Bjorn.UIVars.loadLocal();
      delete overrides[name];
      Bjorn.UIVars.saveLocal(overrides);
      document.documentElement.style.removeProperty(name);
      const base = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || value;
      raw.value = base;
      preview.style.background = base;
    });

    body.append(angleWrap, stopsWrap, raw);
    card.append(title, preview, body, btnReset);
    return card;
  }

  function createVarEditor(name, value){
    const ref = parseVarRef(value);
    if (!ref) return null;

    const resolved = resolveCssVar(ref.ref) || ref.fallback || '';
    const card = document.createElement('div');
    card.className = 'ui-var-card';
    card.dataset.name = name;

    const title = document.createElement('div');
    title.className = 'ui-var-name';
    title.textContent = name;

    const info = document.createElement('div');
    info.style.display = 'grid';
    info.style.gap = '8px';
    info.style.flex = '1';

    const row1 = document.createElement('div');
    row1.style.display = 'flex';
    row1.style.alignItems = 'center';
    row1.style.gap = '8px';

    const refBadge = document.createElement('span');
    refBadge.className = 'badge-modern';
    refBadge.textContent = `ref: ${ref.ref}`;

    const resolvedBox = document.createElement('div');
    resolvedBox.textContent = `resolved: ${resolved || '(empty)'}`;
    resolvedBox.style.fontSize = '12px';
    resolvedBox.style.opacity = '.8';

    if (isGradient(resolved) || isColorToken(resolved)){
      const sw = document.createElement('div');
      sw.style.width = '28px'; sw.style.height = '18px';
      sw.style.borderRadius = '6px';
      sw.style.border = '1px solid rgba(255,255,255,.15)';
      sw.style.background = isGradient(resolved) ? resolved : resolved;
      row1.appendChild(sw);
    }

    row1.append(refBadge, resolvedBox);

    const row2 = document.createElement('div');
    row2.style.display = 'flex'; row2.style.gap = '8px';

    const btnFollow = document.createElement('button');
    btnFollow.className = 'btn';
    btnFollow.textContent = 'Follow →';
    btnFollow.addEventListener('click', ()=>{
      const target = document.querySelector(`.ui-var-card[data-name="${CSS.escape(ref.ref)}"]`);
      if (target){
        target.scrollIntoView({behavior:'smooth', block:'center'});
        target.animate([{outline:'2px solid var(--acid)'},{outline:'none'}], {duration:900});
      } else {
        window.toast?.(`Variable ${ref.ref} not found in the list`);
      }
    });

    const btnDereference = document.createElement('button');
    btnDereference.className = 'btn';
    btnDereference.textContent = 'Dereference';
    btnDereference.title = 'Replace this var() by its resolved value';
    btnDereference.addEventListener('click', ()=>{
      const val = resolved || ref.fallback || '';
      if (!val) return;
      document.documentElement.style.setProperty(name, val);
      const cur = Bjorn.UIVars.loadLocal(); cur[name] = val; Bjorn.UIVars.saveLocal(cur);
      window.toast?.(`\`${name}\` ← ${val}`);
    });

    const btnReset = document.createElement('button');
    btnReset.className = 'btn';
    btnReset.textContent = 'Reset';
    btnReset.addEventListener('click', ()=>{
      const overrides = Bjorn.UIVars.loadLocal();
      delete overrides[name];
      Bjorn.UIVars.saveLocal(overrides);
      document.documentElement.style.removeProperty(name);
    });

    row2.append(btnFollow, btnDereference, btnReset);
    info.append(row1, row2);

    card.append(title, info);
    return card;
  }

  // ------------------------------ enhancement --------------------------------
  function getVarNameFromCard(card){
    // try dataset first
    const name = card.dataset.name;
    if (name) return name;
    // else read from title label
    const t = card.querySelector('.ui-var-name');
    if (t) return t.textContent.trim();
    // else try first label
    const lab = card.querySelector('label');
    return lab ? lab.textContent.trim() : null;
  }

  function readValueForVar(name){
    const overrides = (window.Bjorn?.UIVars?.loadLocal?.() || {});
    if (Object.prototype.hasOwnProperty.call(overrides, name)) return overrides[name];
    const css = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return css || '';
  }

  function enhanceCard(card){
    if (!card || card.dataset.enhanced === '1') return;
    const name = getVarNameFromCard(card);
    if (!name || !name.startsWith('--')) return;

    const value = readValueForVar(name);
    let special = null;

    // var() wrapper takes priority
    const varRef = parseVarRef(value);
    if (varRef){
      special = createVarEditor(name, value);
    } else if (isGradient(value)){
      special = createGradientEditor(name, value);
    } else if (isColorToken(value)){
      // simple color -> ensure a color input exists next to the text field
      const inputRow = card.querySelector('.ui-var-input') || card;
      const swatch = document.createElement('input');
      // normalize #abc -> #aabbcc
      let hex = value;
      if (isHexColor(value) && value.length === 4){
        hex = '#' + value[1]+value[1]+value[2]+value[2]+value[3]+value[3];
      }
      swatch.type = 'color';
      swatch.value = isHexColor(hex) ? hex.toLowerCase() : '#000000';
      swatch.style.width='42px'; swatch.style.height='28px';
      swatch.addEventListener('input', ()=>{
        const val = swatch.value;
        const cur = Bjorn.UIVars.loadLocal(); cur[name] = val; Bjorn.UIVars.saveLocal(cur);
        document.documentElement.style.setProperty(name, val);
      });
      inputRow.prepend(swatch);
    }

    if (special){
      // Replace original card UI by our editor
      card.innerHTML = '';
      card.appendChild(special);
      card.dataset.enhanced = '1';
    }else{
      card.dataset.enhanced = '1';
    }
  }

  function enhanceAll(root){
    root = root || document;
    const cards = root.querySelectorAll('#uiVarsHost .ui-var-card');
    cards.forEach(enhanceCard);
  }

  // Observe UI tab for re-render
  const host = document.getElementById('uiVarsHost');
  if (host){
    enhanceAll(host);
    const mo = new MutationObserver((muts)=>{
      let need=false;
      for (const m of muts){
        if (m.type === 'childList' || m.type === 'subtree') { need=true; break; }
      }
      if (need) enhanceAll(host);
    });
    mo.observe(host, { childList:true, subtree:true });
  } else {
    // Fallback: try later when settings opens
    document.addEventListener('click', (e)=>{
      const btn = e.target.closest('#openSettings');
      if (btn){
        setTimeout(()=>{
          const h = document.getElementById('uiVarsHost');
          if (h) enhanceAll(h);
        }, 400);
      }
    });
  }

  // Public API
  window.Bjorn = window.Bjorn || {};
  window.Bjorn.UIGradAddon = { refresh: ()=>enhanceAll(document) };
})();

/* Free AI Video Editor frontend */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let VOICES = [];
const uploads = new Map();      // id -> {id,name,kind}
const state = {
  textBgm: null, imgBgm: null, clipBgm: null, audBgm: null,
  aud: null,
  images: [],                    // {id,name,caption,duration}
  audImages: [],
  clips: [],                     // {id,name,in,dur}
};

/* ---------- boot ---------- */
async function boot() {
  const meta = await (await fetch('/api/meta')).json();
  const pill = $('#enginePill');
  const pillText = pill.querySelector('span');
  if (meta.ok) { pillText.textContent = 'engine ready'; pill.classList.add('ok'); }
  else { pillText.textContent = 'ffmpeg missing'; pill.classList.add('bad'); }
  if (meta.version) $('#versionTag').textContent = 'v' + meta.version;
  VOICES = meta.voices || [];
  for (const sel of [$('#textVoice'), $('#imgVoice'), $('#audVoice')]) {
    sel.innerHTML = VOICES.map(v => `<option value="${v.id}">${v.label}</option>`).join('');
  }
  addScene(); addScene();
  bindTabs(); bindDropzones(); bindRunners();
  refreshJobs(); setInterval(refreshJobs, 2000);
}

/* ---------- tabs ---------- */
function activateTab(name) {
  const t = $(`.tab[data-tab="${name}"]`);
  if (!t) return;
  $$('.tab').forEach(x => { x.classList.remove('active'); x.setAttribute('aria-selected', 'false'); });
  $$('.panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  t.setAttribute('aria-selected', 'true');
  $('#panel-' + name).classList.add('active');
}
function bindTabs() {
  $$('.tab').forEach(t => t.addEventListener('click', () => {
    activateTab(t.dataset.tab);
    history.replaceState(null, '', '#' + t.dataset.tab);
  }));
  activateTab(new URLSearchParams(location.search).get('tab') || location.hash.slice(1) || 'text');
}

/* ---------- dropzones ---------- */
function dz(el, multiple, accept, onDone) {
  el.addEventListener('click', () => {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.multiple = !!multiple; if (accept) inp.accept = accept;
    inp.onchange = () => upload([...inp.files], onDone);
    inp.click();
  });
  el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('over'); });
  el.addEventListener('dragleave', () => el.classList.remove('over'));
  el.addEventListener('drop', e => {
    e.preventDefault(); el.classList.remove('over');
    upload([...e.dataTransfer.files], onDone);
  });
}
async function upload(files, onDone) {
  if (!files.length) return;
  const fd = new FormData();
  files.forEach(f => fd.append('files', f));
  const r = await fetch('/api/upload', { method: 'POST', body: fd });
  const j = await r.json();
  if (j.error) { alert(j.error); return; }
  onDone(j.uploads);
}
function bindDropzones() {
  dz($('#textBgmDz'), false, 'audio/*', us => { state.textBgm = us[0].id; $('#textBgmNote').textContent = 'Music: ' + us[0].name; });
  dz($('#imgBgmDz'), false, 'audio/*', us => { state.imgBgm = us[0].id; $('#imgBgmDz').textContent = 'Music: ' + us[0].name; });
  dz($('#clipBgmDz'), false, 'audio/*', us => { state.clipBgm = us[0].id; $('#clipBgmDz').textContent = 'Music: ' + us[0].name; });
  dz($('#audBgmDz'), false, 'audio/*', us => { state.audBgm = us[0].id; $('#audBgmDz').textContent = 'Music: ' + us[0].name; });
  dz($('#imgDz'), true, 'image/*', us => { us.filter(u => u.kind === 'image').forEach(u => state.images.push({ id: u.id, name: u.name, caption: '', duration: 3.5 })); renderImages(); });
  dz($('#audImgDz'), true, 'image/*', us => { us.filter(u => u.kind === 'image').forEach(u => state.audImages.push({ id: u.id, name: u.name })); renderAudImages(); });
  dz($('#clipDz'), true, 'video/*', us => { us.filter(u => u.kind === 'video').forEach(u => state.clips.push({ id: u.id, name: u.name, in: 0, dur: '' })); renderClips(); });
  dz($('#audDz'), false, 'audio/*', us => { state.aud = us[0].id; $('#audNote').textContent = 'Audio: ' + us[0].name; });
}

/* ---------- text scenes ---------- */
function renumberScenes() {
  $$('#scenes .scene').forEach((s, i) => {
    s.querySelector('.scene-n').textContent = 'Scene ' + (i + 1);
  });
}
function addScene(head = '', body = '', narr = '') {
  const node = $('#tplScene').content.firstElementChild.cloneNode(true);
  node.querySelector('.sHead').value = head;
  node.querySelector('.sBody').value = body;
  node.querySelector('.sNarr').value = narr;
  node.querySelector('.scene-x').onclick = () => {
    node.remove();
    if (!$('#scenes .scene')) addScene();
    renumberScenes();
  };
  $('#scenes').appendChild(node);
  renumberScenes();
}
$('#addScene').onclick = () => addScene();

/* ---------- image rows ---------- */
function renderImages() {
  const c = $('#imgList'); c.innerHTML = '';
  state.images.forEach((im, i) => {
    const row = document.createElement('div');
    row.className = 'assetRow';
    row.innerHTML = `<span class="nm">${esc(im.name)}</span>
      <input class="cap" placeholder="caption (spoken too)" value="${esc(im.caption)}">
      <label style="display:flex;align-items:center;gap:4px">dur
        <input type="number" value="${im.duration}" min="1" max="30" step="0.5" style="width:70px"></label>
      <div class="mv"><button data-a="up">▲</button><button data-a="dn">▼</button></div>
      <button class="x">✕</button>`;
    row.querySelector('.cap').oninput = e => im.caption = e.target.value;
    row.querySelectorAll('input[type=number]')[0].onchange = e => im.duration = parseFloat(e.target.value) || 3.5;
    row.querySelector('.x').onclick = () => { state.images.splice(i, 1); renderImages(); };
    row.querySelector('[data-a=up]').onclick = () => { if (i) { [state.images[i - 1], state.images[i]] = [state.images[i], state.images[i - 1]]; renderImages(); } };
    row.querySelector('[data-a=dn]').onclick = () => { if (i < state.images.length - 1) { [state.images[i + 1], state.images[i]] = [state.images[i], state.images[i + 1]]; renderImages(); } };
    c.appendChild(row);
  });
}

/* ---------- voice images ---------- */
function renderAudImages() {
  const c = $('#audImgList'); c.innerHTML = '';
  state.audImages.forEach((im, i) => {
    const row = document.createElement('div');
    row.className = 'assetRow';
    row.innerHTML = `<span class="nm">${esc(im.name)}</span><button class="x">✕</button>`;
    row.querySelector('.x').onclick = () => { state.audImages.splice(i, 1); renderAudImages(); };
    c.appendChild(row);
  });
}

/* ---------- clip rows ---------- */
function renderClips() {
  const c = $('#clipList'); c.innerHTML = '';
  state.clips.forEach((cl, i) => {
    const row = document.createElement('div');
    row.className = 'assetRow';
    row.innerHTML = `<span class="nm">${esc(cl.name)}</span>
      <label style="flex-direction:row;align-items:center;gap:4px">in
        <input class="cin" type="number" value="${cl.in}" min="0" step="0.1" style="width:70px"></label>
      <label style="flex-direction:row;align-items:center;gap:4px">dur
        <input class="cdur" placeholder="full" value="${esc(cl.dur)}" style="width:70px"></label>
      <div class="mv"><button data-a="up">▲</button><button data-a="dn">▼</button></div>
      <button class="x">✕</button>`;
    row.querySelector('.cin').onchange = e => cl.in = parseFloat(e.target.value) || 0;
    row.querySelector('.cdur').onchange = e => cl.dur = e.target.value.trim();
    row.querySelector('.x').onclick = () => { state.clips.splice(i, 1); renderClips(); };
    row.querySelector('[data-a=up]').onclick = () => { if (i) { [state.clips[i - 1], state.clips[i]] = [state.clips[i], state.clips[i - 1]]; renderClips(); } };
    row.querySelector('[data-a=dn]').onclick = () => { if (i < state.clips.length - 1) { [state.clips[i + 1], state.clips[i]] = [state.clips[i], state.clips[i + 1]]; renderClips(); } };
    c.appendChild(row);
  });
}

/* ---------- run jobs ---------- */
async function runJob(kind, params, btn) {
  btn.disabled = true; btn.textContent = 'rendering…';
  try {
    const r = await fetch('/api/jobs', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ kind, params }),
    });
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    refreshJobs();
    setTimeout(() => { btn.disabled = false; btn.textContent = btn.dataset.label || 'Render video'; }, 800);
  } catch (e) {
    alert('Error: ' + e.message);
    btn.disabled = false; btn.textContent = btn.dataset.label || 'Render video';
  }
}
function bindRunners() {
  $('#runText').dataset.label = 'Render video';
  $('#runImages').dataset.label = 'Render video';
  $('#runClips').dataset.label = 'Render video';
  $('#runVoice').dataset.label = 'Render video';

  $('#runText').onclick = e => {
    const scenes = $$('#scenes .scene').map(s => ({
      heading: s.querySelector('.sHead').value.trim(),
      body: s.querySelector('.sBody').value.trim(),
      narration: s.querySelector('.sNarr').value.trim(),
    })).filter(s => s.heading || s.body || s.narration);
    if (!scenes.length) return alert('add at least one scene');
    runJob('text-to-video', { scenes, voice: $('#textVoice').value, rate: $('#textRate').value, resolution: $('#textRes').value, bgm: state.textBgm }, e.target);
  };
  $('#runImages').onclick = e => {
    if (!state.images.length) return alert('add images first');
    runJob('images-to-video', { images: state.images, voice: $('#imgVoice').value, resolution: $('#imgRes').value, transition: $('#imgTrans').value, narrate_captions: $('#imgNarrate').checked, bgm: state.imgBgm }, e.target);
  };
  $('#runClips').onclick = e => {
    if (!state.clips.length) return alert('add clips first');
    runJob('clips-to-video', {
      clips: state.clips.map(c => ({ id: c.id, in: c.in, dur: c.dur || null })),
      transition: $('#clipTrans').value, trans_dur: parseFloat($('#clipTransDur').value) || 0.5,
      resolution: $('#clipRes').value, keep_audio: $('#clipAudio').checked,
      fade_out: $('#clipFade').checked, bgm: state.clipBgm,
    }, e.target);
  };
  $('#runVoice').onclick = e => {
    const mode = $('#capMode').value;
    runJob('voice-to-video', {
      audio: state.aud, narration_text: $('#audText').value.trim(),
      voice: $('#audVoice').value, images: state.audImages.map(i => i.id),
      title: $('#audTitle').value, resolution: $('#audRes').value,
      caption_lines: mode === 'lines' ? $('#capLines').value : '',
      caption_mode: mode, bgm: state.audBgm, transition: 'dissolve',
    }, e.target);
  };
}

/* ---------- jobs panel ---------- */
function ago(ts) {
  const s = Math.max(0, (Date.now() / 1000) - ts);
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
}

const jobEls = new Map();   // id -> {el, refs}

function buildJob(j) {
  const el = document.createElement('div');
  el.className = 'job';
  el.dataset.id = j.id;
  el.innerHTML = `
    <div class="jt"><span class="st-dot"></span>
      <span class="kind"></span><span class="ago"></span></div>
    <div class="bar"><i></i></div>
    <div class="stage"></div>
    <div class="err" hidden></div>
    <video controls preload="none" hidden></video>
    <div class="acts">
      <a class="dl" hidden>Download mp4</a>
      <button class="del">Delete</button></div>`;
  const refs = {
    dot: el.querySelector('.st-dot'), kind: el.querySelector('.kind'),
    ago: el.querySelector('.ago'), bar: el.querySelector('.bar'),
    fill: el.querySelector('.bar i'), stage: el.querySelector('.stage'),
    err: el.querySelector('.err'), video: el.querySelector('video'),
    dl: el.querySelector('.dl'),
  };
  refs.kind.textContent = (j.kind || '').replace(/-/g, ' ');
  el.querySelector('.del').onclick = async () => {
    await fetch('/api/jobs/' + j.id, { method: 'DELETE' });
    refreshJobs();
  };
  jobEls.set(j.id, { el, refs });
  return el;
}

function syncJob(entry, j) {
  const { el, refs } = entry;
  refs.ago.textContent = ago(j.created || 0);
  refs.dot.className = 'st-dot ' + j.status;
  const active = j.status === 'running' || j.status === 'queued';
  refs.bar.hidden = !active;
  refs.stage.hidden = !active;
  if (active) {
    refs.fill.style.width = (j.progress || 2) + '%';
    if (refs.stage.textContent !== (j.stage || '')) refs.stage.textContent = j.stage || '';
  }
  const done = j.status === 'done', failed = j.status === 'error';
  refs.err.hidden = !failed;
  if (failed && refs.err.textContent !== (j.error || '')) refs.err.textContent = j.error || 'failed';
  refs.video.hidden = !done;
  refs.dl.hidden = !done;
  if (done && !refs.video.src) {          // attach player exactly once — never rebuilt
    refs.video.src = `/api/jobs/${j.id}/stream`;
    refs.dl.href = `/api/jobs/${j.id}/result`;
    refs.dl.setAttribute('download', '');
  }
  el.dataset.status = j.status;
}

async function refreshJobs() {
  let list = [];
  try { list = await (await fetch('/api/jobs')).json(); } catch { return; }
  const c = $('#jobList');
  let empty = c.querySelector('.empty');
  if (!empty && !list.length) {
    empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'Nothing rendered yet.';
  }
  if (empty) empty.hidden = list.length > 0;
  if (!list.length && !empty) {
    c.innerHTML = '<div class="empty">Nothing rendered yet.</div>';
    jobEls.clear();
    return;
  }
  const seen = new Set();
  for (const j of list.slice(0, 14)) {
    seen.add(j.id);
    let entry = jobEls.get(j.id);
    if (!entry) {
      const el = buildJob(j);
      c.prepend(el);                     // newest first; element is never rebuilt after
      entry = jobEls.get(j.id);
    }
    syncJob(entry, j);
  }
  for (const [id, entry] of jobEls) {
    if (!seen.has(id)) { entry.el.remove(); jobEls.delete(id); }
  }
}

function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
boot();

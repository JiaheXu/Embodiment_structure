'use strict';

(() => {
  const $ = id => document.getElementById(id);
  const canvas = $('paper-sphere');
  const ctx = canvas.getContext('2d');
  const stage = $('sphere-stage');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const state = {nodes: [], groups: [], active: new Set(), positions: [], projected: [],
    yaw: -.35, pitch: -.12, zoom: 1, rotating: !reducedMotion.matches,
    selected: new Set(), highlights: null, lastResults: null, view: null, operation: 0, width: 1, height: 1, lastInteraction: 0};
  const ingestionStorageKey = 'robotlit.ingestion-runs';
  let sourceRoots = [], indexing = false, monitoring = false;
  const compact = window.matchMedia('(max-width: 1150px)');
  $('collection-browser').open = !compact.matches;
  compact.addEventListener('change', () => {$('collection-browser').open = !compact.matches;});

  function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  }

  function link(label, url) {
    const a = element('a', label);
    a.href = url; a.target = '_blank'; a.rel = 'noopener';
    return a;
  }

  async function api(url, body, signal) {
    const response = await fetch(url, {signal, ...(body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})});
    const value = await response.json();
    if (!response.ok) {
      const error = new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
      error.status = response.status; throw error;
    }
    return value;
  }

  function message(text, error = false) {
    $('status').textContent = text;
    $('status').setAttribute('role', error ? 'alert' : 'status');
  }

  function randomFor(id) {
    let seed = 2166136261;
    for (const char of id) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619);
    return () => {seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return (seed >>> 0) / 4294967296;};
  }

  function setupPositions() {
    const centers = new Map();
    state.groups.forEach((group, index) => {
      const y = 1 - 2 * (index + .5) / state.groups.length;
      const angle = index * Math.PI * (3 - Math.sqrt(5));
      const ring = Math.sqrt(1 - y * y);
      centers.set(group.id, {x: Math.cos(angle) * ring, y, z: Math.sin(angle) * ring});
    });
    state.positions = state.nodes.map(paper => {
      const center = centers.get(paper.group_id);
      const random = randomFor(paper.id);
      const x = center.x + (random() - .5) * .5;
      const y = center.y + (random() - .5) * .5;
      const z = center.z + (random() - .5) * .5;
      const scale = (.85 + random() * .14) / Math.hypot(x, y, z);
      return {paper, x: x * scale, y: y * scale, z: z * scale};
    });
    state.anchors = state.groups.map(group => ({group, ...centers.get(group.id)}));
  }

  function resize() {
    state.width = stage.clientWidth; state.height = stage.clientHeight;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = state.width * ratio; canvas.height = state.height * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw();
  }

  function project(point) {
    const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw);
    const cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
    const x = point.x * cy + point.z * sy;
    const z0 = -point.x * sy + point.z * cy;
    const y = point.y * cp - z0 * sp;
    const z = point.y * sp + z0 * cp;
    const radius = Math.min(state.width * .36, state.height * .405) * state.zoom;
    const perspective = 2.7 / (2.7 - z * .34);
    return {x: state.width / 2 + x * radius * perspective, y: state.height / 2 - y * radius * perspective, z, scale: perspective};
  }

  function isVisible(paper) { return state.active.has(paper.group_id); }

  function draw() {
    const w = state.width, h = state.height;
    ctx.clearRect(0, 0, w, h);
    const r = Math.min(w * .36, h * .405) * state.zoom;
    const gradient = ctx.createRadialGradient(w / 2 - r * .2, h / 2 - r * .3, 0, w / 2, h / 2, r);
    gradient.addColorStop(0, '#32313e60'); gradient.addColorStop(.75, '#28283124'); gradient.addColorStop(1, '#22212908');
    ctx.fillStyle = gradient; ctx.beginPath(); ctx.arc(w / 2, h / 2, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#89839b22'; ctx.lineWidth = .8; ctx.stroke();
    for (let axis = 0; axis < 3; axis++) {
      ctx.beginPath();
      for (let i = 0; i <= 96; i++) {
        const a = i / 96 * Math.PI * 2;
        const p = project(axis === 0 ? {x: Math.cos(a), y: 0, z: Math.sin(a)} :
          axis === 1 ? {x: 0, y: Math.cos(a), z: Math.sin(a)} : {x: Math.cos(a), y: Math.sin(a), z: 0});
        if (!i) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
      }
      ctx.strokeStyle = '#81798e18'; ctx.stroke();
    }
    const anchors = state.anchors?.filter(a => state.active.has(a.group.id)).map(a => ({...a, ...project(a)})) || [];
    const byGroup = new Map(anchors.map(a => [a.group.id, a]));
    const points = state.positions.filter(p => isVisible(p.paper)).map(p => ({...p, ...project(p)})).sort((a, b) => a.z - b.z);
    if ($('show-links').checked) {
      ctx.lineWidth = .5;
      for (const p of points) {
        const anchor = byGroup.get(p.paper.group_id);
        ctx.globalAlpha = .025 + Math.max(0, p.z) * .045;
        ctx.strokeStyle = anchor.group.color;
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(anchor.x, anchor.y); ctx.stroke();
      }
    }
    state.projected = [];
    for (const p of points) {
      const group = byGroup.get(p.paper.group_id).group;
      const selected = state.selected.has(p.paper.id);
      const highlighted = state.highlights?.has(p.paper.id);
      const faded = state.highlights && !highlighted && !selected;
      ctx.globalAlpha = faded ? .1 : .18 + (p.z + 1) * .35;
      const radius = (selected ? 6 : highlighted ? 4 : 2.4) * p.scale;
      ctx.fillStyle = group.color;
      ctx.shadowColor = group.color; ctx.shadowBlur = selected || highlighted ? 13 : 0;
      ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;
      if (selected) {ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.3; ctx.stroke();}
      state.projected.push({...p, type: 'paper', radius});
    }
    const labels = [];
    for (const a of anchors.sort((a, b) => a.z - b.z)) {
      const radius = (7 + Math.min(6, Math.sqrt(a.group.count) / 2)) * a.scale;
      ctx.globalAlpha = .2 + (a.z + 1) * .38;
      ctx.shadowColor = a.group.color; ctx.shadowBlur = a.z > 0 ? 18 : 5;
      ctx.fillStyle = a.group.color;
      ctx.beginPath(); ctx.arc(a.x, a.y, radius, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0; ctx.fillStyle = '#ffffff'; ctx.beginPath(); ctx.arc(a.x, a.y, 2.3 * a.scale, 0, Math.PI * 2); ctx.fill();
      if ($('show-labels').checked && a.z > -.2) labels.push({...a, radius});
      state.projected.push({...a, type: 'group', radius});
    }
    const boxes = [];
    ctx.font = '11px system-ui'; ctx.fillStyle = '#dddae8'; ctx.textAlign = 'left';
    for (const a of labels.sort((a, b) => b.z - a.z)) {
      const width = ctx.measureText(a.group.label).width;
      const x = Math.max(8, Math.min(w - width - 8, a.x + a.radius + 9));
      for (const offset of [0, -15, 15, -30, 30]) {
        const y = a.y + 4 + offset, box = {left: x, right: x + width, top: y - 12, bottom: y + 4};
        if (box.top < 8 || box.bottom > h - 8 || boxes.some(b => box.left < b.right + 4 && box.right > b.left - 4 && box.top < b.bottom + 3 && box.bottom > b.top - 3)) continue;
        ctx.globalAlpha = .65 + Math.max(0, a.z) * .3;
        ctx.fillText(a.group.label, x, y); boxes.push(box); break;
      }
    }
    ctx.globalAlpha = 1; ctx.textAlign = 'left';
  }

  function pick(x, y) {
    return state.projected.filter(p => Math.hypot(x - p.x, y - p.y) < Math.max(p.radius + 5, 9))
      .sort((a, b) => b.z - a.z)[0];
  }

  function updateList() {
    const query = $('quick-find').value.trim().toLocaleLowerCase();
    const papers = state.nodes.filter(n => isVisible(n) && (!query || n.title.toLocaleLowerCase().includes(query)));
    $('paper-list').replaceChildren();
    for (const paper of papers.slice(0, 100)) {
      const button = element('button', paper.title, 'side-paper' + (state.selected.has(paper.id) ? ' selected' : ''));
      const availability = paper.search_ready ? 'PDF indexed' : paper.summary ? 'Summary available' : 'Not indexed yet';
      button.append(element('small', paper.year ? `${paper.year} · ${availability}` : availability));
      button.onclick = () => selectPaper(paper);
      $('paper-list').append(button);
    }
    if (!papers.length) $('paper-list').append(element('p', 'No papers match these filters.', 'side-note'));
    if (papers.length > 100) $('paper-list').append(element('p', 'Showing 100 papers. Filter by title to find more.', 'side-note'));
    $('collection-count').textContent = papers.length;
    $('visible-count').textContent = `${state.nodes.filter(isVisible).length} papers on the sphere`;
  }

  function resultHeader(title, subtitle) {
    $('result-title').textContent = title; $('result-subtitle').textContent = subtitle;
    $('result-content').replaceChildren(); $('result-actions').replaceChildren();
  }

  function card(paper, status = 'collection paper') {
    const source = paper.source_url || (paper.document_id ? `/v1/documents/${paper.document_id}/pdf` : null);
    const el = element('article', undefined, 'paper-card');
    const title = element('h3');
    title.append(source ? link(paper.title, source) : document.createTextNode(paper.title));
    el.append(element('span', status.replaceAll('_', ' '), 'badge ' + status), title);
    const groupId = paper.group_id || state.nodes.find(n => paper.document_id ? n.document_id === paper.document_id : source && n.source_url === source)?.group_id;
    const category = state.groups.find(g => g.id === groupId)?.label || 'Research literature';
    el.append(element('div', paper.year ? `${paper.year} · ${category}` : category, 'paper-meta'));
    const preview = paper.summary || paper.summary_hits?.[0]?.text;
    if (preview) {
      const details = element('details'); details.append(element('summary', 'Read summary · unverified'), element('pre', preview)); el.append(details);
    }
    for (const config of paper.configurations || []) {
      const details = element('details'); details.append(element('summary', `${config.label}: ${config.status}`));
      for (const judgment of [...config.judgments, ...(config.record_judgments || [])])
        details.append(element('p', `${judgment.id}: ${judgment.outcome}${judgment.explanation ? ' — ' + judgment.explanation : ''}`));
      el.append(details);
    }
    for (const passage of (paper.source_passages || []).slice(0, 4)) {
      const details = element('details'); details.append(element('summary', `PDF evidence · page ${passage.pdf_page}`), element('blockquote', passage.text), link('Open this source page ↗', passage.source_url)); el.append(details);
    }
    const links = element('div', undefined, 'card-links');
    if (source) links.append(link('Open PDF ↗', source));
    if (paper.paper_id) links.append(link('Paper record ↗', `/v1/papers/${paper.paper_id}`));
    if (!source) el.append(element('p', (preview ? 'Summary available. ' : 'PDF not yet indexed. ') + 'Use Rebuild RAG to load the collection and inspect original PDF evidence.'));
    el.append(links); return el;
  }

  function showPapers(papers, title, subtitle) {
    resultHeader(title, subtitle);
    const grid = element('div', undefined, 'results-grid');
    for (const paper of papers) grid.append(card(paper));
    $('result-content').append(grid);
  }

  function selectPaper(paper) {
    state.view = {kind: 'paper', id: paper.id, key: paper.paper_key};
    state.operation++; state.selected = new Set([paper.id]); state.highlights = null;
    state.lastResults = null;
    $('search-button').disabled = false;
    const group = state.groups.find(g => g.id === paper.group_id);
    showPapers([paper], 'Selected paper', `${group.label} · selected from the sphere`);
    $('selection-hint').textContent = paper.title;
    message('Paper selected. Its summary and available source links are shown below.');
    updateList(); draw();
    $('results').scrollIntoView({behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'start'});
  }

  function selectGroup(group) {
    state.view = {kind: 'group', id: group.id};
    state.operation++; state.selected.clear();
    state.lastResults = null;
    $('search-button').disabled = false;
    const papers = state.nodes.filter(p => p.group_id === group.id);
    state.highlights = new Set(papers.map(p => p.id));
    showPapers(papers, group.label, `${papers.length} papers · local topic grouping`);
    $('selection-hint').textContent = `Exploring ${group.label.toLowerCase()}`;
    message('Topic group selected. These are exploration candidates, not verified matches.'); draw(); updateList();
    $('results').scrollIntoView({behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'start'});
  }

  async function search(question) {
    state.view = {kind: 'search', question};
    const operation = ++state.operation;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    $('search-button').disabled = true; message('Looking for papers in your local collection…');
    try {
      const {run_id} = await api('/v1/search', {question}, controller.signal);
      let run;
      while (operation === state.operation) {
        run = await api(`/v1/search/${run_id}`, undefined, controller.signal);
        if (['succeeded', 'failed', 'partial', 'deferred'].includes(run.state)) break;
        await new Promise(resolve => setTimeout(resolve, 650));
      }
      if (operation !== state.operation) return;
      if (run.state === 'failed') throw new Error(run.error || 'Search failed');
      const out = run.result;
      state.lastResults = out;
      resultHeader(question, `${out.coverage.documents_evaluated} indexed PDFs reviewed · ${out.coverage.documents_in_snapshot} in snapshot`);
      state.highlights = new Set(); state.selected.clear();
      let total = 0;
      for (const bucket of ['confirmed', 'partial', 'unresolved', 'discovery_only', 'excluded']) {
        if (!out[bucket]?.length) continue;
        $('result-content').append(element('h3', `${bucket.replaceAll('_', ' ')} · ${out[bucket].length}`));
        const grid = element('div', undefined, 'results-grid');
        for (const paper of out[bucket]) {
          total++; grid.append(card(paper, bucket));
        }
        $('result-content').append(grid);
      }
      highlightResults(out);
      if (!total) $('result-content').append(element('div', 'No candidates found. Try broader terms or use Rebuild RAG to index your collection.', 'empty-state'));
      for (const format of ['json', 'markdown']) $('result-actions').append(link(format.toUpperCase() + ' ↗', `/v1/search/${run_id}/export?format=${format}`));
      message(`${total} candidates found. Unresolved results still need source review before their requirements can be confirmed.`);
      draw(); updateList();
      $('results').scrollIntoView({behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'start'});
    } catch (error) {
      if (operation === state.operation) message(error.name === 'AbortError' ? 'Search is taking longer than expected. Check that the worker is running, then retry.' : error.message, true);
    } finally {clearTimeout(timeout); if (operation === state.operation) $('search-button').disabled = false;}
  }

  function highlightResults(out) {
    state.highlights = new Set();
    for (const bucket of ['confirmed', 'partial', 'unresolved', 'discovery_only'])
      for (const paper of out[bucket] || [])
        for (const n of state.nodes)
          if (paper.document_id ? n.document_id === paper.document_id : !n.document_id && n.title === paper.title)
            state.highlights.add(n.id);
    $('selection-hint').textContent = `${state.highlights.size} candidate nodes highlighted`;
  }

  let drag = null;
  canvas.addEventListener('pointerdown', event => {
    canvas.setPointerCapture(event.pointerId); drag = {x: event.clientX, y: event.clientY, moved: 0};
    state.lastInteraction = performance.now(); $('sphere-tooltip').hidden = true;
  });
  canvas.addEventListener('pointermove', event => {
    const rect = canvas.getBoundingClientRect();
    if (drag) {
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      state.yaw += dx * .007; state.pitch = Math.max(-1.5, Math.min(1.5, state.pitch + dy * .007));
      drag.moved += Math.abs(dx) + Math.abs(dy); drag.x = event.clientX; drag.y = event.clientY;
      state.lastInteraction = performance.now(); draw(); return;
    }
    const hit = pick(event.clientX - rect.left, event.clientY - rect.top);
    $('sphere-tooltip').hidden = !hit;
    canvas.style.cursor = hit ? 'pointer' : 'grab';
    if (hit) {
      $('sphere-tooltip').textContent = hit.type === 'group' ? `${hit.group.label} · ${hit.group.count} papers` : hit.paper.title;
      $('sphere-tooltip').style.left = `${Math.max(8, Math.min(event.clientX - rect.left + 13, state.width - 300))}px`;
      $('sphere-tooltip').style.top = `${Math.min(event.clientY - rect.top + 13, state.height - 70)}px`;
    }
  });
  canvas.addEventListener('pointerup', event => {
    if (drag && drag.moved < 7) {
      const rect = canvas.getBoundingClientRect(), hit = pick(event.clientX - rect.left, event.clientY - rect.top);
      if (hit?.type === 'paper') selectPaper(hit.paper); else if (hit?.type === 'group') selectGroup(hit.group);
    }
    drag = null; state.lastInteraction = performance.now();
  });
  canvas.addEventListener('pointercancel', () => {drag = null;});
  canvas.addEventListener('pointerleave', () => {$('sphere-tooltip').hidden = true;});
  canvas.addEventListener('wheel', event => {event.preventDefault(); state.zoom = Math.max(.65, Math.min(1.5, state.zoom - event.deltaY * .001)); state.lastInteraction = performance.now(); draw();}, {passive: false});
  canvas.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '-', ' '].includes(event.key)) return;
    event.preventDefault(); state.lastInteraction = performance.now();
    if (event.key === 'ArrowLeft') state.yaw -= .12;
    if (event.key === 'ArrowRight') state.yaw += .12;
    if (event.key === 'ArrowUp') state.pitch = Math.min(1.5, state.pitch + .12);
    if (event.key === 'ArrowDown') state.pitch = Math.max(-1.5, state.pitch - .12);
    if (event.key === '+') state.zoom = Math.min(1.5, state.zoom + .1);
    if (event.key === '-') state.zoom = Math.max(.65, state.zoom - .1);
    if (event.key === ' ') $('rotation-toggle').click();
    draw();
  });

  function updateRotationButton() {$('rotation-toggle').textContent = state.rotating ? 'Pause rotation' : 'Resume rotation'; $('rotation-toggle').setAttribute('aria-pressed', String(state.rotating));}
  $('rotation-toggle').onclick = () => {state.rotating = !state.rotating; updateRotationButton();};
  $('reset-view').onclick = () => {state.yaw = -.35; state.pitch = -.12; state.zoom = 1; draw();};
  for (const id of ['show-labels', 'show-links']) $(id).onchange = draw;
  $('quick-find').oninput = updateList;
  $('reset-filters').onclick = () => {state.active = new Set(state.groups.map(g => g.id)); for (const input of $('topic-options').querySelectorAll('input')) input.checked = true; updateList(); draw();};
  $('search').onsubmit = event => {event.preventDefault(); search($('question').value.trim());};
  document.querySelectorAll('[data-query]').forEach(button => {button.onclick = () => {$('question').value = button.dataset.query; search(button.dataset.query);};});
  reducedMotion.addEventListener('change', () => {if (reducedMotion.matches) {state.rotating = false; updateRotationButton();}});
  new ResizeObserver(resize).observe(stage);

  let lastFrame = 0;
  function animate(now) {
    if (state.rotating && !drag && !document.hidden && now - state.lastInteraction > 4000 && now - lastFrame >= 30) {
      state.yaw += Math.min(now - lastFrame, 40) * .000055; draw();
      lastFrame = now;
    }
    if (!state.rotating || drag || document.hidden || now - state.lastInteraction <= 4000) lastFrame = now;
    requestAnimationFrame(animate);
  }

  async function loadGraph() {
    try {
      const graph = await api('/v1/sphere');
      sourceRoots = graph.source_roots || ['papers'];
      const previousGroups = new Set(state.groups.map(g => g.id));
      const previouslyActive = state.active;
      state.nodes = graph.nodes; state.groups = graph.groups;
      state.active = new Set(graph.groups.filter(g => !previousGroups.has(g.id) || previouslyActive.has(g.id)).map(g => g.id));
      $('topic-count').textContent = graph.groups.length;
      $('health').textContent = `${graph.nodes.length} collection papers`;
      $('topic-options').replaceChildren();
      for (const group of graph.groups) {
        const label = element('label', undefined, 'topic-row');
        const input = element('input'); input.type = 'checkbox'; input.checked = state.active.has(group.id);
        input.onchange = () => {if (input.checked) state.active.add(group.id); else state.active.delete(group.id); updateList(); draw();};
        const dot = element('span', undefined, 'dot'); dot.style.background = group.color;
        const count = element('button', group.count, 'count');
        count.type = 'button'; count.setAttribute('aria-label', `Show ${group.count} ${group.label} papers`);
        count.onclick = event => {event.preventDefault(); event.stopPropagation(); selectGroup(group);};
        label.append(input, dot, element('span', group.label), count); $('topic-options').append(label);
      }
      setupPositions(); updateList(); updateRotationButton(); resize();
      if (state.lastResults) {highlightResults(state.lastResults); draw();}
      if (graph.inventory_warnings?.length) message(graph.inventory_warnings.join(' '));
      if (!graph.nodes.length) message('Your collection is empty. Use Rebuild RAG to load all local papers.');
      $('rebuild-index').disabled = indexing || !sourceRoots.length;
      return true;
    } catch (error) {message('Could not load your collection: ' + error.message, true); $('visible-count').textContent = 'Collection unavailable';}
    return false;
  }

  function persistIngestion(ids, errors = []) {
    try {if (ids.length) localStorage.setItem(ingestionStorageKey, JSON.stringify({ids, errors})); else localStorage.removeItem(ingestionStorageKey);} catch (_) { /* Progress still works when browser storage is disabled. */ }
  }

  function savedIngestion() {
    try {
      const record = JSON.parse(localStorage.getItem(ingestionStorageKey) || 'null');
      const ids = Array.isArray(record) ? record : record?.ids;
      if (Array.isArray(ids) && ids.length && ids.every(id => typeof id === 'string' && /^[0-9a-f-]{36}$/i.test(id)))
        return {ids, errors: Array.isArray(record.errors) ? record.errors.filter(e => typeof e === 'string') : []};
      persistIngestion([]);
    } catch (_) { /* A damaged progress record does not hide the collection. */ }
    return null;
  }

  function showIndexProgress(runs) {
    $('index-progress').hidden = false;
    const totals = runs.reduce((sum, run) => {
      const r = run.result || {};
      sum.ready += r.searchable || 0; sum.failed += r.failed || 0; sum.pending += r.pending || 0;
      sum.scanned += r.inventoried || 0; sum.preparing ||= !run.result;
      return sum;
    }, {ready: 0, failed: 0, pending: 0, scanned: 0, preparing: false});
    const finished = runs.every(run => ['succeeded', 'partial', 'failed'].includes(run.state));
    const failedRun = runs.find(run => run.state === 'failed');
    const reloadError = runs.find(run => run.result?.reload_error)?.result.reload_error;
    const hasFailures = !!failedRun || totals.failed > 0 || !!reloadError;
    $('index-state').textContent = finished ? hasFailures ? 'Indexing finished with failures' : 'Index ready' : 'Building the paper index';
    $('index-counts').textContent = `${totals.ready} indexed · ${totals.pending} pending · ${totals.failed} failed`;
    const meter = $('index-meter');
    if (totals.preparing && !finished) meter.removeAttribute('value');
    else {meter.max = Math.max(1, totals.ready + totals.pending + totals.failed); meter.value = totals.ready + totals.failed;}
    $('index-message').className = hasFailures ? 'error' : '';
    $('index-message').textContent = reloadError ? `Search indexes are available, but the title catalog could not refresh: ${reloadError}` :
      failedRun ? failedRun.error || 'An ingestion run failed. Check the worker logs.' :
      finished ? `Loaded ${totals.scanned} PDF paths. ${totals.ready} unique document indexes are available; unchanged indexes were reused.` :
      totals.preparing ? 'Queued or scanning all local PDFs. Keep robotlit worker running; progress appears once snapshots are ready.' :
      `Scanned ${totals.scanned} PDF paths. The worker is processing the remaining documents.`;
    return finished;
  }

  async function monitorIngestion(ids, errors = []) {
    if (monitoring) return;
    monitoring = indexing = true; $('rebuild-index').disabled = true;
    $('rebuild-index').textContent = 'Indexing…';
    try {
      while (true) {
        const results = await Promise.allSettled(ids.map(id => api(`/v1/ingest/${encodeURIComponent(id)}`)));
        const runs = [], retained = [];
        let pollError;
        results.forEach((result, i) => {
          if (result.status === 'fulfilled') {runs.push(result.value); retained.push(ids[i]);}
          else if ([404, 422].includes(result.reason.status)) errors.push(`Saved indexing run ${ids[i]} is unavailable.`);
          else {retained.push(ids[i]); pollError = result.reason;}
        });
        ids = retained; persistIngestion(ids, errors);
        const complete = showIndexProgress([...runs, ...errors.map(error => ({state: 'failed', error}))]);
        if (pollError) throw pollError;
        if (complete) break;
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
      persistIngestion([]);
      const operation = state.operation;
      if (await loadGraph() && operation === state.operation && state.view) {
        const view = state.view;
        if (view.kind === 'search') void search(view.question);
        else if (view.kind === 'group') {
          const group = state.groups.find(g => g.id === view.id);
          if (group) selectGroup(group);
        } else {
          const paper = state.nodes.find(p => p.id === view.id);
          const matches = paper ? [paper] : state.nodes.filter(p => p.paper_key === view.key);
          if (matches.length === 1) selectPaper(matches[0]);
          else showPapers(matches, 'Selected paper', `${matches.length} title matches in the refreshed collection`);
        }
      }
    } catch (error) {
      $('index-progress').hidden = false; $('index-state').textContent = 'Index progress unavailable';
      $('index-message').className = 'error';
      $('index-message').textContent = `${error.message}. The queued work can continue. Refresh to reconnect.`;
    } finally {
      monitoring = false; indexing = false;
      $('rebuild-index').disabled = !sourceRoots.length; $('rebuild-index').textContent = 'Rebuild RAG ↻';
    }
  }

  $('rebuild-index').onclick = async () => {
    if (indexing) return;
    const saved = savedIngestion();
    if (saved) {await monitorIngestion(saved.ids, saved.errors); return;}
    indexing = true; $('rebuild-index').disabled = true;
    $('index-progress').hidden = false; $('index-state').textContent = 'Loading all papers';
    $('index-message').className = ''; $('index-message').textContent = 'Queuing every configured source root, without a paper limit.';
    const ids = [], errors = [];
    for (const root of sourceRoots) {
      try {
        const {run_id} = await api('/v1/ingest', {source_root: root});
        ids.push(run_id);
      } catch (error) {errors.push(`${root}: ${error.message}`);}
      persistIngestion(ids, errors);
    }
    await monitorIngestion(ids, errors);
  };

  async function initialize() {
    await loadGraph(); requestAnimationFrame(animate);
    const saved = savedIngestion();
    if (saved) await monitorIngestion(saved.ids, saved.errors);
  }
  initialize();
})();

/**
 * LivingMemory Persona Dashboard - Frontend Core Application
 * 
 * Provides interactive categorized memory browsing, searching,
 * editing, and cross-persona transfer powered by AstrBot Bridge.
 */

// 1. Bridge SDK Compatibility (Supports AstrBot 4.28+ pages and latest views)
const bridge = window.AstrBotPluginPage || window.AstrBotPluginView || null;

// Palette for Persona Avatars
const AVATAR_COLORS = [
  'linear-gradient(135deg, #6366f1, #3b82f6)',
  'linear-gradient(135deg, #ec4899, #8b5cf6)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #06b6d4, #0284c7)',
  'linear-gradient(135deg, #84cc16, #16a34a)',
  'linear-gradient(135deg, #f43f5e, #be123c)',
  'linear-gradient(135deg, #8b5cf6, #6d28d9)',
];

function getAvatarGradient(name) {
  if (!name || name === '__all__') return 'linear-gradient(135deg, #3b82f6, #1d4ed8)';
  if (name === '__unassigned__') return 'linear-gradient(135deg, #64748b, #475569)';
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % AVATAR_COLORS.length;
  return AVATAR_COLORS[index];
}

function getAvatarInitial(name) {
  if (!name || name === '__all__') return '全';
  if (name === '__unassigned__') return '通';
  return name.trim().charAt(0).toUpperCase();
}

// 2. Application State
const state = {
  dbStatus: null,
  personas: [],
  selectedPersonaId: '__all__',
  memories: [],
  total: 0,
  page: 1,
  pageSize: 15,
  totalPages: 1,
  selectedIds: new Set(),
  expandedMemoryIds: new Set(),
  expandedDetailsCache: new Map(), // memory_id -> detail object
  filters: {
    keyword: '',
    type: 'all',
    status: 'active',
    sort: 'created_desc',
  },
  searchDebounceTimer: null,
};

// 3. API Caller Wrapper
async function callApi(endpoint, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const params = options.params || {};
  const body = options.body || null;

  if (bridge) {
    if (method === 'GET') {
      return await bridge.apiGet(endpoint, params);
    } else if (method === 'POST') {
      return await bridge.apiPost(endpoint, body || {});
    }
  }

  // Fallback for standalone dev preview
  let url = `/api/v1/plugins/extensions/astrbot_plugin_lm_persona_dashboard/${endpoint}`;
  if (method === 'GET' && Object.keys(params).length > 0) {
    const q = new URLSearchParams(params).toString();
    url += (url.includes('?') ? '&' : '?') + q;
  }

  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: method === 'POST' ? JSON.stringify(body || {}) : undefined,
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errText}`);
  }
  return await res.json();
}

// 4. Toast Notification
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✓' : type === 'error' ? '⚠️' : 'ℹ️'}</span>
    <span>${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 5. Data Fetching
async function checkStatus() {
  const statusBadge = document.getElementById('btn-db-status');
  const statusText = document.getElementById('status-text');
  try {
    const data = await callApi('status');
    state.dbStatus = data;
    if (data.connected) {
      statusBadge.className = 'status-badge connected';
      statusText.textContent = `已连接: ${data.documents_count} 条记忆 (${data.personas_count} 人格)`;
      statusBadge.title = `数据库：${data.db_path} (${data.file_size_display})`;
    } else {
      statusBadge.className = 'status-badge error';
      statusText.textContent = '未连接数据库';
      statusBadge.title = data.message || '点击配置数据源';
    }
    renderDbModal();
  } catch (err) {
    statusBadge.className = 'status-badge error';
    statusText.textContent = '连接异常';
    console.error('Check status error:', err);
  }
}

async function fetchPersonas() {
  const container = document.getElementById('persona-list');
  try {
    const data = await callApi('personas');
    state.personas = data.personas || [];
    renderPersonaList();
    updateBatchPersonaSelect();
    renderHeroCard();
  } catch (err) {
    container.innerHTML = `<div class="loading-placeholder error">加载人格列表失败: ${escapeHtml(err.message)}</div>`;
  }
}

async function fetchMemories() {
  const container = document.getElementById('memory-cards-list');
  container.innerHTML = '<div class="loading-placeholder">正在加载当前分类记忆...</div>';
  state.selectedIds.clear();
  updateBatchBar();

  try {
    const params = {
      persona_id: state.selectedPersonaId,
      keyword: state.filters.keyword,
      type: state.filters.type,
      status: state.filters.status,
      sort: state.filters.sort,
      page: state.page,
      page_size: state.pageSize,
    };

    const res = await callApi('memories', { params });
    state.memories = res.items || [];
    state.total = res.total || 0;
    state.totalPages = res.total_pages || 1;
    renderMemoryCards();
    renderPagination();
  } catch (err) {
    container.innerHTML = `<div class="loading-placeholder error">加载记忆失败: ${escapeHtml(err.message)}</div>`;
  }
}

// 6. Rendering Logic
function renderPersonaList() {
  const container = document.getElementById('persona-list');
  const filterVal = (document.getElementById('persona-filter-input').value || '').trim().toLowerCase();
  document.getElementById('persona-total-badge').textContent = state.personas.length;

  const filtered = state.personas.filter((p) => {
    if (!filterVal) return true;
    return (
      p.name.toLowerCase().includes(filterVal) ||
      p.persona_id.toLowerCase().includes(filterVal) ||
      (p.system_prompt && p.system_prompt.toLowerCase().includes(filterVal))
    );
  });

  if (filtered.length === 0) {
    container.innerHTML = '<div class="loading-placeholder">无匹配的角色人格</div>';
    return;
  }

  container.innerHTML = '';
  filtered.forEach((p) => {
    const item = document.createElement('div');
    const isActive = p.persona_id === state.selectedPersonaId;
    item.className = `persona-item ${isActive ? 'active' : ''}`;
    item.dataset.pid = p.persona_id;

    const initial = getAvatarInitial(p.name);
    const gradient = getAvatarGradient(p.persona_id);

    item.innerHTML = `
      <div class="persona-avatar-wrap" style="background: ${gradient}">
        ${initial}
      </div>
      <div class="persona-item-info">
        <div class="persona-item-name" title="${escapeHtml(p.display_title)}">
          ${escapeHtml(p.name)}
        </div>
        <div class="persona-item-sub">
          ${p.persona_id === '__all__' ? '全库记忆总览' : p.persona_id === '__unassigned__' ? '未指定归属' : escapeHtml(p.persona_id)}
        </div>
      </div>
      <div class="persona-item-badge">
        ${p.total_count}
      </div>
    `;

    item.addEventListener('click', () => {
      if (state.selectedPersonaId === p.persona_id) return;
      state.selectedPersonaId = p.persona_id;
      state.page = 1;
      renderPersonaList();
      renderHeroCard();
      fetchMemories();
    });

    container.appendChild(item);
  });
}

function renderHeroCard() {
  const current = state.personas.find((p) => p.persona_id === state.selectedPersonaId) || {
    persona_id: state.selectedPersonaId,
    name: '当前分类',
    display_title: '当前分类',
    system_prompt: '',
    total_count: 0,
    active_count: 0,
    atom_count: 0,
    type_distribution: {},
  };

  const heroAvatar = document.getElementById('hero-avatar');
  heroAvatar.textContent = getAvatarInitial(current.name);
  heroAvatar.style.background = getAvatarGradient(current.persona_id);

  document.getElementById('hero-name').textContent = current.name;
  
  const pidBadge = document.getElementById('hero-pid-badge');
  pidBadge.textContent = current.persona_id;
  pidBadge.onclick = () => {
    navigator.clipboard.writeText(current.persona_id);
    showToast(`已复制 Persona ID: ${current.persona_id}`, 'success');
  };

  const tag = document.getElementById('hero-configured-tag');
  if (current.persona_id === '__all__') {
    tag.textContent = '全局视图';
    tag.className = 'tag tag-configured';
  } else if (current.persona_id === '__unassigned__') {
    tag.textContent = '通用/未分配';
    tag.className = 'tag tag-history';
  } else if (current.is_configured) {
    tag.textContent = '系统已配置';
    tag.className = 'tag tag-configured';
  } else {
    tag.textContent = '历史数据人格';
    tag.className = 'tag tag-history';
  }

  document.getElementById('hero-prompt').textContent =
    current.system_prompt || (current.persona_id === '__all__' ? '查看当前数据库中跨所有角色的人格记忆全貌' : '暂无系统设定描述');

  document.getElementById('stat-total').textContent = current.total_count || 0;
  document.getElementById('stat-active').textContent = current.active_count || 0;
  document.getElementById('stat-atoms').textContent = current.atom_count || 0;

  // Render Type Distribution Bar
  renderDistributionBar(current.type_distribution || {});
}

const TYPE_COLORS = {
  GENERAL: '#94a3b8',
  FACT: '#0284c7',
  PREFERENCE: '#8b5cf6',
  EVENT: '#10b981',
  OPINION: '#f59e0b',
  EPISODIC: '#ef4444',
  RELATIONAL: '#f97316',
  PLANNED: '#15803d',
};

function renderDistributionBar(dist) {
  const bar = document.getElementById('dist-bar');
  const legend = document.getElementById('dist-legend');
  bar.innerHTML = '';
  legend.innerHTML = '';

  const entries = Object.entries(dist).filter(([_, cnt]) => cnt > 0);
  const total = entries.reduce((acc, [_, cnt]) => acc + cnt, 0);

  if (total === 0) {
    bar.innerHTML = '<div class="dist-seg" style="width: 100%; background: var(--bg-hover);"></div>';
    legend.innerHTML = '<span>暂无分类统计</span>';
    return;
  }

  entries.forEach(([type, count]) => {
    const pct = ((count / total) * 100).toFixed(1);
    const color = TYPE_COLORS[type] || '#64748b';

    // Segment
    const seg = document.createElement('div');
    seg.className = 'dist-seg';
    seg.style.width = `${pct}%`;
    seg.style.backgroundColor = color;
    seg.title = `${type}: ${count}条 (${pct}%)`;
    bar.appendChild(seg);

    // Legend item
    const legItem = document.createElement('div');
    legItem.className = 'legend-item';
    legItem.innerHTML = `
      <span class="legend-color" style="background: ${color}"></span>
      <span>${type} (${count})</span>
    `;
    legend.appendChild(legItem);
  });
}

function renderMemoryCards() {
  const container = document.getElementById('memory-cards-list');
  if (state.memories.length === 0) {
    container.innerHTML = `
      <div class="loading-placeholder">
        <p>📭 当前筛选条件下未找到任何记忆。</p>
        <small style="color: var(--text-subtle);">可尝试更换检索关键词、切换记忆状态或选择其他人格分类。</small>
      </div>
    `;
    return;
  }

  container.innerHTML = '';
  state.memories.forEach((m) => {
    const card = document.createElement('div');
    card.className = 'memory-card';
    card.dataset.id = m.id;

    const isSelected = state.selectedIds.has(m.id);
    const isExpanded = state.expandedMemoryIds.has(m.id);

    // Star score visualization
    const starCount = Math.min(5, Math.max(1, Math.round((m.importance || 0.5) * 5)));
    const stars = '★'.repeat(starCount) + '☆'.repeat(5 - starCount);

    // Topics list
    const topicsHtml = (m.topics || [])
      .map((t) => `<span class="topic-tag">#${escapeHtml(t)}</span>`)
      .join('');

    card.innerHTML = `
      <div class="memory-card-header">
        <div class="card-header-left">
          <input type="checkbox" class="card-select-check" data-id="${m.id}" ${isSelected ? 'checked' : ''} />
          <span class="card-id-badge">#${m.id}</span>
          <span class="persona-pill" title="所属人格设定">
            <span>👤</span>
            <span>${escapeHtml(m.persona_id || '未指定')}</span>
          </span>
          <span class="type-pill type-${escapeHtml(m.memory_type)}">${escapeHtml(m.memory_type)}</span>
          <span class="status-tag status-${escapeHtml(m.status)}">${escapeHtml(m.status)}</span>
        </div>
        <div class="card-header-right">
          <div class="importance-meter" title="重要性评分: ${m.importance}">
            <span>${stars}</span>
            <span>${(m.importance * 10).toFixed(0)}分</span>
          </div>
          <span class="memory-time" title="创建时间: ${m.create_time_display}">${m.create_time_display}</span>
        </div>
      </div>

      <div class="memory-content">${escapeHtml(m.text)}</div>

      <div class="memory-tags-row">
        ${topicsHtml}
        ${m.session_id ? `<span class="session-ref" title="会话来源: ${escapeHtml(m.session_id)}">💬 ${escapeHtml(m.session_id)}</span>` : ''}
      </div>

      <div class="memory-card-footer">
        <div class="expand-actions">
          <button class="btn-link btn-expand-atoms" data-id="${m.id}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><path d="M10.4 10.4 6.4 17.6M13.6 13.6l4-7.2"/></svg>
            <span>原子记忆 (${m.atom_count || 0})</span>
          </button>
          ${m.has_source ? `
            <button class="btn-link btn-expand-source" data-id="${m.id}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              <span>来源对话</span>
            </button>
          ` : ''}
        </div>
        <div class="edit-actions">
          <button class="btn btn-sm btn-secondary btn-edit-mem" data-id="${m.id}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            <span>编辑 / 转移</span>
          </button>
          <button class="btn btn-sm btn-ghost btn-archive-mem" data-id="${m.id}" title="归档此记忆">
            <span>归档</span>
          </button>
        </div>
      </div>

      <div class="details-expand-box" id="details-box-${m.id}" style="${isExpanded ? '' : 'display: none;'}"></div>
    `;

    // Bind card events
    const check = card.querySelector('.card-select-check');
    check.addEventListener('change', (e) => {
      if (e.target.checked) state.selectedIds.add(m.id);
      else state.selectedIds.delete(m.id);
      updateBatchBar();
    });

    const expandAtomsBtn = card.querySelector('.btn-expand-atoms');
    expandAtomsBtn.addEventListener('click', () => toggleMemoryDetail(m.id, 'atoms'));

    const expandSourceBtn = card.querySelector('.btn-expand-source');
    if (expandSourceBtn) {
      expandSourceBtn.addEventListener('click', () => toggleMemoryDetail(m.id, 'source'));
    }

    const editBtn = card.querySelector('.btn-edit-mem');
    editBtn.addEventListener('click', () => openEditModal(m));

    const archiveBtn = card.querySelector('.btn-archive-mem');
    archiveBtn.addEventListener('click', () => archiveSingleMemory(m.id));

    container.appendChild(card);
  });
}

async function toggleMemoryDetail(memoryId, defaultTab = 'atoms') {
  const box = document.getElementById(`details-box-${memoryId}`);
  if (!box) return;

  if (state.expandedMemoryIds.has(memoryId) && box.style.display !== 'none') {
    box.style.display = 'none';
    state.expandedMemoryIds.delete(memoryId);
    return;
  }

  box.style.display = 'flex';
  state.expandedMemoryIds.add(memoryId);
  box.innerHTML = '<div style="font-size:12px; color:var(--text-muted);">正在加载原子细则与上下文...</div>';

  try {
    let detail = state.expandedDetailsCache.get(memoryId);
    if (!detail) {
      detail = await callApi(`memory/${memoryId}`);
      state.expandedDetailsCache.set(memoryId, detail);
    }

    const atoms = detail.atoms || [];
    const messages = detail.source_messages || [];

    let html = '';
    if (atoms.length > 0) {
      html += `
        <div style="font-size:12px; font-weight:600; color:var(--atom-color); margin-bottom:4px;">
          🔬 拆解出的原子记忆 (Memory Atoms - ${atoms.length}条):
        </div>
        <div class="atom-list">
          ${atoms.map((a, i) => `
            <div class="atom-item">
              <span class="atom-text"><strong>#${i + 1}</strong> [${escapeHtml(a.atom_type)}] ${escapeHtml(a.content)}</span>
              <div class="atom-meta">
                <span>重要性: ${a.importance}</span>
                <span>置信度: ${a.confidence}</span>
                <span>状态: ${a.status}</span>
              </div>
            </div>
          `).join('')}
        </div>
      `;
    } else {
      html += '<div style="font-size:12px; color:var(--text-subtle);">暂无关联原子记忆数据</div>';
    }

    if (messages.length > 0) {
      html += `
        <div style="font-size:12px; font-weight:600; color:var(--primary); margin-top:8px; margin-bottom:4px;">
          💬 会话上下文对话溯源:
        </div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          ${messages.map((msg) => `
            <div style="font-size:11px; padding:4px 8px; background:var(--bg-card); border-radius:4px; border:1px solid var(--border-color);">
              <span style="font-weight:600; color:var(--primary);">${escapeHtml(msg.sender_name || msg.role)}:</span>
              <span style="color:var(--text-main); margin-left:4px;">${escapeHtml(msg.content)}</span>
            </div>
          `).join('')}
        </div>
      `;
    }

    box.innerHTML = html;
  } catch (err) {
    box.innerHTML = `<div style="font-size:12px; color:var(--danger);">加载详情失败: ${escapeHtml(err.message)}</div>`;
  }
}

function renderPagination() {
  document.getElementById('page-total-items').textContent = state.total;
  document.getElementById('page-current').textContent = state.page;
  document.getElementById('page-total-pages').textContent = state.totalPages;

  const prevBtn = document.getElementById('btn-prev-page');
  const nextBtn = document.getElementById('btn-next-page');
  prevBtn.disabled = state.page <= 1;
  nextBtn.disabled = state.page >= state.totalPages;

  const pageNums = document.getElementById('page-numbers');
  pageNums.innerHTML = '';

  const maxButtons = 5;
  let startPage = Math.max(1, state.page - 2);
  let endPage = Math.min(state.totalPages, startPage + maxButtons - 1);
  if (endPage - startPage < maxButtons - 1) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  for (let i = startPage; i <= endPage; i++) {
    const btn = document.createElement('button');
    btn.className = `page-num-btn ${i === state.page ? 'active' : ''}`;
    btn.textContent = i;
    btn.addEventListener('click', () => {
      if (state.page !== i) {
        state.page = i;
        fetchMemories();
      }
    });
    pageNums.appendChild(btn);
  }
}

function updateBatchBar() {
  const bar = document.getElementById('batch-bar');
  const countSpan = document.getElementById('batch-count');
  const selectAll = document.getElementById('checkbox-select-all');

  const count = state.selectedIds.size;
  countSpan.textContent = count;
  bar.style.display = count > 0 ? 'flex' : 'none';

  selectAll.checked = count > 0 && count === state.memories.length;
}

function updateBatchPersonaSelect() {
  const select = document.getElementById('batch-target-persona');
  const editSelect = document.getElementById('edit-persona');
  select.innerHTML = '';
  editSelect.innerHTML = '';

  const validPersonas = state.personas.filter((p) => p.persona_id !== '__all__');

  validPersonas.forEach((p) => {
    const opt = document.createElement('option');
    opt.value = p.persona_id === '__unassigned__' ? '' : p.persona_id;
    opt.textContent = `${p.name} (${opt.value || '未归属'})`;
    select.appendChild(opt.cloneNode(true));
    editSelect.appendChild(opt);
  });
}

// 7. Modals and Actions
function openEditModal(mem) {
  const modal = document.getElementById('edit-modal');
  document.getElementById('edit-id').value = mem.id;
  document.getElementById('edit-text').value = mem.text || '';
  document.getElementById('edit-type').value = mem.memory_type || 'GENERAL';
  document.getElementById('edit-status').value = mem.status || 'active';
  
  const imp = mem.importance || 0.5;
  document.getElementById('edit-importance').value = imp;
  document.getElementById('edit-importance-val').textContent = imp.toFixed(2);

  document.getElementById('edit-persona').value = mem.persona_id || '';
  modal.style.display = 'flex';
}

function closeEditModal() {
  document.getElementById('edit-modal').style.display = 'none';
}

async function saveEditMemory() {
  const id = document.getElementById('edit-id').value;
  const text = document.getElementById('edit-text').value.trim();
  const persona_id = document.getElementById('edit-persona').value;
  const memory_type = document.getElementById('edit-type').value;
  const status = document.getElementById('edit-status').value;
  const importance = parseFloat(document.getElementById('edit-importance').value);

  if (!text) {
    showToast('记忆内容不能为空', 'error');
    return;
  }

  try {
    await callApi('memory/update', {
      method: 'POST',
      body: { id, text, persona_id, memory_type, status, importance },
    });
    showToast('记忆保存成功！', 'success');
    closeEditModal();
    state.expandedDetailsCache.delete(Number(id));
    await fetchPersonas();
    await fetchMemories();
  } catch (err) {
    showToast(`保存失败: ${err.message}`, 'error');
  }
}

async function archiveSingleMemory(id) {
  if (!confirm(`确定将记忆 #${id} 移入归档吗？`)) return;
  try {
    await callApi('memory/delete', {
      method: 'POST',
      body: { id, soft: true },
    });
    showToast(`记忆 #${id} 已归档`, 'success');
    await fetchPersonas();
    await fetchMemories();
  } catch (err) {
    showToast(`归档失败: ${err.message}`, 'error');
  }
}

async function executeBatchTransfer() {
  const targetPid = document.getElementById('batch-target-persona').value;
  const ids = Array.from(state.selectedIds);
  if (ids.length === 0) return;

  const targetName = targetPid || '未指定人格';
  if (!confirm(`确定将选中的 ${ids.length} 条记忆转移至人格设定 [${targetName}] 吗？`)) return;

  try {
    const res = await callApi('memory/batch_persona', {
      method: 'POST',
      body: { ids, target_persona_id: targetPid },
    });
    showToast(`成功将 ${res.updated_count} 条记忆转移至 [${targetName}]！`, 'success');
    state.selectedIds.clear();
    updateBatchBar();
    await fetchPersonas();
    await fetchMemories();
  } catch (err) {
    showToast(`批量转移失败: ${err.message}`, 'error');
  }
}

async function executeExport() {
  const currentPid = state.selectedPersonaId;
  const fmt = 'json'; // support json / csv
  try {
    const res = await callApi('export', {
      params: { persona_id: currentPid, format: fmt },
    });
    const blob = new Blob([res.content], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `livingmemory_persona_${currentPid}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('导出文件已生成并开始下载', 'success');
  } catch (err) {
    showToast(`导出失败: ${err.message}`, 'error');
  }
}

function renderDbModal() {
  const status = state.dbStatus || {};
  document.getElementById('current-db-path').textContent = status.db_path || '无可用数据库';
  document.getElementById('current-db-status').textContent = status.connected ? '正常连接 (WAL)' : '未连接';
  document.getElementById('current-db-docs').textContent = status.documents_count || 0;
  document.getElementById('current-db-atoms').textContent = status.atoms_count || 0;
  document.getElementById('current-db-personas').textContent = status.personas_count || 0;

  const list = document.getElementById('candidate-list');
  list.innerHTML = '';
  const candidates = status.candidates || [];
  if (candidates.length === 0) {
    list.innerHTML = '<div style="font-size:12px;color:var(--text-muted);">未自动扫描到其他数据库</div>';
    return;
  }

  candidates.forEach((c) => {
    const isCurrent = c.path === status.db_path;
    const item = document.createElement('div');
    item.className = 'candidate-item';
    item.innerHTML = `
      <div>
        <div style="font-weight:600; color:var(--text-main); font-family:monospace;">${escapeHtml(c.path)}</div>
        <div style="font-size:11px; color:var(--text-muted);">大小: ${c.size_display} | 修改时间: ${c.mtime_display}</div>
      </div>
      <button class="btn btn-sm ${isCurrent ? 'btn-secondary' : 'btn-primary'}" ${isCurrent ? 'disabled' : ''}>
        ${isCurrent ? '当前正在使用' : '切换至此库'}
      </button>
    `;
    if (!isCurrent) {
      item.querySelector('button').addEventListener('click', () => switchDatabase(c.path));
    }
    list.appendChild(item);
  });
}

async function switchDatabase(path) {
  try {
    await callApi('set_active_db', {
      method: 'POST',
      body: { path },
    });
    showToast('已切换至目标数据库！', 'success');
    document.getElementById('db-modal').style.display = 'none';
    await checkStatus();
    await fetchPersonas();
    await fetchMemories();
  } catch (err) {
    showToast(`切换失败: ${err.message}`, 'error');
  }
}

// 8. Event Listeners Setup
function setupEventListeners() {
  // DB status click
  document.getElementById('btn-db-status').addEventListener('click', () => {
    document.getElementById('db-modal').style.display = 'flex';
  });
  document.getElementById('btn-close-db').addEventListener('click', () => {
    document.getElementById('db-modal').style.display = 'none';
  });
  document.getElementById('btn-cancel-db').addEventListener('click', () => {
    document.getElementById('db-modal').style.display = 'none';
  });
  document.getElementById('btn-switch-db').addEventListener('click', () => {
    const p = document.getElementById('custom-db-input').value.trim();
    if (p) switchDatabase(p);
  });

  // Global Refresh
  document.getElementById('btn-refresh').addEventListener('click', async () => {
    showToast('正在刷新全部数据...', 'info');
    await checkStatus();
    await fetchPersonas();
    await fetchMemories();
  });

  // Export
  document.getElementById('btn-export-persona').addEventListener('click', executeExport);

  // Persona Sidebar Filter Input
  document.getElementById('persona-filter-input').addEventListener('input', () => {
    renderPersonaList();
  });

  // Memory Search Input (Debounced)
  const searchInput = document.getElementById('memory-search-input');
  const clearSearchBtn = document.getElementById('btn-clear-search');
  searchInput.addEventListener('input', (e) => {
    clearTimeout(state.searchDebounceTimer);
    const val = e.target.value;
    clearSearchBtn.style.display = val ? 'block' : 'none';
    state.searchDebounceTimer = setTimeout(() => {
      state.filters.keyword = val;
      state.page = 1;
      fetchMemories();
    }, 300);
  });

  clearSearchBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearSearchBtn.style.display = 'none';
    state.filters.keyword = '';
    state.page = 1;
    fetchMemories();
  });

  // Filters select
  document.getElementById('select-type').addEventListener('change', (e) => {
    state.filters.type = e.target.value;
    state.page = 1;
    fetchMemories();
  });
  document.getElementById('select-status').addEventListener('change', (e) => {
    state.filters.status = e.target.value;
    state.page = 1;
    fetchMemories();
  });
  document.getElementById('select-sort').addEventListener('change', (e) => {
    state.filters.sort = e.target.value;
    state.page = 1;
    fetchMemories();
  });

  // Reset Filters
  document.getElementById('btn-reset-filters').addEventListener('click', () => {
    searchInput.value = '';
    clearSearchBtn.style.display = 'none';
    document.getElementById('select-type').value = 'all';
    document.getElementById('select-status').value = 'active';
    document.getElementById('select-sort').value = 'created_desc';
    state.filters.keyword = '';
    state.filters.type = 'all';
    state.filters.status = 'active';
    state.filters.sort = 'created_desc';
    state.page = 1;
    fetchMemories();
  });

  // Pagination
  document.getElementById('btn-prev-page').addEventListener('click', () => {
    if (state.page > 1) {
      state.page--;
      fetchMemories();
    }
  });
  document.getElementById('btn-next-page').addEventListener('click', () => {
    if (state.page < state.totalPages) {
      state.page++;
      fetchMemories();
    }
  });

  // Batch Select All
  document.getElementById('checkbox-select-all').addEventListener('change', (e) => {
    if (e.target.checked) {
      state.memories.forEach((m) => state.selectedIds.add(m.id));
    } else {
      state.selectedIds.clear();
    }
    renderMemoryCards();
    updateBatchBar();
  });
  document.getElementById('btn-cancel-batch').addEventListener('click', () => {
    state.selectedIds.clear();
    renderMemoryCards();
    updateBatchBar();
  });
  document.getElementById('btn-batch-transfer').addEventListener('click', executeBatchTransfer);

  // Edit Modal
  document.getElementById('btn-close-edit').addEventListener('click', closeEditModal);
  document.getElementById('btn-cancel-edit').addEventListener('click', closeEditModal);
  document.getElementById('btn-save-edit').addEventListener('click', saveEditMemory);
  document.getElementById('edit-importance').addEventListener('input', (e) => {
    document.getElementById('edit-importance-val').textContent = parseFloat(e.target.value).toFixed(2);
  });
}

// 9. Startup Sequence
async function startApp() {
  setupEventListeners();

  if (bridge && typeof bridge.ready === 'function') {
    try {
      await bridge.ready();
    } catch (e) {
      console.warn('Bridge ready timeout or warning:', e);
    }
  }

  await checkStatus();
  await fetchPersonas();
  await fetchMemories();
}

startApp();

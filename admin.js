// ===================== 智能技术能力评估平台 · 管理后台 =====================
const TOKEN_KEY = 'admin_token';
const API = '';
let specialtiesMap = {};   // key -> label
let examsCache = [];

function $(id) { return document.getElementById(id); }

function token() { return localStorage.getItem(TOKEN_KEY) || ''; }

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (opts.token !== false && token()) headers['X-Admin-Token'] = token();
  const resp = await fetch(API + path, { ...opts, headers });
  const data = await resp.json().catch(() => ({}));
  if (resp.status === 403) {
    doLogout();
    throw new Error('登录已失效，请重新登录');
  }
  if (!resp.ok) throw new Error(data.detail || ('请求失败 ' + resp.status));
  return data;
}

function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2200);
}

// ---------------- 登录 ----------------
async function doLogin() {
  const msg = $('login-msg');
  msg.textContent = '';
  try {
    const data = await api('/api/admin/login', {
      method: 'POST',
      token: false,
      body: JSON.stringify({ username: $('login-user').value.trim(), password: $('login-pass').value }),
    });
    localStorage.setItem(TOKEN_KEY, data.token);
    enterApp();
  } catch (e) {
    msg.textContent = e.message;
  }
}

function doLogout() {
  localStorage.removeItem(TOKEN_KEY);
  $('app-view').classList.add('hidden');
  $('login-view').classList.remove('hidden');
}

function enterApp() {
  $('login-view').classList.add('hidden');
  $('app-view').classList.remove('hidden');
  init();
}

// ---------------- 初始化 ----------------
async function init() {
  await Promise.all([loadSpecialties(), loadDashboard(), loadExams(), initBankCenter()]);
}

// ---------------- 题库中心 ----------------
let bankModules = [];

async function initBankCenter() {
  await Promise.all([refreshBankHealth(), loadBankCatalog()]);
}

async function loadBankCatalog() {
  try {
    const data = await api('/api/admin/bank/catalog');
    bankModules = Object.keys(data.modules || {});
    const sel = $('bx-module');
    sel.innerHTML = '';
    for (const m of bankModules) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      sel.appendChild(opt);
    }
  } catch (e) { /* 提示已在 api 层处理 */ }
}

async function refreshBankHealth() {
  const box = $('bank-health');
  box.innerHTML = '<div class="empty">加载中...</div>';
  try {
    const data = await api('/api/admin/bank/health');
    const total = data.total_questions || 0;
    let html = `<div class="kv"><span>题库总量：<b style="color:#a5b4fc">${total}</b></span></div>`;
    for (const m of data.modules || []) {
      const hasRatios = !!m.has_ratios;
      html += `<div class="result-box"><h3>${esc(m.module)} · ${m.total} 题` +
        (hasRatios ? '' : ' <span class="small">（模块题量少，按子方向随机抽题即可）</span>') + '</h3>';
      const cats = Object.entries(m.categories || {});
      const chips = cats.map(([c, n]) =>
        `<span class="tag ${(m.warnings || []).includes(c) ? 'warn-badge' : ''}">${esc(c)} ${n}</span>`).join(' ');
      html += `<div>${chips || '<span class="small">无</span>'}</div>`;
      const diff = Object.entries(m.difficulty || {}).map(([d, n]) =>
        `<span class="q-meta diff-${esc(d)}">${esc(d)} ${n}</span>`).join(' ');
      if (diff) html += `<div style="margin-top:6px;">难度：${diff}</div>`;
      // 仅对配置了 assessment_ratios 的模块做“覆盖均衡”判断；未配置的模块随机抽题即合理
      if (hasRatios) {
        if (m.suggestions && m.suggestions.length) {
          html += `<div style="margin-top:6px;">` + m.suggestions.map(s =>
            `<span class="warn-badge" style="margin-right:6px;">⚠ ${esc(s)}</span>`).join('') + '</div>';
        } else {
          html += `<div style="margin-top:6px;"><span class="ok-badge">✓ 覆盖均衡</span></div>`;
        }
      }
      html += '</div>';
    }
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = `<div class="empty">健康分析加载失败：${esc(e.message)}</div>`;
  }
}

function typeLabel(t) {
  return ({ single_choice: '单选', multi_choice: '多选', true_false: '判断', subjective: '主观' })[t] || t;
}

// ---------------- 出题模式切换 ----------------
let bxMode = 'brainstorm';  // brainstorm=快速脑暴 / url=URL 定向

function switchMode(mode) {
  bxMode = mode;
  $('mode-chip-brainstorm').classList.toggle('active', mode === 'brainstorm');
  $('mode-chip-url').classList.toggle('active', mode === 'url');
  $('mode-brainstorm-tip').classList.toggle('hidden', mode !== 'brainstorm');
  $('mode-url-tip').classList.toggle('hidden', mode !== 'url');
  $('bx-url-field').classList.toggle('hidden', mode !== 'url');
}

function renderQuestions(questions) {
  const typeName = (d) => `[${typeLabel(d.type)}]`;
  return (questions || []).map(q =>
    `<div class="question-row">
      <div class="q-txt">${esc(q.question)}</div>
      <div class="q-meta">
        ${typeName(q)} <span class="tag">${esc(q.assessment_category)}</span>
        ${(q.skill_dimension || []).map(s => `<span class="tag">${esc(s)}</span>`).join('')}
        <span class="diff-${esc(q.difficulty)}">难度：${esc(q.difficulty)}</span>
        <span class="mono">id ${q.id != null ? q.id : '待分配'}</span>
      </div>
    </div>`).join('') || '<div class="small">（无）</div>';
}

async function runBankExpand() {
  const btn = $('bx-btn');
  const status = $('bx-status');
  const box = $('bx-result');
  const module = $('bx-module').value;
  const topics = $('bx-topics').value.split('\n').map(s => s.trim()).filter(Boolean);
  const urls = $('bx-urls').value.split('\n').map(s => s.trim()).filter(Boolean);
  const instruction = $('bx-instruction').value.trim();
  const dryRun = $('bx-dryrun').checked;
  const mode = bxMode;
  if (!module) { toast('请选择专业方向'); return; }
  if (mode === 'url' && !urls.length) { toast('URL 模式需要至少填一个参考 URL'); return; }
  if (mode === 'brainstorm' && !topics.length) { toast('脑暴模式需要至少填一个话题'); return; }
  btn.disabled = true;
  btn.textContent = '任务已提交…';
  status.textContent = '';
  box.innerHTML = '';
  try {
    const started = await api('/api/admin/bank/expand', {
      method: 'POST',
      body: JSON.stringify({ module, topics, urls, instruction, mode, dry_run: dryRun }),
    });
    const jobId = started.job_id;
    // 轮询进度
    const poll = async () => {
      const job = await api('/api/admin/bank/expand/' + jobId);
      if (job.status === 'running' || job.status === 'pending') {
        status.textContent = 'AI 处理中：' + (job.stage || '') + (mode === 'url' ? '（约 3~6 分钟，可稍等）' : '（约 1~3 分钟，可稍等）');
        setTimeout(poll, 5000);
        return;
      }
      btn.disabled = false;
      btn.textContent = '开始 AI 扩充';
      status.textContent = '';
      if (job.status === 'error') {
        box.innerHTML = `<div class="result-box"><div class="q-txt" style="color:#ff8a8a;">${esc(job.error || '任务失败')}</div></div>`;
        toast(job.error || '任务失败');
        return;
      }
      renderExpandResult(job.result, dryRun);
      if (!dryRun && job.result && job.result.inserted_count > 0) {
        toast(`已入库 ${job.result.inserted_count} 道题`);
        refreshBankHealth();
      } else {
        toast(dryRun ? '预览完成（未入库）' : '未生成有效题目');
      }
    };
    poll();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = '开始 AI 扩充';
    box.innerHTML = `<div class="result-box"><div class="q-txt" style="color:#ff8a8a;">${esc(e.message)}</div></div>`;
    toast(e.message);
  }
}

function renderExpandResult(data, dryRun) {
  const box = $('bx-result');
  const kps = data.knowledge_points || [];
  let html = `<div class="result-box">
    <h3>${dryRun ? '【预览】' : '✓ 已入库'} · ${esc(data.module || '')} · AI 扩充结果</h3>
    <div class="kv">
      <span>候选：${data.collected_count} 条</span>
      <span>筛选：${esc(data.screen || '')}</span>
      <span>知识点：${kps.length} 个</span>
      <span>${dryRun ? '预览题' : '入库题'}：${data.inserted_count} 道</span>
      ${data.new_ids && data.new_ids.length ? `<span class="mono">新ID：${data.new_ids.join(',')}</span>` : ''}
    </div>`;
  if (data.sources && data.sources.length) {
    html += '<div class="q-meta">来源：' + data.sources.map(s =>
      s.error ? `${esc(s.url)}（抓取失败：${esc(s.error)}）` : `${esc(s.url)}（${s.chars}字）`).join('<br>') + '</div>';
  }
  if (kps.length) {
    html += `<div style="margin-top:8px;"><b class="small">知识点 → 维度映射：</b> ` +
      kps.map(k => `<span class="tag">${esc(k.name)} → ${esc(k.assessment_category)} ×${k.question_count}</span>`).join('') + '</div>';
  }
  html += '</div>';
  if (data.questions && data.questions.length) {
    html += `<div class="result-box"><h3>生成题目预览（${data.questions.length} 道）</h3>${renderQuestions(data.questions)}</div>`;
  }
  if (data.errors && data.errors.length) {
    html += `<div class="result-box"><h3>被过滤/校验未过（${data.errors.length} 条）</h3>` +
      data.errors.map(e => `<div class="q-meta">${esc(e)}</div>`).join('') + '</div>';
  }
  box.innerHTML = html;
}

async function loadSpecialties() {
  try {
    const data = await api('/api/specialties', { token: false });
    specialtiesMap = data.specialties || {};
  } catch (e) { specialtiesMap = {}; }
  renderSpecChips();
}

const selectedSpecs = new Set();
function renderSpecChips() {
  const box = $('f-specs');
  box.innerHTML = '';
  for (const [key, sp] of Object.entries(specialtiesMap)) {
    const chip = document.createElement('div');
    chip.className = 'spec-chip' + (selectedSpecs.has(key) ? ' active' : '');
    chip.textContent = sp.label || key;
    chip.onclick = () => {
      if (selectedSpecs.has(key)) selectedSpecs.delete(key);
      else if (selectedSpecs.size < 3) selectedSpecs.add(key);
      chip.classList.toggle('active', selectedSpecs.has(key));
    };
    box.appendChild(chip);
  }
}

async function loadDashboard() {
  try {
    const d = await api('/api/admin/dashboard');
    $('st-exams').textContent = d.total_exams;
    $('st-candidates').textContent = d.total_candidates;
    $('st-submitted').textContent = d.submitted_candidates;
    $('st-avg').textContent = d.avg_score;
  } catch (e) { /* 已提示 */ }
}

// ---------------- 创建考试 ----------------
async function createExam() {
  const title = $('f-title').value.trim();
  if (!title) return toast('请填写考试名称');
  if (selectedSpecs.size === 0) return toast('请至少选择一个专业方向');
  const duration = parseInt($('f-duration').value, 10) || 30;
  const payload = {
    title,
    specialties: [...selectedSpecs],
    duration,
    enable_subjective: $('f-subj').checked,
    enable_ai: $('f-ai').checked,
  };
  try {
    const exam = await api('/api/admin/exams', { method: 'POST', body: JSON.stringify(payload) });
    toast('考试创建成功，邀请码 ' + exam.invite_code);
    const link = location.origin + '/exam/join?code=' + encodeURIComponent(exam.invite_code);
    $('new-link').value = link;
    $('new-code').textContent = exam.invite_code;
    $('new-link-box').classList.remove('hidden');
    // 清空表单方向选择
    selectedSpecs.clear();
    renderSpecChips();
    await loadDashboard();
    await loadExams();
  } catch (e) {
    toast(e.message);
  }
}

function copyLink(id) {
  const input = $(id);
  input.select();
  navigator.clipboard.writeText(input.value)
    .then(() => toast('链接已复制'))
    .catch(() => toast('请手动复制'));
}

// ---------------- 考试列表 ----------------
async function loadExams() {
  const data = await api('/api/admin/exams');
  examsCache = data.exams || [];
  renderExams();
}

function specLabel(keys) {
  return (keys || []).map(k => (specialtiesMap[k] ? specialtiesMap[k].label : k)).join(' / ') || '—';
}

function fmtTime(t) {
  if (!t) return '—';
  return String(t).replace('T', ' ').slice(0, 16);
}

function renderExams() {
  const box = $('exam-table');
  if (!examsCache.length) {
    box.innerHTML = '<div class="empty">还没有考试，先在上方创建一场吧</div>';
    return;
  }
  let html = `<table><thead><tr>
    <th>名称</th><th>邀请码</th><th>专业方向</th><th>候选人</th><th>创建时间</th><th>操作</th>
  </tr></thead><tbody>`;
  for (const e of examsCache) {
    const statusBadge = e.status === 'active'
      ? '<span class="badge green">进行中</span>'
      : '<span class="badge gray">已关闭</span>';
    html += `<tr>
      <td><strong>${esc(e.title)}</strong> <span style="display:block;font-size:11px;color:#64748b;">${statusBadge}${e.enable_ai ? '' : ' · 无AI'}</span></td>
      <td><b style="color:#a5b4fc;letter-spacing:1px;">${esc(e.invite_code || '—')}</b></td>
      <td>${esc(specLabel(e.specialties))}</td>
      <td>${e.candidate_count}（提交 ${e.submitted_count}）</td>
      <td>${fmtTime(e.created_at)}</td>
      <td>
        <button class="act-btn" onclick="viewCandidates('${e.id}')">候选人</button>
        <button class="act-btn" onclick="copyExamLink('${e.id}')">复制链接</button>
        <button class="act-btn" style="border-color:rgba(255,107,107,0.5);color:#ff8a8a;" onclick="deleteExam('${e.id}')">删除</button>
      </td>
    </tr>`;
  }
  html += '</tbody></table>';
  box.innerHTML = html;
}

async function deleteExam(id) {
  const exam = examsCache.find(x => x.id === id);
  if (!exam) return;
  if (!confirm(`确定删除考试「${exam.title}」吗？该考试的全部候选人记录将一并删除，不可恢复。`)) return;
  try {
    await api('/api/admin/exams/' + id, { method: 'DELETE' });
    toast('考试已删除');
    $('cand-panel').classList.add('hidden');
    await loadDashboard();
    await loadExams();
  } catch (e) {
    toast(e.message);
  }
}

async function copyExamLink(id) {
  const e = examsCache.find(x => x.id === id);
  if (!e) return;
  const link = location.origin + '/exam/join?code=' + encodeURIComponent(e.invite_code || '');
  await navigator.clipboard.writeText(link).catch(() => {});
  toast('邀请链接已复制（候选人在 /exam/join 输入邀请码即可）');
}

// ---------------- 候选人 ----------------
async function viewCandidates(examId) {
  const exam = examsCache.find(x => x.id === examId);
  if (!exam) return;
  const data = await api('/api/admin/exams/' + examId);
  $('cand-title').textContent = '候选人 · ' + exam.title;
  $('cand-panel').classList.remove('hidden');
  const box = $('cand-table');
  const cands = data.candidates || [];
  if (!cands.length) {
    box.innerHTML = '<div class="empty">该考试还没有候选人参加</div>';
    return;
  }
  let html = `<table><thead><tr>
    <th>姓名</th><th>专业方向</th><th>成绩</th><th>状态</th><th>开始时间</th><th>操作</th>
  </tr></thead><tbody>`;
  const statusMap = {
    submitted: ['<span class="badge green">已提交</span>'],
    started: ['<span class="badge orange">答题中</span>'],
    timeout: ['<span class="badge gray">超时未交</span>'],
  };
  for (const c of cands) {
    const score = c.final_score == null ? '—' : c.final_score;
    const sb = (statusMap[c.status] || ['<span class="badge gray">' + esc(c.status) + '</span>'])[0];
    const canView = c.status === 'submitted';
    html += `<tr>
      <td>${esc(c.candidate_name || '未署名')}</td>
      <td>${esc(c.specialty || '—')}</td>
      <td>${score}</td>
      <td>${sb}</td>
      <td>${fmtTime(c.started_at)}</td>
      <td>${canView
        ? `<button class="act-btn" onclick="openReport('${c.id}')">查看报告</button>
           <button class="act-btn" style="border-color:rgba(165,180,252,0.6);color:#a5b4fc;" onclick="exportPdf('${c.id}')">导出PDF</button>`
        : '<span style="color:#64748b">—</span>'}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  box.innerHTML = html;
}

function openReport(recordId) {
  window.open(location.origin + '/#r/' + recordId, '_blank');
}

// ---------------- 导出 PDF 报告 ----------------
async function exportPdf(recordId) {
  try {
    const resp = await fetch(API + '/api/report/' + recordId + '/pdf', {
      headers: { 'X-Admin-Token': token() },
    });
    if (resp.status === 403) {
      doLogout();
      toast('登录已失效，请重新登录');
      return;
    }
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || ('导出失败 ' + resp.status));
    }
    const blob = await resp.blob();
    // 优先取服务端 Content-Disposition 里的文件名
    let filename = '评估报告.pdf';
    const cd = resp.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="?([^";]+)"?/i);
    if (m && m[1]) {
      try { filename = decodeURIComponent(m[1]); }
      catch (e) { filename = m[1]; }
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast('PDF 已开始下载');
  } catch (e) {
    toast(e.message);
  }
}

// ---------------- 工具 ----------------
function esc(s) {
  const div = document.createElement('div');
  div.textContent = s == null ? '' : String(s);
  return div.innerHTML;
}

// 启动：已有 token 直接进后台
if (token()) enterApp();

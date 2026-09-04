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
  await Promise.all([loadSpecialties(), loadDashboard(), loadExams()]);
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
        ? `<button class="act-btn" onclick="openReport('${c.id}')">查看报告</button>`
        : '<span style="color:#64748b">—</span>'}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  box.innerHTML = html;
}

function openReport(recordId) {
  window.open(location.origin + '/#r/' + recordId, '_blank');
}

// ---------------- 工具 ----------------
function esc(s) {
  const div = document.createElement('div');
  div.textContent = s == null ? '' : String(s);
  return div.innerHTML;
}

// 启动：已有 token 直接进后台
if (token()) enterApp();

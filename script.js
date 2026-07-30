// ===================== 全局状态 =====================
const API = '';
let examData = null;
let questions = [];
let userAnswers = {};
let currentIndex = 0;
let timerSeconds = 0;
let timerInterval = null;
let saveInterval = null;
let selectedSpecialties = [];
let specialties = {};
let examRecordId = null;

const pages = ['start', 'specialty', 'exam', 'result', 'history'];

function setRoute(page, replace = false) {
  if (!pages.includes(page)) page = 'start';
  const url = page === 'start' ? location.pathname : location.pathname + '#' + page;
  const state = { page };
  if (replace) history.replaceState(state, '', url);
  else history.pushState(state, '', url);
}

function getRoutePage() {
  const statePage = history.state && history.state.page;
  if (pages.includes(statePage)) return statePage;
  const hashPage = location.hash.replace('#', '');
  return pages.includes(hashPage) ? hashPage : 'start';
}

function showPage(page) {
  document.getElementById('start-page').classList.toggle('hidden', page !== 'start');
  document.getElementById('specialty-page').classList.toggle('hidden', page !== 'specialty');
  document.getElementById('exam-page').classList.toggle('hidden', page !== 'exam');
  document.getElementById('result-page').classList.toggle('hidden', page !== 'result');
  document.getElementById('history-page').classList.toggle('hidden', page !== 'history');
}

function handleRoute(page) {
  if (page !== 'exam' && timerInterval) clearInterval(timerInterval);

  // exam / result 依赖内存数据，刷新后数据丢失则回首页
  if (page === 'exam' && (!questions || questions.length === 0)) {
    page = 'start';
    setRoute('start', true);
  }
  if (page === 'result' && !document.getElementById('result-content').textContent.trim()) {
    page = 'start';
    setRoute('start', true);
  }

  if (page === 'specialty') {
    renderSpecialtySelect();
  } else if (page === 'history') {
    loadHistory();
  }
  showPage(page);
}

window.addEventListener('popstate', () => {
  handleRoute(getRoutePage());
});

// ===================== 初始化 =====================
window.addEventListener('DOMContentLoaded', async () => {
  try {
    const resp = await fetch(API + '/api/specialties');
    const data = await resp.json();
    specialties = data.specialties;
    if (getRoutePage() === 'specialty') renderSpecialtySelect();
  } catch (e) {
    console.error('加载专业列表失败', e);
  }
});

// ===================== 专业选择（多选 1~3 个） =====================
const initialPage = getRoutePage();
setRoute(initialPage, true);
handleRoute(initialPage);

function showSpecialtySelect() {
  setRoute('specialty');
  renderSpecialtySelect();
  showPage('specialty');
}

function renderSpecialtySelect() {
  const grid = document.getElementById('specialty-grid');
  grid.innerHTML = '';
  selectedSpecialties = [];
  updateConfirmButton();

  for (const [key, sp] of Object.entries(specialties)) {
    const card = document.createElement('div');
    card.className = 'specialty-card';
    card.dataset.key = key;
    card.innerHTML = `
      <div class="sp-icon">${sp.icon || ''}</div>
      <div class="sp-name">${sp.label}</div>
      <div class="sp-desc">${sp.desc}</div>
    `;
    card.onclick = () => {
      const idx = selectedSpecialties.indexOf(key);
      if (idx >= 0) {
        selectedSpecialties.splice(idx, 1);
        card.classList.remove('selected');
      } else if (selectedSpecialties.length < 3) {
        selectedSpecialties.push(key);
        card.classList.add('selected');
      }
      updateConfirmButton();
    };
    grid.appendChild(card);
  }
}

function updateConfirmButton() {
  const btn = document.getElementById('btn-confirm');
  const n = selectedSpecialties.length;
  btn.disabled = (n === 0);
  btn.textContent = n === 0 ? '请至少勾选 1 个方向' :
    `确认并开始答题（已选 ${n}/3 个方向）`;
}

function confirmSpecialty() {
  if (selectedSpecialties.length === 0) return;
  startExam(selectedSpecialties.join(','));
}

// ===================== 开始考试 =====================
async function startExam(specialty) {
  setRoute('exam');
  showPage('exam');

  // 显示加载
  document.getElementById('q-card').innerHTML =
    '<div style="text-align:center;padding:60px;color:#aab;">正在生成试卷...</div>';

  const url = specialty
    ? API + '/api/exam/start?specialty=' + encodeURIComponent(specialty)
    : API + '/api/exam/start';

  const resp = await fetch(url);
  examData = await resp.json();
  examRecordId = examData.record_id || null;
  questions = examData.questions;
  userAnswers = {};
  currentIndex = 0;
  selectedSpecialties = examData.specialty ? examData.specialty.split(',') : [];

  // 专业标签
  const tag = document.getElementById('specialty-tag');
  const labels = selectedSpecialties
    .map(s => specialties[s] ? specialties[s].label : s)
    .join(' + ');
  tag.textContent = '方向: ' + (labels || '通用基础');

  // 初始化答案
  questions.forEach(q => {
    if (q.type === 'multi_choice') userAnswers[q.id] = [];
    else userAnswers[q.id] = '';
  });

  startTimer(examData.time_limit_minutes * 60);
  renderQuestion();
}

// ===================== 计时器 =====================
function startTimer(totalSec) {
  if (timerInterval) clearInterval(timerInterval);
  timerSeconds = totalSec;
  updateTimerDisplay();
  timerInterval = setInterval(() => {
    timerSeconds--;
    updateTimerDisplay();
    if (timerSeconds <= 0) {
      clearInterval(timerInterval);
      alert('考试时间到，系统将自动提交。');
      submitExam();
    }
  }, 1000);

  // 每 30 秒自动保存
  if (saveInterval) clearInterval(saveInterval);
  saveInterval = setInterval(() => autoSave(), 30000);
}

function updateTimerDisplay() {
  const m = Math.floor(timerSeconds / 60);
  const s = timerSeconds % 60;
  const el = document.getElementById('timer-display');
  el.textContent = `剩余时间: ${m}:${String(s).padStart(2, '0')}`;
  el.className = 'timer' + (timerSeconds < 300 ? ' warning' : '');
}

// ===================== 渲染题目 =====================
function renderQuestion() {
  const q = questions[currentIndex];
  const total = questions.length;
  document.getElementById('q-progress').textContent = `${currentIndex + 1} / ${total}`;

  document.getElementById('btn-prev').disabled = (currentIndex === 0);
  const btnNext = document.getElementById('btn-next');
  btnNext.textContent = (currentIndex === total - 1) ? '提交答卷' : '下一题';

  const diffMap = { '简单': 'easy', '中等': 'mid', '困难': 'hard' };
  const diffCls = diffMap[q.difficulty] || 'mid';
  const typeNames = {
    'single_choice': '单选题', 'multi_choice': '多选题',
    'true_false': '判断题', 'subjective': '主观题'
  };

  let html = `
    <div class="q-meta">
      <span class="badge badge-module">${q.module || q.category}</span>
      <span class="badge badge-cat">${q.category}</span>
      <span class="badge badge-diff-${diffCls}">${q.difficulty}</span>
      <span class="badge badge-weight">权重 ×${q.weight}</span>
      <span class="badge badge-type">${typeNames[q.type] || q.type}</span>
    </div>
    <div class="q-text">${escapeHtml(q.question)}</div>
  `;

  const curAns = userAnswers[q.id];

  if (q.type === 'single_choice') {
    html += '<ul class="option-list">';
    q.options.forEach((opt, i) => {
      const sel = curAns === opt ? ' selected' : '';
      html += `<li class="option-item${sel}" onclick="selectOption('${escapeAttr(opt)}')">
        <div class="radio"></div><span>${String.fromCharCode(65+i)}. ${escapeHtml(opt)}</span></li>`;
    });
    html += '</ul>';
  } else if (q.type === 'multi_choice') {
    html += '<ul class="option-list">';
    q.options.forEach((opt, i) => {
      const arr = Array.isArray(curAns) ? curAns : [];
      const sel = arr.includes(opt) ? ' selected' : '';
      html += `<li class="option-item${sel}" onclick="toggleOption('${escapeAttr(opt)}')">
        <div class="checkbox"></div><span>${String.fromCharCode(65+i)}. ${escapeHtml(opt)}</span></li>`;
    });
    html += '</ul>';
  } else if (q.type === 'true_false') {
    html += '<ul class="option-list">';
    ['正确', '错误'].forEach(opt => {
      const sel = curAns === opt ? ' selected' : '';
      html += `<li class="option-item${sel}" onclick="selectOption('${opt}')">
        <div class="radio"></div><span>${opt}</span></li>`;
    });
    html += '</ul>';
  } else if (q.type === 'subjective') {
    html += `<textarea class="subjective-input" id="subj-input" placeholder="请输入你的回答..."
      oninput="saveSubjective()">${escapeHtml(curAns)}</textarea>`;
  }

  document.getElementById('q-card').innerHTML = html;
  renderQuestionNav();
}

// ===================== 题号导航 =====================
function renderQuestionNav() {
  const nav = document.getElementById('question-nav');
  if (!nav) return;
  const count = questions.length;
  nav.style.display = count <= 1 ? 'none' : '';
  let navHtml = '';
  for (let i = 0; i < count; i++) {
    const q = questions[i];
    const ans = userAnswers[q.id];
    const answered = Array.isArray(ans) ? ans.length > 0 : (ans && String(ans).trim() !== '');
    const cls = i === currentIndex ? 'current' : (answered ? 'answered' : '');
    navHtml += `<button class="q-nav-btn ${cls}" onclick="jumpToQuestion(${i})" title="第${i+1}题${answered?'（已答）':''}">${i + 1}</button>`;
  }
  nav.innerHTML = navHtml;
}

function jumpToQuestion(index) {
  saveSubjective();
  currentIndex = index;
  renderQuestion();
}

function selectOption(val) {
  userAnswers[questions[currentIndex].id] = val;
  renderQuestion();
}

function toggleOption(val) {
  const q = questions[currentIndex];
  let arr = userAnswers[q.id];
  if (!Array.isArray(arr)) arr = [];
  const idx = arr.indexOf(val);
  if (idx >= 0) arr.splice(idx, 1);
  else arr.push(val);
  userAnswers[q.id] = arr;
  renderQuestion();
}

function saveSubjective() {
  const ta = document.getElementById('subj-input');
  if (ta) userAnswers[questions[currentIndex].id] = ta.value;
}

// ===================== 导航 =====================
function prevQuestion() {
  if (currentIndex > 0) {
    saveSubjective();
    currentIndex--;
    renderQuestion();
  }
}

function nextOrSubmit() {
  saveSubjective();
  if (currentIndex < questions.length - 1) {
    currentIndex++;
    renderQuestion();
  } else {
    const unanswered = questions.filter(q => {
      const a = userAnswers[q.id];
      if (Array.isArray(a)) return a.length === 0;
      return !a || a.trim() === '';
    });
    if (unanswered.length > 0) {
      if (!confirm(`还有 ${unanswered.length} 题未作答，确定提交吗？`)) return;
    } else {
      if (!confirm('确定要提交答卷吗？')) return;
    }
    submitExam();
  }
}

// ===================== 自动保存 =====================
async function autoSave() {
  if (!examRecordId) return;
  const answers = questions.map(q => ({
    question_id: q.id,
    user_answer: userAnswers[q.id]
  }));
  try {
    await fetch(API + '/api/exam/save/' + encodeURIComponent(examRecordId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(answers)
    });
  } catch (e) {
    // 静默失败，不影响答题
  }
}

function stopAutoSave() {
  if (saveInterval) {
    clearInterval(saveInterval);
    saveInterval = null;
  }
}

// ===================== 提交 =====================
async function submitExam() {
  if (timerInterval) clearInterval(timerInterval);
  stopAutoSave();
  const answers = questions.map(q => ({
    question_id: q.id,
    user_answer: userAnswers[q.id]
  }));
  setRoute('result');
  showPage('result');
  document.getElementById('result-content').innerHTML =
    '<div style="text-align:center;padding:60px;font-size:18px;color:#aab;">正在评判中，请稍候...</div>';

  try {
    const resp = await fetch(API + '/api/exam/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record_id: examRecordId, answers })
    });
    renderResult(await resp.json());
  } catch (e) {
    document.getElementById('result-content').innerHTML =
      '<div style="text-align:center;padding:60px;color:#ff6b6b;">提交失败: ' + e.message + '</div>';
  }
}

// ===================== 结果渲染 =====================
function renderResult(result) {
  const passed = result.passed;
  const scoreCls = passed ? 'pass' : 'fail';
  const verdict = passed ? '考核通过' : '考核未通过';
  const labels = selectedSpecialties
    .map(s => specialties[s] ? specialties[s].label : s)
    .join(' + ');

  let html = `
    <div class="result-score">
      <div class="big-score ${scoreCls}">${result.final_score}</div>
      <div class="verdict" style="color:${passed?'#51cf66':'#ff6b6b'}">
        ${verdict}（及格线: ${result.pass_score} 分 | 专业方向: ${labels || '通用基础'}）
      </div>
    </div>
  `;

  // 分类统计
  if (result.category_stats) {
    html += '<div class="cat-stats">';
    for (const [cat, stat] of Object.entries(result.category_stats)) {
      html += `<div class="cat-stat">
        <div class="cat-name">${cat}</div>
        <div class="cat-acc">${stat.correct_count}/${stat.total_count}</div>
        <div style="font-size:12px;color:#889;">正确率 ${stat.accuracy}%</div>
      </div>`;
    }
    html += '</div>';
  }

  // 每题详情
  html += '<h3 style="margin-bottom:14px;color:#ccc;">答题详情</h3>';
  result.details.forEach(d => {
    const correctCls = d.is_correct ? 'correct' : 'incorrect';
    const icon = d.is_correct ? '\u2713' : '\u2717';
    const scoreColor = d.is_correct ? '#51cf66' : '#ff6b6b';
    const typeNames = { 'single_choice': '单选', 'multi_choice': '多选', 'true_false': '判断', 'subjective': '主观' };

    html += `<div class="detail-item ${correctCls}">`;
    html += `<div class="d-q"><strong>${icon}</strong> [${d.category}] ${d.question.substring(0, 60)}${d.question.length > 60 ? '...' : ''}</div>`;
    html += `<div class="d-row">
      <span><strong>你的答案:</strong> ${formatAnswer(d.user_answer)}</span>
      <span><strong>正确答案:</strong> ${formatAnswer(d.correct_answer)}</span>
    </div>`;
    html += `<div class="d-row">
      <span><strong>题型:</strong> ${typeNames[d.type] || d.type}</span>
      <span><strong>难度:</strong> ${d.difficulty} (权重×${d.weight})</span>
      <span><strong>得分:</strong> <span style="color:${scoreColor}">${d.score} / ${d.max_score}</span></span>
    </div>`;
    if (d.ai_used !== undefined) {
      html += `<div class="d-row">
        <span><strong>AI 评分:</strong> ${d.ai_score} 分</span>
        <span class="ai-badge">${d.ai_used ? 'AI 评判' : '关键词评判'}</span>
      </div>`;
      if (d.ai_comment) {
        html += `<div class="d-explain"><strong>AI 点评:</strong> ${escapeHtml(d.ai_comment)}</div>`;
      }
    }
    html += `<div class="d-explain"><strong>解析:</strong> ${escapeHtml(d.explanation)}</div>`;
    html += '</div>';
  });

  document.getElementById('result-content').innerHTML = html;
}

async function showHistory() {
  if (timerInterval) clearInterval(timerInterval);
  setRoute('history');
  showPage('history');
  loadHistory();
}

async function loadHistory() {
  const list = document.getElementById('history-list');
  list.innerHTML = '<div style="text-align:center;padding:30px;color:#aab;">正在加载...</div>';

  try {
    const resp = await fetch(API + '/api/records');
    const data = await resp.json();
    renderHistory(data.records || []);
  } catch (e) {
    list.innerHTML = '<div style="text-align:center;padding:30px;color:#ff6b6b;">加载失败: ' + escapeHtml(e.message) + '</div>';
  }
}

function renderHistory(records) {
  const list = document.getElementById('history-list');
  if (!records.length) {
    list.innerHTML = '<div style="text-align:center;padding:30px;color:#aab;">暂无考试记录</div>';
    return;
  }

  list.innerHTML = records.map(r => {
    const statusMap = { submitted: '已提交', timeout: '已超时', started: '进行中' };
    const status = statusMap[r.status] || r.status;
    const statusClass = r.status === 'timeout' ? 'timeout' : (r.status === 'submitted' ? 'submitted' : 'started');
    const score = r.final_score === null || r.final_score === undefined ? '-' : r.final_score;
    const passed = r.passed === null || r.passed === undefined ? '' : (r.passed ? ' · 通过' : ' · 未通过');
    const startedAt = formatTime(r.started_at);
    const submittedAt = r.submitted_at ? formatTime(r.submitted_at) : '-';
    const canView = true;
    return `
      <div class="history-item">
        <div class="history-main">
          <div class="history-title">${escapeHtml(r.specialty || '未选择方向')} <span class="status-${statusClass}">${status}</span></div>
          <div class="history-meta">
            分数: ${score}${passed}<br>
            开始: ${startedAt} · 提交: ${submittedAt}
          </div>
        </div>
        <div class="history-actions">
          <button class="btn btn-outline" onclick="viewRecord('${escapeAttr(r.id)}')">查看</button>
          <button class="btn btn-outline" style="color:#ff6b6b;border-color:rgba(255,107,107,0.4);margin-top:6px;" onclick="deleteRecord('${escapeAttr(r.id)}')">删除</button>
        </div>
      </div>
    `;
  }).join('');
}

function deleteRecord(recordId) {
  if (!confirm('确定要删除这条考试记录吗？此操作不可撤销。')) return;
  (async () => {
    try {
      const resp = await fetch(API + '/api/records/' + encodeURIComponent(recordId), { method: 'DELETE' });
      if (!resp.ok) throw new Error('删除失败');
      loadHistory();
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  })();
}

async function viewRecord(recordId) {
  const list = document.getElementById('history-list');
  list.innerHTML = '<div style="text-align:center;padding:30px;color:#aab;">正在加载结果...</div>';

  try {
    const resp = await fetch(API + '/api/records/' + encodeURIComponent(recordId));
    const record = await resp.json();
    if (!record.result) {
      showNoResultPage(record);
      return;
    }
    selectedSpecialties = record.specialty ? record.specialty.split(',') : [];
    setRoute('result');
    showPage('result');
    renderResult(record.result);
  } catch (e) {
    list.innerHTML = '<div style="text-align:center;padding:30px;color:#ff6b6b;">加载失败: ' + escapeHtml(e.message) + '</div>';
  }
}

function showNoResultPage(record) {
  const statusMap = { submitted: '已提交', timeout: '已超时', started: '进行中' };
  const statusText = statusMap[record.status] || record.status;
  const startedAt = formatTime(record.started_at);
  let message = '';
  if (record.status === 'timeout') {
    message = '该次考试已超时，未能在规定时间内提交答卷，无判分结果。';
  } else if (record.status === 'started') {
    message = '该次考试仍在进行中，尚未提交答卷。';
  } else {
    message = '暂无判分结果。';
  }

  const resumeBtn = record.status === 'started'
    ? `<button class="btn btn-primary" style="margin-right:10px;" onclick="resumeExam('${escapeAttr(record.id)}')">返回答题</button>`
    : '';

  document.getElementById('result-content').innerHTML = `
    <div class="result-score">
      <div class="big-score fail" style="font-size:28px;">${statusText}</div>
      <div class="verdict" style="color:#889;">${escapeHtml(record.specialty || '未选择方向')}</div>
    </div>
    <div style="text-align:center;color:#aab;font-size:15px;line-height:1.8;padding:10px 0;">
      ${message}<br>
      <span style="font-size:13px;color:#667;">开始时间: ${startedAt}</span>
    </div>
    <div style="text-align:center;margin-top:20px;">
      ${resumeBtn}
      <button class="btn btn-outline" onclick="showHistory()">返回历史记录</button>
    </div>
  `;
  setRoute('result');
  showPage('result');
}

async function resumeExam(recordId) {
  document.getElementById('result-content').innerHTML =
    '<div style="text-align:center;padding:60px;font-size:18px;color:#aab;">正在恢复答题...</div>';

  try {
    const resp = await fetch(API + '/api/exam/resume/' + encodeURIComponent(recordId));
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || '恢复失败');
    }
    examData = await resp.json();
    examRecordId = examData.record_id || null;
    questions = examData.questions;
    userAnswers = {};
    currentIndex = 0;
    selectedSpecialties = examData.specialty ? examData.specialty.split(',') : [];

    setRoute('exam');
    showPage('exam');

    const tag = document.getElementById('specialty-tag');
    const labels = selectedSpecialties
      .map(s => specialties[s] ? specialties[s].label : s)
      .join(' + ');
    tag.textContent = '方向: ' + (labels || '通用基础');

    questions.forEach(q => {
      if (q.type === 'multi_choice') userAnswers[q.id] = [];
      else userAnswers[q.id] = '';
    });

    // 恢复已保存的答案
    const saved = examData.answers || [];
    saved.forEach(a => {
      if (userAnswers.hasOwnProperty(a.question_id)) {
        userAnswers[a.question_id] = a.user_answer;
      }
    });

    // 自动跳到第一个未答题
    const firstUnanswered = questions.findIndex(q => {
      const ans = userAnswers[q.id];
      return Array.isArray(ans) ? ans.length === 0 : (!ans || ans.trim() === '');
    });
    currentIndex = firstUnanswered >= 0 ? firstUnanswered : 0;

    const totalSec = examData.time_limit_minutes * 60;
    const elapsed = Math.floor((Date.now() - new Date(examData.started_at).getTime()) / 1000);
    const remaining = Math.max(0, totalSec - elapsed);

    startTimer(remaining);
    renderQuestion();
  } catch (e) {
    document.getElementById('result-content').innerHTML =
      '<div style="text-align:center;padding:60px;color:#ff6b6b;">恢复失败: ' + escapeHtml(e.message) + '</div>';
  }
}

function backToStart() {
  if (timerInterval) clearInterval(timerInterval);
  stopAutoSave();
  setRoute('start');
  showPage('start');
}

function restartExam() {
  if (timerInterval) clearInterval(timerInterval);
  stopAutoSave();
  examData = null;
  questions = [];
  userAnswers = {};
  currentIndex = 0;
  timerSeconds = 0;
  selectedSpecialties = [];
  examRecordId = null;
  setRoute('start');
  showPage('start');
}

function formatTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatAnswer(ans) {
  if (Array.isArray(ans)) return ans.join(', ') || '（未作答）';
  return ans || '（未作答）';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
function escapeAttr(str) {
  return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

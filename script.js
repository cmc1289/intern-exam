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

const pages = ['start', 'specialty', 'exam', 'result', 'history', 'admin'];

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
  document.getElementById('admin-page').classList.toggle('hidden', page !== 'admin');
  const ee = document.getElementById('exam-entry-page');
  if (ee) ee.classList.toggle('hidden', page !== 'exam-entry');
}

function handleRoute(page) {
  // 离开考试页面时保存进度
  if (page !== 'exam' && examRecordId && questions.length > 0) {
    saveBeforeExit();
  }
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

// ===================== 启动路由 =====================
let currentJoin = null;   // { exam, candidate_session_id, candidate_name }

// 访客标识：公开自测记录按它归属（无账号体系的轻量隔离）
function getVisitorId() {
  let v = localStorage.getItem('visitor_id');
  if (!v) {
    v = (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '')
      : 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10));
    localStorage.setItem('visitor_id', v);
  }
  return v;
}

async function loadSpecialtyMap() {
  try {
    const resp = await fetch(API + '/api/specialties');
    const data = await resp.json();
    specialties = data.specialties;
  } catch (e) {
    console.error('加载专业列表失败', e);
  }
}

// 同步隐藏所有页面区块（用于深链首次加载时避免“闪现首页”）
function hideAllPages() {
  ['start-page', 'specialty-page', 'exam-page', 'result-page',
   'history-page', 'admin-page', 'exam-entry-page'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  });
}

async function boot() {
  getVisitorId();  // 确保访客标识存在
  const reportMatch = location.hash.match(/^#r\/([0-9a-f]+)/);

  // 考试入口 /exam/join：不依赖专业列表，立即渲染邀请码表单，不闪现首页
  if (location.pathname.startsWith('/exam/')) {
    const q = new URLSearchParams(location.search);
    renderJoinForm(q.get('code') || '');
    loadSpecialtyMap();  // 后台预加载，供加入后的方向标签使用
    return;
  }
  // 只读报告 /#r/<id>：先隐藏首页，加载到报告后直接展示
  if (reportMatch) {
    hideAllPages();
    await loadSpecialtyMap();
    await showRecordReport(reportMatch[1]);
    return;
  }

  // 其余情况等待专业列表（首页本身无需隐藏，默认即为首页）
  await loadSpecialtyMap();
  const hashPage = location.hash.replace('#', '');
  if (hashPage === 'admin') {
    history.replaceState({ page: 'admin' }, '', location.pathname + '#admin');
    showPage('admin');
  } else {
    setRoute('start', true);
    handleRoute('start');
  }
}

function renderJoinForm(code = '') {
  const body = document.getElementById('ee-body');
  body.innerHTML = `
    <h1>输入考试邀请码</h1>
    <p class="subtitle">这是由企业管理员发布的正式考试，请输入邀请码与你的姓名</p>
    <input id="ee-code" placeholder="邀请码（如 AGENT2026）"
      value="${escapeHtml(code)}"
      style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid rgba(255,255,255,0.2);background:rgba(255,255,255,0.05);color:#fff;margin-bottom:10px;">
    <input id="ee-name" placeholder="你的姓名（用于成绩归档）"
      style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid rgba(255,255,255,0.2);background:rgba(255,255,255,0.05);color:#fff;margin-bottom:14px;">
    <div class="msg" id="ee-msg" style="min-height:18px;color:#ff8a8a;font-size:13px;"></div>
    <div>
      <button class="btn btn-primary" onclick="joinExam()">进入考试</button>
      <button class="btn btn-outline" style="margin-left:10px;" onclick="backToStart()">返回首页</button>
    </div>
  `;
  showPage('exam-entry');
}

function renderExamCard(exam, stateText, btnLabel, btnFn) {
  const specLabel = (exam.specialties || [])
    .map(k => (specialties[k] ? specialties[k].label : k))
    .join(' / ');
  const body = document.getElementById('ee-body');
  body.innerHTML = `
    <h1>${escapeHtml(exam.title)}</h1>
    <p class="subtitle">${escapeHtml(stateText)}</p>
    <div class="info-grid">
      <div class="info-item"><div class="label">专业方向</div><div class="value">${escapeHtml(specLabel || '通用基础')}</div></div>
      <div class="info-item"><div class="label">考试时长</div><div class="value">${exam.duration} 分钟</div></div>
      <div class="info-item"><div class="label">主观题</div><div class="value">${exam.enable_subjective ? '启用' : '关闭'}</div></div>
    </div>
    <div style="margin-top:20px;">
      <button class="btn btn-primary" onclick="${btnFn}">${btnLabel}</button>
      <button class="btn btn-outline" style="margin-left:10px;" onclick="renderJoinForm()">切换账号</button>
    </div>
  `;
  showPage('exam-entry');
}

async function joinExam() {
  const code = (document.getElementById('ee-code').value || '').trim();
  const name = (document.getElementById('ee-name').value || '').trim();
  const msg = document.getElementById('ee-msg');
  if (!code) { msg.textContent = '请输入邀请码'; return; }
  if (!name) { msg.textContent = '请填写你的姓名'; return; }
  msg.textContent = '';
  try {
    const resp = await fetch(API + '/api/exams/join', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invite_code: code, candidate_name: name }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || '进入失败');
    currentJoin = {
      exam: data.exam,
      candidate_session_id: data.candidate_session_id,
      candidate_name: name,
      record_id: data.record_id || null,
      status: data.status,
    };
    if (data.status === 'submitted') {
      renderExamCard(data.exam, '你已完成该场考试，可查看本次报告', '查看本次报告',
        `showRecordReport('${data.record_id}')`);
    } else if (data.status === 'started') {
      renderExamCard(data.exam, '你有一场进行中的作答，请继续完成', '继续作答',
        `resumeExam('${data.record_id}')`);
    } else {
      renderExamCard(data.exam, '请确认考试信息后开始作答（仅一次作答机会）', '开始考试',
        'startFromEntry()');
    }
  } catch (e) {
    msg.textContent = e.message;
  }
}

function startFromEntry() {
  if (!currentJoin) return;
  const exam = currentJoin.exam;
  startExam(
    (exam.specialties || []).join(','),
    exam.id,
    currentJoin.candidate_name,
    currentJoin.candidate_session_id,
  );
}

// ===================== 专业选择（多选 1~3 个） =====================

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
async function startExam(specialty, examId = '', candidateName = '', sessionId = '') {
  setRoute('exam');
  showPage('exam');

  // 显示加载
  document.getElementById('q-card').innerHTML =
    '<div style="text-align:center;padding:60px;color:#aab;">正在生成试卷...</div>';

  const params = new URLSearchParams();
  if (specialty) params.set('specialty', specialty);
  if (examId) params.set('exam_id', examId);
  if (candidateName) params.set('candidate_name', candidateName);
  if (sessionId) params.set('candidate_session_id', sessionId);
  // 公开自测记录按访客标识归属
  if (!examId) params.set('visitor_id', getVisitorId());
  const url = API + '/api/exam/start' + (params.toString() ? '?' + params.toString() : '');

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

  let opts = null;   // 供下方闭包绑定的选项数组
  let isMulti = false;

  if (q.type === 'single_choice') {
    opts = q.options;
    html += '<ul class="option-list">';
    opts.forEach((opt, i) => {
      const sel = curAns === opt ? ' selected' : '';
      html += `<li class="option-item${sel}" data-i="${i}">
        <div class="radio"></div><span>${String.fromCharCode(65+i)}. ${escapeHtml(opt)}</span></li>`;
    });
    html += '</ul>';
  } else if (q.type === 'multi_choice') {
    opts = q.options;
    isMulti = true;
    html += '<ul class="option-list">';
    opts.forEach((opt, i) => {
      const arr = Array.isArray(curAns) ? curAns : [];
      const sel = arr.includes(opt) ? ' selected' : '';
      html += `<li class="option-item${sel}" data-i="${i}">
        <div class="checkbox"></div><span>${String.fromCharCode(65+i)}. ${escapeHtml(opt)}</span></li>`;
    });
    html += '</ul>';
  } else if (q.type === 'true_false') {
    opts = ['正确', '错误'];
    html += '<ul class="option-list">';
    opts.forEach((opt, i) => {
      const sel = curAns === opt ? ' selected' : '';
      html += `<li class="option-item${sel}" data-i="${i}">
        <div class="radio"></div><span>${opt}</span></li>`;
    });
    html += '</ul>';
  } else if (q.type === 'subjective') {
    html += `<textarea class="subjective-input" id="subj-input" placeholder="请输入你的回答..."
      oninput="saveSubjective()">${escapeHtml(curAns)}</textarea>`;
  }

  document.getElementById('q-card').innerHTML = html;

  // 用闭包绑定点击，避免内联 onclick 拼接选项文本带来的转义/引号问题
  if (opts) {
    document.querySelectorAll('#q-card .option-item').forEach(li => {
      li.addEventListener('click', () => {
        const val = opts[parseInt(li.dataset.i, 10)];
        if (isMulti) toggleOption(val);
        else selectOption(val);
      });
    });
  }

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

function saveBeforeExit() {
  // 离开考试页面或关闭浏览器前保存进度（keepalive 保证页面关闭时也能发出）
  if (!examRecordId || !questions.length) return;
  const answers = questions.map(q => ({
    question_id: q.id,
    user_answer: userAnswers[q.id]
  }));
  fetch(API + '/api/exam/save/' + encodeURIComponent(examRecordId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(answers),
    keepalive: true
  }).catch(() => {});
}

window.addEventListener('beforeunload', saveBeforeExit);

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

  // 高层能力统计：优先 assessment_category；历史记录（无 assessment_stats）回退 category
  const statSource = result.assessment_stats || result.category_stats;
  const boxEntries = statSource ? Object.entries(statSource) : [];

  // 能力卡片：只展示 assessment_category，最多 8 个
  if (boxEntries.length > 0) {
    const shown = boxEntries.length > 8
      ? boxEntries.sort((a, b) => b[1].total_count - a[1].total_count).slice(0, 8)
      : boxEntries;
    html += '<div class="cat-stats">';
    for (const [cat, stat] of shown) {
      html += `<div class="cat-stat">
        <div class="cat-name">${cat}</div>
        <div class="cat-acc">${stat.correct_count}/${stat.total_count}</div>
        <div style="font-size:12px;color:#889;">正确率 ${stat.accuracy}%</div>
      </div>`;
    }
    html += '</div>';
  }

  // 雷达图 + AI 总结
  // 数据来源同能力卡片（assessment_category），维度 >=3 时展示
  let radarLabels = null, radarValues = null;
  if (boxEntries.length >= 3) {
    let entries = boxEntries;
    // 如果维度太多，按题目权重（total_count）筛选 top 8
    if (entries.length > 8) {
      entries = entries.sort((a, b) => b[1].total_count - a[1].total_count).slice(0, 8);
    }
    radarLabels = entries.map(([cat]) => cat);
    radarValues = entries.map(([, s]) => s.accuracy);

    html += '<div class="radar-section">';
    html += '<div class="radar-box"><canvas id="abilityRadar" width="340" height="340"></canvas></div>';
    html += '<div class="ai-summary-box">';
    html += '<div class="ai-summary-label">AI 评估总结</div>';
    html += `<div class="ai-summary-text">${escapeHtml(result.ai_summary || '正在生成评估...')}</div>`;
    html += '</div></div>';
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

  // 初始化雷达图
  const canvas = document.getElementById('abilityRadar');
  if (canvas && typeof Chart !== 'undefined' && radarLabels) {
    new Chart(canvas.getContext('2d'), {
      type: 'radar',
      data: {
        labels: radarLabels,
        datasets: [{
          label: '正确率 %',
          data: radarValues,
          fill: true,
          backgroundColor: 'rgba(99, 102, 241, 0.25)',
          borderColor: 'rgba(99, 102, 241, 1)',
          borderWidth: 2,
          pointBackgroundColor: 'rgba(99, 102, 241, 1)',
          pointRadius: 4,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          r: {
            min: 0,
            max: 100,
            ticks: { display: false, stepSize: 20 },
            pointLabels: { color: '#ccc', font: { size: 12 } },
            grid: { color: 'rgba(255,255,255,0.1)' },
            angleLines: { color: 'rgba(255,255,255,0.15)' },
          },
        },
      },
    });
  }
}

async function showHistory() {
  if (timerInterval) clearInterval(timerInterval);
  setRoute('history');
  showPage('history');
  loadHistory();
}

function showAdmin() {
  if (timerInterval) clearInterval(timerInterval);
  setRoute('admin');
  showPage('admin');
}

function verifyAdminToken() {
  const token = document.getElementById('admin-token-input').value.trim();
  if (!token) {
    alert('请输入管理员令牌');
    return;
  }
  localStorage.setItem('adminToken', token);
  showHistory();
}

async function loadHistory() {
  const list = document.getElementById('history-list');
  list.innerHTML = '<div style="text-align:center;padding:30px;color:#aab;">正在加载...</div>';

  try {
    const resp = await fetch(API + '/api/records?visitor_id=' + encodeURIComponent(getVisitorId()));
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

  // 这里展示的均为当前访客自己的公开自测记录，可删除；考试记录不在此列表
  list.innerHTML = records.map(r => {
    const statusMap = { submitted: '已提交', timeout: '已超时', started: '进行中' };
    const status = statusMap[r.status] || r.status;
    const statusClass = r.status === 'timeout' ? 'timeout' : (r.status === 'submitted' ? 'submitted' : 'started');
    const score = r.final_score === null || r.final_score === undefined ? '-' : r.final_score;
    const passed = r.passed === null || r.passed === undefined ? '' : (r.passed ? ' · 通过' : ' · 未通过');
    const startedAt = formatTime(r.started_at);
    const submittedAt = r.submitted_at ? formatTime(r.submitted_at) : '-';
    const deletable = !r.exam_id;
    const deleteBtn = deletable
      ? `<button class="btn btn-outline" style="color:#ff6b6b;border-color:rgba(255,107,107,0.4);margin-top:6px;" onclick="deleteRecord('${escapeAttr(r.id)}')">删除</button>`
      : '';
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
          ${deleteBtn}
        </div>
      </div>
    `;
  }).join('');
}

function deleteRecord(recordId) {
  if (!confirm('确定要删除这条自测记录吗？此操作不可撤销。')) return;
  const token = localStorage.getItem('adminToken') || localStorage.getItem('admin_token') || '';
  (async () => {
    try {
      const headers = {};
      if (token) headers['X-Admin-Token'] = token;
      const resp = await fetch(
        API + '/api/records/' + encodeURIComponent(recordId)
          + '?visitor_id=' + encodeURIComponent(getVisitorId()),
        { method: 'DELETE', headers }
      );
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
  saveBeforeExit();
  stopAutoSave();
  setRoute('start');
  showPage('start');
}

function restartExam() {
  if (timerInterval) clearInterval(timerInterval);
  saveBeforeExit();
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
  // 先做 JS 单引号字符串层转义，再做 HTML 双引号属性层转义
  const s = String(str)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/\r?\n/g, '\\n');
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

// ===================== 只读报告视图（管理后台/链接直达） =====================
async function showRecordReport(recordId) {
  let rec;
  try {
    const resp = await fetch(API + '/api/records/' + recordId);
    if (!resp.ok) throw new Error('not found');
    rec = await resp.json();
  } catch (e) {
    alert('报告不存在或链接无效');
    backToStart();
    return;
  }
  if (!rec || rec.status !== 'submitted' || !rec.result) {
    alert('该记录尚未完成提交，无法查看报告');
    backToStart();
    return;
  }
  if (timerInterval) clearInterval(timerInterval);
  examRecordId = rec.id;
  selectedSpecialties = rec.specialty ? rec.specialty.split(',') : [];
  history.replaceState({ page: 'result' }, '', location.pathname + '#r/' + recordId);
  renderResult(rec.result);
  showPage('result');
}

// 启动路由（脚本位于 body 末尾，DOM 已就绪）
boot();

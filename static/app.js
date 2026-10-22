'use strict';
const app = document.querySelector('#app');
const storage = {
  get(key, fallback = null) { try { return JSON.parse(localStorage.getItem('quiz:' + key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem('quiz:' + key, JSON.stringify(value)); } catch { /* Server remains the source of saved answers. */ } },
};
const e = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value !== false && value != null) node.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat(Infinity)) if (child != null) node.append(child instanceof Node ? child : String(child));
  return node;
};
const button = (label, action, secondary = false, attrs = {}) => e('button', {type: 'button', class: 'button' + (secondary ? ' secondary' : ''), onclick: action, ...attrs}, label);
const link = (label, href, secondary = false) => e('a', {class: 'button' + (secondary ? ' secondary' : ''), href}, label);
const clock = seconds => { const s = Math.max(0, Math.floor(seconds)); return `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`; };
const date = timestamp => new Date(timestamp * 1000).toLocaleString('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric'});
const score = value => Number(value).toLocaleString('vi-VN', {maximumFractionDigits: 2});
let config, exam = null, questionIndex = 0, routeVersion = 0, timer = null, toastTimer;

async function api(path, method = 'GET', data) {
  let response;
  try {
    response = await fetch('/api/' + path, {method, headers: data === undefined ? {} : {'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
  } catch { throw new Error('Mất kết nối. Câu trả lời chưa gửi sẽ được giữ trên trình duyệt; hãy thử lại khi có mạng.'); }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(result.error || 'Máy chủ chưa xử lý được yêu cầu. Vui lòng thử lại.');
    error.status = response.status; throw error;
  }
  return result;
}
function toast(message) {
  const node = document.querySelector('#toast'); node.textContent = message; node.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { node.hidden = true; }, 6000);
}
function confirmAction(title, message, label) {
  const dialog = document.querySelector('#confirm-dialog');
  document.querySelector('#confirm-title').textContent = title;
  document.querySelector('#confirm-text').textContent = message;
  document.querySelector('#confirm-ok').textContent = label;
  dialog.returnValue = ''; dialog.showModal();
  return new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), {once: true}));
}
function show(...nodes) { app.replaceChildren(...nodes); app.setAttribute('aria-busy', 'false'); }
function pageHead(title, description, eyebrow = 'PHÒNG LUYỆN THI') {
  return e('header', {class: 'page-head'}, e('span', {class: 'eyebrow'}, eyebrow), e('h1', {}, title), e('p', {}, description));
}
function errorPage(error) {
  show(e('section', {class: 'empty'}, e('h2', {}, 'Chưa mở được nội dung'), e('p', {}, error.message), button('Thử lại', route), link('Về luyện thi', '#home', true)));
}

function homeView() {
  const name = e('input', {id: 'nickname', name: 'nickname', required: true, minlength: 2, maxlength: 30, autocomplete: 'nickname', placeholder: 'Ví dụ: Minh Anh', 'aria-describedby': 'name-note'});
  name.value = storage.get('nickname', '');
  const formError = e('p', {class: 'form-error', role: 'alert'});
  const start = e('button', {type: 'submit', class: 'button full'}, 'Bắt đầu làm bài', e('span', {'aria-hidden': 'true'}, '↗'));
  const form = e('form', {class: 'start-card', onsubmit: async event => {
    event.preventDefault(); formError.textContent = '';
    if (storage.get('active') && !await confirmAction('Bắt đầu lượt mới?', 'Bài đang làm sẽ được kết thúc mà không đưa lên bảng xếp hạng. Bạn có thể chọn “Tiếp tục bài đang làm” để giữ lượt cũ.', 'Tạo đề mới')) return;
    start.disabled = true;
    try {
      const created = await api('exams', 'POST', {nickname: name.value.trim()});
      storage.set('nickname', name.value.trim()); storage.set('active', created.id);
      exam = null; location.hash = 'exam/' + created.id;
    } catch (error) { formError.textContent = error.message; start.disabled = false; }
  }},
    e('div', {class: 'card-top'}, e('span', {class: 'label'}, 'MỘT LƯỢT THỬ MỚI'), e('span', {class: 'small'}, '40 câu · 45 phút')),
    e('h2', {}, 'Bạn đã sẵn sàng?'), e('p', {class: 'small'}, 'Mỗi lượt là một đề mới. Mỗi câu là một cơ hội để hiểu chắc hơn.'),
    e('label', {for: 'nickname'}, 'Biệt danh của bạn'), name, formError, start,
    e('p', {class: 'public-note', id: 'name-note'}, 'Khi bắt đầu, bạn đồng ý công khai biệt danh, điểm và chi tiết bài đã nộp. Không cần tài khoản. Biệt danh có thể trùng, không xác minh danh tính.'),
  );
  if (storage.get('active')) form.append(e('div', {class: 'resume'}, button('Tiếp tục bài đang làm →', () => { location.hash = 'exam/' + storage.get('active'); }, true)));
  show(
    e('section', {class: 'hero'},
      e('div', {}, e('span', {class: 'eyebrow'}, 'AICB / DATA ANNOTATION'),
        e('h1', {}, 'Thử sức.', e('br'), 'Biết mình ', e('em', {}, 'cần ôn gì.')),
        e('p', {class: 'lead'}, 'Một phòng luyện thi nhỏ cho những kiến thức lớn. Làm đề ngẫu nhiên, xem lại từng đáp án và theo dõi tiến bộ của bạn.'),
        e('div', {class: 'hero-meta'},
          e('div', {}, e('strong', {}, config.question_count), e('span', {}, 'câu trắc nghiệm')),
          e('div', {}, e('strong', {}, config.topics.length), e('span', {}, 'chủ đề kiến thức')),
          e('div', {}, e('strong', {}, '01'), e('span', {}, 'bước để bắt đầu')))), form),
    e('section', {}, e('div', {class: 'section-head'}, e('div', {}, e('span', {class: 'eyebrow'}, 'TRONG NGÂN HÀNG ĐỀ'), e('h2', {}, 'Từ nền tảng đến thực hành')), e('p', {}, '40 câu được rút từ các chủ đề dưới đây.')),
      e('div', {class: 'topics'}, config.topics.map((t, i) => e('article', {class: 'topic'}, e('span', {class: 'index'}, String(i + 1).padStart(2, '0')), e('div', {}, e('h3', {}, t.title), e('p', {}, t.count + ' câu hỏi')))))),
    e('aside', {class: 'bottom-banner'}, e('div', {}, e('h3', {}, 'Một lượt thi. Một điểm bắt đầu mới.'), e('p', {}, 'Xem những lượt làm bài đã hoàn thành từ cộng đồng.')), link('Khám phá bảng xếp hạng ↗', '#leaderboard')),
  );
}

function persistDraft(ex) { storage.set('draft:' + ex.id, ex.answers); }
function updateSaveStatus(ex, failed = false) {
  if (exam !== ex) return;
  const node = document.querySelector('#save-status');
  if (!node) return;
  node.classList.toggle('bad', failed);
  node.textContent = failed ? 'Chưa đồng bộ được. Đang giữ nháp trên trình duyệt; hãy kiểm tra mạng và thử lưu lại.' : ex.pending.size ? `Đang đồng bộ ${ex.pending.size} câu…` : 'Đã lưu trên máy chủ.';
}
async function flush(ex) {
  if (ex.saving) return ex.saving;
  ex.saving = (async () => {
    while (ex.pending.size) {
      const [id, option] = ex.pending.entries().next().value;
      const saved = await api(`exams/${ex.id}/answers`, 'PUT', {question_id: id, option});
      if (saved.status === 'completed') {
        ex.pending.clear(); openCompleted(ex.id); return;
      }
      if (ex.pending.get(id) === option) ex.pending.delete(id);
      updateSaveStatus(ex);
    }
  })();
  try { await ex.saving; } catch (error) { updateSaveStatus(ex, true); throw error; }
  finally { ex.saving = null; }
}
function openCompleted(id) {
  if (storage.get('active') === id) storage.set('active', null);
  storage.set('draft:' + id, null);
  if (location.hash === '#exam/' + id) location.hash = 'result/' + id;
}
function updateExamNavigation() {
  const answered = Object.values(exam.answers).filter(value => value != null).length;
  document.querySelector('#answered-count').textContent = `${answered}/${exam.questions.length} câu đã chọn`;
  document.querySelector('#answer-progress').value = answered;
  document.querySelectorAll('[data-question-index]').forEach(node => {
    const index = Number(node.dataset.questionIndex), q = exam.questions[index];
    const done = exam.answers[q.id] != null;
    node.classList.toggle('answered', done); node.classList.toggle('current', index === questionIndex);
    node.setAttribute('aria-label', `Câu ${index + 1}${done ? ', đã chọn' : ', chưa chọn'}`);
    if (index === questionIndex) node.setAttribute('aria-current', 'step'); else node.removeAttribute('aria-current');
  });
}
function selectAnswer(option, advance = true) {
  const q = exam.questions[questionIndex], ex = exam;
  ex.answers[q.id] = option; ex.pending.set(q.id, option); persistDraft(ex);
  renderQuestion(); updateExamNavigation(); updateSaveStatus(ex);
  document.querySelectorAll('.option')[option]?.focus({preventScroll: true});
  flush(ex).catch(error => toast(error.message));
  if (advance && questionIndex < ex.questions.length - 1) goQuestion(questionIndex + 1);
}
function goQuestion(index) {
  questionIndex = index; renderQuestion(); updateExamNavigation();
  document.querySelector('#question-heading').focus({preventScroll: true});
  if (window.innerWidth < 760) document.querySelector('#question-panel').scrollIntoView({block: 'start'});
}
function renderQuestion() {
  const q = exam.questions[questionIndex], selected = exam.answers[q.id];
  const options = q.options.map((text, i) => e('button', {
    type: 'button', class: 'option', role: 'radio', 'aria-checked': String(selected === i),
    tabindex: selected === i || (selected == null && i === 0) ? 0 : -1,
    onclick: () => selectAnswer(i), onkeydown: event => {
      if (['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft'].includes(event.key)) {
        event.preventDefault(); selectAnswer((i + (['ArrowDown', 'ArrowRight'].includes(event.key) ? 1 : 3)) % 4, false);
      }
    },
  }, e('span', {class: 'letter', 'aria-hidden': 'true'}, 'ABCD'[i]), e('span', {}, text)));
  document.querySelector('#question-panel').replaceChildren(
    e('div', {class: 'question-meta'}, e('span', {class: 'label'}, `CÂU ${String(questionIndex + 1).padStart(2, '0')} / ${exam.questions.length}`), e('span', {}, 'Chọn 1 đáp án')),
    e('p', {class: 'topic-line'}, q.topic), e('h2', {id: 'question-heading', tabindex: -1}, q.q),
    e('div', {class: 'options', role: 'radiogroup', 'aria-labelledby': 'question-heading'}, options),
    e('div', {class: 'question-actions'},
      button('← Câu trước', () => goQuestion(questionIndex - 1), true, {disabled: questionIndex === 0}),
      questionIndex < exam.questions.length - 1 ? button('Câu tiếp theo →', () => goQuestion(questionIndex + 1)) : button('Xem lại & nộp bài', () => submit(false))),
  );
}
async function examView(id, version) {
  const data = await api('exams/' + id);
  if (version !== routeVersion) return;
  if (data.status === 'completed') { openCompleted(id); return; }
  const draft = storage.get('draft:' + id, {});
  const pending = new Map();
  const ids = new Set(data.questions.map(q => q.id));
  if (draft && typeof draft === 'object') for (const [key, value] of Object.entries(draft)) {
    if (ids.has(key) && Number.isInteger(value) && value >= 0 && value < 4 && data.answers[key] !== value) {
      data.answers[key] = value; pending.set(key, value);
    }
  }
  exam = {...data, pending, saving: null, submitting: false, offset: data.server_now * 1000 - Date.now()};
  questionIndex = 0; storage.set('active', id);
  const ex = exam;
  show(
    e('header', {class: 'exam-header'}, e('div', {}, e('span', {class: 'eyebrow'}, 'TẬP TRUNG VÀO TỪNG CÂU'), e('h1', {}, 'Lượt thi của ' + ex.nickname)),
      e('div', {class: 'timebox'}, e('div', {}, e('small', {}, 'THỜI GIAN CÒN LẠI'), e('strong', {class: 'timer', id: 'timer', role: 'timer'})), e('span', {class: 'small'}, '/ 45 phút'))),
    e('div', {class: 'exam-grid'}, e('div', {}, e('section', {class: 'panel question-panel', id: 'question-panel'}),
      e('p', {class: 'save-line', id: 'save-status', role: 'status', 'aria-live': 'polite'}), button('Lưu lại câu chưa đồng bộ', () => flush(ex).catch(error => toast(error.message)), true)),
      e('aside', {class: 'panel exam-side'}, e('h2', {}, 'Bản đồ câu hỏi'), e('p', {id: 'answered-count'}), e('progress', {id: 'answer-progress', max: ex.questions.length, value: 0, 'aria-label': 'Số câu đã chọn'}),
        e('div', {class: 'question-grid', role: 'navigation', 'aria-label': 'Chuyển đến câu hỏi'}, ex.questions.map((_, i) => e('button', {type: 'button', 'data-question-index': i, onclick: () => goQuestion(i)}, i + 1))),
        e('div', {class: 'legend'}, e('span', {}, e('i', {class: 'done'}), 'Đã chọn'), e('span', {}, e('i'), 'Chưa chọn')),
        button('Nộp bài →', () => submit(false), false, {id: 'submit-button'}),
        e('p', {}, 'Câu bỏ trống được tính 0 điểm. Hết giờ, bài được chấm theo các câu đã lưu.'))),
  );
  renderQuestion(); updateExamNavigation(); updateSaveStatus(ex);
  const tick = () => {
    const remaining = ex.deadline_at - (Date.now() + ex.offset) / 1000;
    const display = document.querySelector('#timer'); if (!display) return;
    display.textContent = clock(remaining); display.classList.toggle('low', remaining < 120);
    if (remaining <= 0 && !ex.submitting) submit(true);
  };
  tick(); timer = setInterval(tick, 1000);
  if (pending.size) flush(ex).catch(error => toast(error.message));
}
async function submit(automatic) {
  const ex = exam; if (!ex || ex.submitting) return;
  const left = ex.questions.length - Object.values(ex.answers).filter(value => value != null).length;
  if (!automatic && !await confirmAction('Nộp bài để xem kết quả?', left ? `Bạn còn ${left} câu bỏ trống. Sau khi nộp, kết quả và chi tiết bài làm sẽ được công khai.` : 'Bạn đã trả lời đủ 40 câu. Sau khi nộp, kết quả và chi tiết bài làm sẽ được công khai.', 'Nộp bài')) return;
  if (exam !== ex || ex.submitting) return;
  ex.submitting = true;
  const btn = document.querySelector('#submit-button'); if (btn) { btn.disabled = true; btn.textContent = 'Đang nộp…'; }
  try {
    if (!automatic) await flush(ex);
    await api(`exams/${ex.id}/submit`, 'POST', {answers: ex.answers});
    openCompleted(ex.id);
  } catch (error) {
    toast(error.message); if (automatic) await new Promise(resolve => setTimeout(resolve, 4000));
  } finally {
    ex.submitting = false;
    if (btn) { btn.disabled = false; btn.textContent = 'Nộp bài →'; }
  }
}

async function resultView(id, version) {
  const data = await api('results/' + id);
  if (version !== routeVersion) return;
  openCompleted(id);
  const total = data.total, wrong = total - data.correct - data.unanswered;
  const title = `${data.nickname} · ${date(data.submitted_at)} (giờ Việt Nam)`;
  show(pageHead('Nhìn lại để tiến xa hơn.', title, 'KẾT QUẢ CÔNG KHAI'),
    e('section', {class: 'result-hero'}, e('div', {class: 'result-score'}, score(data.score), e('span', {}, ' / 10')),
      e('div', {}, e('span', {class: 'eyebrow'}, `${data.correct}/${total} CÂU CHÍNH XÁC`), e('h2', {}, data.assessment),
        e('p', {}, data.finish_reason === 'timeout' ? 'Đã hết giờ. Kết quả dựa trên những câu máy chủ nhận được trước hạn nộp.' : 'Điểm số là một dấu mốc. Những câu chưa chắc là gợi ý cho buổi ôn tiếp theo.'),
        e('div', {class: 'actions'}, link('Làm một đề mới ↗', '#home'), link('Xem bảng xếp hạng', '#leaderboard', true), button('Sao chép link kết quả', async () => {
          try { await navigator.clipboard.writeText(location.href); toast('Đã sao chép link kết quả.'); }
          catch { toast('Bạn có thể sao chép địa chỉ trên thanh URL để chia sẻ kết quả.'); }
        }, true)))),
    e('div', {class: 'stats'}, [['Đúng', data.correct], ['Sai', wrong], ['Bỏ trống', data.unanswered], ['Thời gian', clock(data.duration)]].map(([label, value]) => e('div', {class: 'stat'}, e('b', {}, value), e('span', {}, label)))),
    e('div', {class: 'section-head'}, e('div', {}, e('span', {class: 'eyebrow'}, 'ÔN ĐÚNG TRỌNG TÂM'), e('h2', {}, 'Kiến thức theo chủ đề')), e('p', {}, 'Chỉ phản ánh các câu xuất hiện trong lượt này.')),
    e('div', {class: 'result-topics'}, data.topics.sort((a, b) => a.correct / a.total - b.correct / b.total).map(t => e('div', {class: 'topic-result'}, e('div', {}, e('strong', {}, t.title), e('span', {}, `${t.correct}/${t.total}`)), e('progress', {value: t.correct, max: t.total, 'aria-label': `${t.title}: ${t.correct} trên ${t.total} câu đúng` })))),
    e('div', {class: 'section-head'}, e('div', {}, e('span', {class: 'eyebrow'}, 'HIỂU THÊM SAU MỖI CÂU'), e('h2', {}, 'Đáp án & giải thích')), e('p', {}, `Bộ đề ${data.bank_version}`)),
    ...data.questions.map((q, i) => e('details', {class: 'review'},
      e('summary', {}, e('span', {class: 'badge' + (q.correct ? '' : q.selected == null ? ' skip' : ' wrong')}, q.correct ? 'ĐÚNG' : q.selected == null ? 'BỎ TRỐNG' : 'SAI'), e('span', {}, `${i + 1}. ${q.q}`)),
      e('div', {class: 'review-body'}, q.options.map((text, j) => e('div', {class: 'review-option' + (j === q.answer ? ' right' : j === q.selected ? ' wrong' : '')}, `${'ABCD'[j]}. ${text}${j === q.answer ? ' · Đáp án đúng' : ''}${j === q.selected ? ' · Bạn chọn' : ''}`)),
        e('p', {class: 'explanation'}, q.explain), e('p', {class: 'source'}, `Nguồn: ${q.source.document} · ${q.source.group}. PDF đối chiếu theo chủ đề: ${q.source.references.join(', ')}.`)))),
  );
}

async function listView(kind, page, query, version) {
  const board = kind === 'leaderboard';
  const data = await api(`${kind}?page=${page}&q=${encodeURIComponent(query)}`);
  if (version !== routeVersion) return;
  const input = e('input', {type: 'search', maxlength: 30, 'aria-label': 'Tìm theo biệt danh', placeholder: 'Tìm biệt danh…', name: 'q'}); input.value = query;
  const search = e('form', {class: 'toolbar', onsubmit: event => { event.preventDefault(); location.hash = `${kind}?page=1&q=${encodeURIComponent(input.value.trim())}`; }}, input, e('button', {class: 'button secondary', type: 'submit'}, 'Tìm kiếm'), e('span', {}, `${data.total} lượt hoàn thành`));
  const title = board ? 'Mỗi lần thử, một dấu mốc.' : 'Những lượt làm bài đã hoàn thành.';
  const description = board ? 'Xếp theo số câu đúng, thời gian làm bài, rồi thời điểm nộp. Mỗi hàng là một lượt thi 40 câu thuộc phiên bản ngân hàng hiện tại.' : 'Điểm và chi tiết bài đã nộp được lưu công khai. Biệt danh có thể trùng; đây không phải danh tính đã xác minh.';
  const headers = board ? ['Hạng', 'Biệt danh', 'Điểm', 'Đúng / Tổng', 'Thời gian', 'Nộp bài (VN)', ''] : ['Biệt danh', 'Điểm', 'Đúng / Tổng', 'Thời gian', 'Nộp bài (VN)', 'Bộ đề', ''];
  const rows = data.items.map((row, i) => e('tr', {},
    board ? e('td', {class: 'rank'}, String(row.rank).padStart(2, '0')) : null,
    e('td', {}, row.nickname), e('td', {class: 'score-cell'}, score(row.score)), e('td', {}, `${row.correct}/${row.total}`), e('td', {}, clock(row.duration)), e('td', {}, date(row.submitted_at)),
    !board ? e('td', {class: 'small'}, row.bank_version) : null,
    e('td', {}, e('a', {class: 'result-link', href: '#result/' + row.id}, 'Xem bài ↗')),
  ));
  const toPage = n => { location.hash = `${kind}?page=${n}&q=${encodeURIComponent(query)}`; };
  show(pageHead(title, description, board ? 'BẢNG XẾP HẠNG CÔNG KHAI' : 'LỊCH SỬ CÔNG KHAI'), search,
    rows.length ? e('div', {class: 'table-wrap'}, e('table', {}, e('thead', {}, e('tr', {}, headers.map(h => e('th', {scope: 'col'}, h || 'Chi tiết')))), e('tbody', {}, rows))) :
      e('div', {class: 'empty'}, e('h2', {}, query ? 'Chưa tìm thấy biệt danh này.' : 'Bảng còn trống. Bắt đầu từ bạn nhé?'), e('p', {}, query ? 'Thử tìm với một phần biệt danh hoặc bỏ bộ lọc.' : 'Hoàn thành một đề để lưu dấu mốc đầu tiên.'), link('Vào phòng luyện thi ↗', '#home')),
    e('nav', {class: 'pager', 'aria-label': 'Phân trang'}, button('← Trang trước', () => toPage(data.page - 1), true, {disabled: data.page <= 1}), e('span', {}, `Trang ${data.page} / ${data.pages}`), button('Trang sau →', () => toPage(data.page + 1), true, {disabled: data.page >= data.pages})),
  );
}

async function route() {
  const version = ++routeVersion;
  const dialog = document.querySelector('#confirm-dialog');
  if (dialog.open) dialog.close('cancel');
  clearInterval(timer); timer = null;
  const [path, query = ''] = location.hash.slice(1).split('?'), [view = 'home', id] = (path || 'home').split('/');
  document.querySelectorAll('[data-nav]').forEach(node => {
    const current = node.dataset.nav === (['exam', 'result'].includes(view) ? 'home' : view);
    node.classList.toggle('active', current);
    if (current) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current');
  });
  app.setAttribute('aria-busy', 'true');
  try {
    if (!config) config = await api('config');
    if (version !== routeVersion) return;
    if (view === 'exam' && /^[a-f0-9]{32}$/.test(id || '')) await examView(id, version);
    else if (view === 'result' && /^[a-f0-9]{32}$/.test(id || '')) await resultView(id, version);
    else if (['leaderboard', 'history'].includes(view)) {
      const params = new URLSearchParams(query), raw = Number(params.get('page') || 1);
      await listView(view, Number.isInteger(raw) && raw > 0 ? raw : 1, params.get('q') || '', version);
    } else homeView();
    if (version === routeVersion) window.scrollTo({top: 0});
  } catch (error) {
    if (version !== routeVersion) return;
    if (view === 'exam' && storage.get('active') === id && error.status === 404) storage.set('active', null);
    errorPage(error);
  }
}
window.addEventListener('hashchange', route);
document.querySelector('.skip').addEventListener('click', event => {
  event.preventDefault(); document.querySelector('#main').focus();
});
window.addEventListener('online', () => { if (exam?.pending.size) flush(exam).catch(error => toast(error.message)); });
window.addEventListener('beforeunload', event => { if (exam?.pending.size) { event.preventDefault(); event.returnValue = ''; } });
setInterval(() => { if (exam?.pending.size && !exam.submitting) flush(exam).catch(() => {}); }, 6000);
route();

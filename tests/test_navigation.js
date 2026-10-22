// Optional UI-logic check: node tests/test_navigation.js (no packages required).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const context = vm.createContext({
  exam: {questions: [{id: 'first'}, {id: 'last'}], answers: {}, pending: new Map()},
  questionIndex: 0,
  persistDraft: () => {}, renderQuestion: () => {}, updateExamNavigation: () => {},
  updateSaveStatus: () => {}, document: {querySelectorAll: () => []},
  flush: () => Promise.resolve(), toast: () => {},
  goQuestion: index => { context.questionIndex = index; },
});
vm.runInContext(source.slice(source.indexOf('function selectAnswer('), source.indexOf('function goQuestion(')), context);
vm.runInContext('selectAnswer(2)', context);
assert.equal(context.questionIndex, 1, 'Selecting an answer advances to the next question');
assert.equal(context.exam.answers.first, 2, 'Answer stays attached to the original question');
assert.equal(context.exam.pending.get('first'), 2, 'Original answer is queued for saving');
vm.runInContext('selectAnswer(1)', context);
assert.equal(context.questionIndex, 1, 'Last question stays open and does not submit');
context.questionIndex = 0;
vm.runInContext('selectAnswer(3, false)', context);
assert.equal(context.questionIndex, 0, 'Arrow-key selection stays within the current radio group');
assert.equal(context.exam.answers.first, 3);
console.log('Auto-next, last-question, answer ownership and keyboard checks passed.');

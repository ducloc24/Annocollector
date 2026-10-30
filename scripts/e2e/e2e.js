// Drives the real UI in Chrome against the real API (frontend :3000). Usage:
//   1. cd be && SMOKE_STOP_AFTER_SETUP=1 uv run python scripts/smoke_flow.py  (prints SETUP {run, project})
//   2. npm --prefix fe run build && npm --prefix fe run start
//   3. npm i puppeteer-core, then HR_FILE=<file with email= and password= lines> node scripts/e2e/e2e.js <run> <project>
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const [RUN, PROJECT] = process.argv.slice(2);
const BASE = 'http://localhost:3000';
const SHOTS = __dirname;
const PASSWORD = 'smoke-password-1';
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const creds = Object.fromEntries(
  fs.readFileSync(process.env.HR_FILE, 'utf8').split(/\r?\n/).filter(Boolean).map((l) => l.split(/=(.*)/s).slice(0, 2)),
);

let passed = 0;
const problems = [];
const log = (ok, label, extra = '') => {
  console.log(`[${ok ? 'OK ' : 'FAIL'}] ${label}${extra ? ' — ' + extra : ''}`);
  if (ok) passed++;
  else problems.push(label);
};

async function session(browser, who) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  page.setDefaultTimeout(90000);
  await page.setViewport({ width: 1366, height: 900 });
  page.on('pageerror', (e) => problems.push(`[${who}] page error: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) {
      problems.push(`[${who}] console error: ${m.text().slice(0, 200)}`);
    }
  });
  return page;
}

async function login(page, email, password) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('input[type=email]');
  await page.type('input[type=email]', email);
  await page.type('input[type=password]', password);
  await Promise.all([
    page.waitForFunction(() => location.pathname === '/', { timeout: 120000 }),
    page.click('button[type=submit]'),
  ]);
}

const text = (page) => page.evaluate(() => document.body.innerText);
async function waitText(page, needle, timeout = 120000) {
  await page.waitForFunction((n) => document.body.innerText.includes(n), { timeout }, needle);
}
async function waitClickable(page, needle, selector = 'button, a', timeout = 120000) {
  await page.waitForFunction(
    (n, sel) => [...document.querySelectorAll(sel)].some((e) => e.innerText && e.innerText.trim().includes(n) && !e.disabled),
    { timeout },
    needle,
    selector,
  );
}
async function clickByText(page, needle, selector = 'button, a') {
  await waitClickable(page, needle, selector);
  const handle = await page.evaluateHandle(
    (n, sel) => [...document.querySelectorAll(sel)].find((e) => e.innerText && e.innerText.trim().includes(n) && !e.disabled),
    needle,
    selector,
  );
  const el = handle.asElement();
  if (!el) throw new Error(`no clickable "${needle}"`);
  await el.click();
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

async function step(label, fn, page) {
  try {
    await fn();
    log(true, label);
  } catch (e) {
    log(false, label, e.message.slice(0, 200));
    if (page) await shot(page, label.replace(/\W+/g, '_').slice(0, 40)).catch(() => {});
  }
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
  try {
    // ---------------- HR ----------------
    const hr = await session(browser, 'hr');
    await step('HR logs in and sees the home page', async () => {
      await login(hr, creds.email, creds.password);
      await waitText(hr, 'Xin chào');
    }, hr);
    await step('HR menu shows admin entries only', async () => {
      const t = await text(hr);
      for (const need of ['Người dùng', 'Đội đánh giá', 'Audit']) if (!t.includes(need)) throw new Error(`missing ${need}`);
      if (t.includes('Hệ thống')) throw new Error('HR must not see the system page');
    }, hr);
    await step('HR opens the users list', async () => {
      await hr.goto(`${BASE}/admin/users`, { waitUntil: 'domcontentloaded' });
      await waitText(hr, `Smoke annotator`);
    }, hr);
    await step('HR creates a user in the UI and gets an activation link', async () => {
      await clickByText(hr, 'Tạo người dùng');
      await hr.waitForSelector('input[type=email]');
      const inputs = await hr.$$('div[class*="max-w-lg"] input');
      await inputs[0].type('E2E Browser User');
      await hr.type('input[type=email]', `e2e-${RUN}-${Date.now()}@example.invalid`);
      await clickByText(hr, 'Tạo', 'button[type=submit]');
      await hr.waitForFunction(() => [...document.querySelectorAll('input')].some((i) => i.value.includes('/activate?token=')), { timeout: 120000 });
    }, hr);
    await step('HR opens the teams page and the team detail', async () => {
      await hr.goto(`${BASE}/admin/teams`, { waitUntil: 'domcontentloaded' });
      await waitText(hr, `Smoke team ${RUN}`);
      await clickByText(hr, `Smoke team ${RUN}`, 'a');
      await waitText(hr, 'Thành viên');
      await waitText(hr, 'Smoke reviewer');
    }, hr);

    // ---------------- PO ----------------
    const po = await session(browser, 'po');
    await step('PO logs in', async () => {
      await login(po, `smoke-po-${RUN}@example.invalid`, PASSWORD);
      await waitText(po, 'Xin chào');
    }, po);
    await step('PO workspace shows the tabs for an owner', async () => {
      await po.goto(`${BASE}/projects/${PROJECT}`, { waitUntil: 'domcontentloaded' });
      await waitText(po, 'Tổng quan');
      const t = await text(po);
      for (const need of ['Thành viên và đội', 'Guideline', 'Dữ liệu', 'Cấu hình job', 'Task', 'Job', 'Escalation', 'Khiếu nại', 'Chất lượng', 'Nhật ký']) {
        if (!t.includes(need)) throw new Error(`missing tab ${need}`);
      }
      await waitText(po, 'Tiến độ');
    }, po);
    for (const [tab, needle] of [['people', 'Đội đánh giá'], ['guideline', 'Mã lỗi'], ['data', 'Dataset version'], ['config', 'Cấu hình job'], ['tasks', 'Đợt 1'], ['jobs', 'Tải của từng người'], ['appeals', 'Khiếu nại của annotator'], ['quality', 'Lỗi thường gặp'], ['audit', 'Nhật ký của project']]) {
      await step(`PO tab "${tab}" renders`, async () => {
        await po.goto(`${BASE}/projects/${PROJECT}?tab=${tab}`, { waitUntil: 'domcontentloaded' });
        await waitText(po, needle);
      }, po);
    }
    await step('PO opens the config editor with a live form preview', async () => {
      await po.goto(`${BASE}/projects/${PROJECT}?tab=config`, { waitUntil: 'domcontentloaded' });
      await waitText(po, 'Version mới');
      await clickByText(po, 'Version mới');
      await waitText(po, 'Xem trước form gán nhãn');
      await clickByText(po, 'Sai', 'button');
      await waitText(po, 'Lý do');
      await shot(po, 'config_editor');
    }, po);

    // ---------------- annotator ----------------
    const ann = await session(browser, 'annotator');
    await step('Annotator logs in and sees the queue menu', async () => {
      await login(ann, `smoke-annotator-${RUN}@example.invalid`, PASSWORD);
      const t = await text(ann);
      if (!t.includes('Gán nhãn')) throw new Error('no Gán nhãn menu');
      if (t.includes('Người dùng')) throw new Error('annotator sees admin menu');
    }, ann);
    await step('Annotator pulls the next job', async () => {
      await ann.goto(`${BASE}/work`, { waitUntil: 'domcontentloaded' });
      await waitText(ann, 'Lấy việc tiếp theo');
      await Promise.all([
        ann.waitForFunction(() => /\/jobs\/[^/]+\/annotate/.test(location.pathname), { timeout: 120000 }),
        clickByText(ann, 'Lấy việc tiếp theo'),
      ]);
      await waitText(ann, 'tool call đã gán nhãn');
    }, ann);
    await step('Annotator labels every tool call', async () => {
      for (let i = 0; i < 12; i++) {
        const progress = await text(ann);
        const m = progress.match(/(\d+)\/(\d+) tool call đã gán nhãn/);
        if (m && m[1] === m[2]) break;
        await clickByText(ann, 'Đúng', 'button');
        await new Promise((r) => setTimeout(r, 300));
        if (!(await ann.evaluate(() => [...document.querySelectorAll('button')].some((b) => b.innerText.includes('Sau →') && !b.disabled)))) break;
        await clickByText(ann, 'Sau →', 'button');
      }
      const m = (await text(ann)).match(/(\d+)\/(\d+) tool call đã gán nhãn/);
      if (!m || m[1] !== m[2]) throw new Error(`progress ${m && m[0]}`);
      await shot(ann, 'annotate_done');
    }, ann);
    await step('Submit stays disabled until the self-check is ticked, then submits', async () => {
      const disabled = await ann.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.innerText.trim() === 'Nộp job')?.disabled);
      if (disabled !== true) throw new Error('submit should be disabled before self-check');
      for (const box of await ann.$$('aside input[type=checkbox]')) await box.click();
      await clickByText(ann, 'Nộp job', 'button');
      await waitText(ann, 'Đã nộp job');
    }, ann);

    // ---------------- reviewer ----------------
    const rev = await session(browser, 'reviewer');
    await step('Reviewer logs in and pulls a job to review', async () => {
      await login(rev, `smoke-reviewer-${RUN}@example.invalid`, PASSWORD);
      await rev.goto(`${BASE}/review`, { waitUntil: 'domcontentloaded' });
      await waitText(rev, 'Lấy việc chấm');
      await Promise.all([
        rev.waitForFunction(() => /\/jobs\/[^/]+\/review/.test(location.pathname), { timeout: 120000 }),
        clickByText(rev, 'Lấy việc chấm'),
      ]);
      await waitText(rev, 'NHÃN CỦA ANNOTATOR'); // upper-cased by CSS
    }, rev);
    await step('Reviewer records an error, rejects with a reason', async () => {
      await rev.waitForSelector('aside select');
      const selects = await rev.$$('aside select');
      const options = await selects[0].evaluate((s) => [...s.options].map((o) => o.value).filter(Boolean));
      await selects[0].select(options[0]);
      await clickByText(rev, 'Thêm lỗi', 'button');
      await waitText(rev, 'Lỗi đã ghi (1)');
      await rev.evaluate(() => {
        const sel = [...document.querySelectorAll('aside select')].at(-1);
        sel.value = 'reject';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      });
      await rev.type('aside textarea:last-of-type', 'Bước đầu đánh giá sai, hãy xem lại guideline.');
      await clickByText(rev, 'Lưu quyết định', 'button');
      await waitText(rev, 'Đã lưu quyết định');
      await shot(rev, 'review_rejected');
    }, rev);

    // ---------------- rework + appeal ----------------
    await step('Annotator sees the rejected job and can appeal', async () => {
      await ann.goto(`${BASE}/work`, { waitUntil: 'domcontentloaded' });
      await waitText(ann, 'bị trả lại');
      await clickByText(ann, 'Khiếu nại', 'button');
      await ann.waitForSelector('textarea');
      await ann.type('textarea', 'Tôi làm đúng theo guideline, xin xem lại.');
      await clickByText(ann, 'Gửi khiếu nại', 'button');
      await waitText(ann, 'Khiếu nại của tôi');
    }, ann);
    await step('PO sees the appeal and overturns it', async () => {
      await po.goto(`${BASE}/projects/${PROJECT}?tab=appeals`, { waitUntil: 'domcontentloaded' });
      await waitText(po, 'Xem và quyết định');
      await clickByText(po, 'Xem và quyết định', 'button');
      await po.waitForSelector('textarea');
      await po.type('textarea', 'Annotator đúng, chấp nhận job.');
      await clickByText(po, 'Lưu quyết định', 'button');
      await po.waitForFunction(() => !document.body.innerText.includes('Xem và quyết định'), { timeout: 120000 });
    }, po);
    await step('PO quality tab now has numbers', async () => {
      await po.goto(`${BASE}/projects/${PROJECT}?tab=quality`, { waitUntil: 'domcontentloaded' });
      await waitText(po, 'job đã được chấp nhận');
    }, po);

    // ---------------- misc screens ----------------
    await step('Annotator account page shows its own quality', async () => {
      await ann.goto(`${BASE}/account`, { waitUntil: 'domcontentloaded' });
      await waitText(ann, 'Chất lượng của tôi');
    }, ann);
    await step('Signing out sends the user back to the login page', async () => {
      await clickByText(ann, 'Đăng xuất', 'button');
      await ann.waitForFunction(() => location.pathname === '/login', { timeout: 60000 });
    }, ann);
    await step('An anonymous visit to a protected page redirects to login', async () => {
      await ann.goto(`${BASE}/projects`, { waitUntil: 'domcontentloaded' });
      await ann.waitForFunction(() => location.pathname === '/login', { timeout: 60000 });
    }, ann);
  } finally {
    await browser.close();
  }
  console.log(`\n${passed} checks passed`);
  const serious = problems.filter((p) => !p.startsWith('[') || true);
  if (serious.length) {
    console.log('PROBLEMS:');
    for (const p of serious) console.log(' -', p);
    process.exit(1);
  }
})().catch((e) => {
  console.error('E2E crashed:', e);
  process.exit(2);
});

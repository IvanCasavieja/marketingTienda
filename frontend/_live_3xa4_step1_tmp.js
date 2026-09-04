const { chromium } = require("playwright");

const BASE = "https://marketing-tienda.vercel.app";
const EMAIL = "claude-smoketest@local.test";
const PASSWORD = "ClaudeSmokeTest2026!";
const SCREENSHOT_DIR = "C:/Users/Usuario/AppData/Local/Temp/claude/c--Users-Usuario-MKTG-Platform/b1196b8c-1a35-4942-b434-7cfcda50aeb8/scratchpad";
const EXCEL_PATH = `${SCREENSHOT_DIR}/test_3xa4.xlsx`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1300 } });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));

  await page.goto(BASE + "/login", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  await page.locator('input[name="email"]').first().fill(EMAIL);
  await page.locator('input[type="password"]').first().fill(PASSWORD);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForTimeout(2500);

  await page.goto(BASE + "/materiales/cenefas?destino=rompe_precios", { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  await page.locator('input[type="file"][accept*="xlsx"]').first().setInputFiles(EXCEL_PATH);
  await page.waitForTimeout(1500);
  await page.locator('button:has-text("Elegir plantillas")').first().click();
  await page.waitForTimeout(1200);
  await page.locator('input[placeholder*="uscar" i]').first().fill("Rompe Precios-202608-3xA4");
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/x3_00_picker.png` });
  await page.locator('text=Rompe Precios-202608-3xA4').first().click();
  await page.waitForTimeout(1000);
  await page.locator('button:has-text("Generar")').first().click();
  await page.waitForTimeout(4000);
  for (let i = 0; i < 20; i++) {
    if (await page.locator("canvas").count() > 0) break;
    await page.waitForTimeout(2000);
  }
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/x3_01_preview_top.png`, fullPage: true });

  console.log("Canvas count:", await page.locator("canvas").count());
  console.log("Page errors:", JSON.stringify(pageErrors));
  await browser.close();
})().catch((e) => { console.error("ERROR:", e); process.exit(1); });

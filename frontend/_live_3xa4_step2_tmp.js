const { chromium } = require("playwright");

const BASE = "https://marketing-tienda.vercel.app";
const EMAIL = "claude-smoketest@local.test";
const PASSWORD = "ClaudeSmokeTest2026!";
const SCREENSHOT_DIR = "C:/Users/Usuario/AppData/Local/Temp/claude/c--Users-Usuario-MKTG-Platform/b1196b8c-1a35-4942-b434-7cfcda50aeb8/scratchpad";
const EXCEL_PATH = `${SCREENSHOT_DIR}/test_3xa4.xlsx`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 2600 } });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  page.on("console", (msg) => {
    const t = msg.text();
    if (t.includes("CLAUDE-DEBUG")) console.log("BROWSER:", t);
  });

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
  await page.locator('text=Rompe Precios-202608-3xA4').first().click();
  await page.waitForTimeout(1000);
  await page.locator('button:has-text("Generar")').first().click();
  await page.waitForTimeout(4000);
  for (let i = 0; i < 20; i++) {
    if (await page.locator("canvas").count() > 0) break;
    await page.waitForTimeout(2000);
  }
  await page.waitForTimeout(2000);

  // Click en "Coca Cola 1.5L" (descripcion de la banda 1), coordenadas leidas
  // del screenshot de x3_01_preview_top.png (viewport identico 1500x1300).
  const clickX = 723, clickY = 728;
  await page.mouse.click(clickX, clickY);
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/x3_02_selected_banda1.png` });

  // Arrastrar bien notoriamente: 120px a la derecha, 40 hacia abajo.
  await page.mouse.move(clickX, clickY);
  await page.mouse.down();
  await page.mouse.move(clickX + 120, clickY + 40, { steps: 15 });
  await page.mouse.up();
  await page.waitForTimeout(1200);

  // En vez de scrollear el contenedor interno (h-[560px], overflow-auto) y
  // arriesgar timing raro, se le saca el limite de alto por JS para que el
  // canvas ENTERO (912px) quede visible en una sola captura, sin ambiguedad
  // de scroll.
  await page.evaluate(() => {
    const stage = document.querySelector("canvas");
    let el = stage;
    for (let i = 0; i < 6 && el; i++) {
      const cs = getComputedStyle(el);
      if (cs.overflow === "auto" || cs.overflowY === "auto") {
        el.style.height = "auto";
        el.style.maxHeight = "none";
        el.style.overflow = "visible";
        break;
      }
      el = el.parentElement;
    }
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/x3_06_sin_scroll_completo.png`, fullPage: true });

  console.log("Page errors:", JSON.stringify(pageErrors));
  await browser.close();
})().catch((e) => { console.error("ERROR:", e); process.exit(1); });

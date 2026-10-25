import { test, expect, type Page } from "@playwright/test";

// Exercise the real React UI; only the native IPC boundary is replaced.
async function openEditor(page: Page, options = { failThumbs: false, failBoot: false }) {
  await page.addInitScript((initial) => {
    const audit = (window as any).__uiTest = {
      ...initial, failPreview: false, previewDelay: 10, thumbDelay: 0,
      activeThumbs: 0, maxActiveThumbs: 0, calls: [] as any[],
    };
    function png(width: number, height: number, original = false) {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d")!;
      context.fillStyle = original ? "#d59959" : "#738c65";
      context.fillRect(0, 0, width, height);
      context.fillStyle = "#253c59";
      context.fillRect(0, height / 2, width / 2, height / 2);
      return canvas.toDataURL("image/png").split(",")[1];
    }
    (window as any).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: any = {}) => {
        audit.calls.push({ command, ...args });
        const films = ["kodak_portra_400", "kodak_gold_200", "fuji_superia_400"];
        const papers = ["kodak_portra_endura", "kodak_supra_endura"];
        if (command === "sidecar_health") {
          if (audit.failBoot) throw new Error("Python unavailable");
          return { status: "ok", python: "3.13", protocol: 1 };
        }
        if (command === "sidecar_version") return { spektrafilm: "0.3.4", python: "3.13", protocol: 1 };
        if (command === "list_film_profiles") return { profiles: films.map(id => ({ id, name: id })) };
        if (command === "list_print_profiles") return { profiles: papers.map(id => ({ id, name: id })) };
        if (command === "stock_thumb") {
          audit.activeThumbs += 1;
          audit.maxActiveThumbs = Math.max(audit.maxActiveThumbs, audit.activeThumbs);
          try {
            await new Promise(resolve => setTimeout(resolve, audit.thumbDelay));
            if (audit.failThumbs) throw new Error("Thumbnail failed");
            return { ...args.params, mime: "image/png", png_base64: png(96, 48), cached: true };
          } finally {
            audit.activeThumbs -= 1;
          }
        }
        if (command === "run_preview") {
          await new Promise(resolve => setTimeout(resolve, audit.previewDelay));
          if (audit.failPreview) throw new Error("Python request timed out. Retry to start a fresh sidecar.");
          const params = args.params;
          return {
            ...params, width: params.max_size, height: params.max_size / 2,
            input_width: 6000, input_height: 3000, mime: "image/png",
            png_base64: png(params.max_size, params.max_size / 2),
            reference_png_base64: png(params.max_size, params.max_size / 2, true),
            elapsed_ms: 100, input_color_space: params.input_color_space ?? "sRGB",
          };
        }
        throw new Error(`Unexpected command: ${command}`);
      },
    };
  }, options);
  await page.goto("/");
  if (!options.failBoot) await expect(page.locator(".expose")).toBeEnabled();
}

async function expose(page: Page) {
  const before = await page.evaluate(() => (window as any).__uiTest.calls.filter((call: any) => call.command === "run_preview").length);
  await page.locator(".expose").click();
  await expect.poll(() => page.evaluate(() => (window as any).__uiTest.calls.filter((call: any) => call.command === "run_preview").length)).toBe(before + 1);
  await expect(page.locator(".expose")).toBeEnabled();
}

test("changing settings marks a print stale without changing its colors", async ({ page }) => {
  await openEditor(page);
  await expose(page);
  const image = page.locator(".frame > img");
  const source = await image.getAttribute("src");
  await page.getByRole("slider", { name: "EV", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator(".frame")).toHaveClass(/is-stale/);
  await expect(image).toHaveAttribute("src", source!);
  await expect(image).toHaveCSS("filter", "none");
  await expose(page);
  await expect(page.locator(".frame")).not.toHaveClass(/is-stale/);
});

test("original comparison works with Space, Enter, mouse and focus loss", async ({ page }) => {
  await openEditor(page);
  await expose(page);
  const hold = page.getByRole("button", { name: "Hold to compare original" });
  for (const key of ["Space", "Enter"]) {
    await hold.focus();
    await page.keyboard.down(key);
    await expect(hold).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.up(key);
    await expect(hold).toHaveAttribute("aria-pressed", "false");
  }
  await page.keyboard.down("Space");
  await page.getByRole("slider", { name: "EV", exact: true }).focus();
  await expect(hold).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.up("Space");
  await hold.hover();
  await page.mouse.down();
  await expect(hold).toHaveAttribute("aria-pressed", "true");
  await page.mouse.up();
  await expect(hold).toHaveAttribute("aria-pressed", "false");
  await hold.focus();
  await page.keyboard.down("Space");
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect(hold).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.up("Space");
});

test("file RGB space is sent to the renderer and path focus stays visible", async ({ page }) => {
  await openEditor(page);
  await page.getByRole("button", { name: "File", exact: true }).click();
  const path = page.getByRole("textbox", { name: "Path" });
  await path.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(path).toHaveCSS("outline-style", "solid");
  await path.fill("C:/photos/linear.exr");
  await page.getByRole("combobox", { name: "RGB space" }).selectOption("ACEScg");
  await expose(page);
  const request = await page.evaluate(() => (window as any).__uiTest.calls.filter((call: any) => call.command === "run_preview").at(-1).params);
  expect(request).toMatchObject({ source: "path", image_path: "C:/photos/linear.exr", input_color_space: "ACEScg", input_cctf_decoding: false, max_size: 512 });
  await page.getByRole("combobox", { name: "RGB space" }).selectOption("ProPhoto RGB");
  await expect(page.locator(".frame")).toHaveClass(/is-stale/);
});

test("failed thumbnails stop loading and both strips can retry", async ({ page }) => {
  await openEditor(page, { failThumbs: true, failBoot: false });
  await expect(page.locator(".thumb-error")).toHaveCount(5);
  await expect(page.locator(".swatch.pending")).toHaveCount(0);
  await page.evaluate(() => { (window as any).__uiTest.failThumbs = false; });
  await page.getByRole("button", { name: "Retry film thumbnails" }).click();
  await expect(page.locator(".strip.film .swatch img")).toHaveCount(3);
  await expect(page.locator(".strip.film .thumb-error")).toHaveCount(0);
  await page.getByRole("button", { name: "Retry paper thumbnails" }).click();
  await expect(page.locator(".strip.paper .swatch img")).toHaveCount(2);
  await expect(page.locator(".swatch.pending, .thumb-error")).toHaveCount(0);
});

test("scan requests a usable resolution with smooth display rendering", async ({ page }) => {
  await openEditor(page);
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await page.getByRole("button", { name: "1024", exact: true }).click();
  await expose(page);
  const request = await page.evaluate(() => (window as any).__uiTest.calls.filter((call: any) => call.command === "run_preview").at(-1).params);
  expect(request).toMatchObject({ render_mode: "scan", max_size: 1024 });
  await expect(page.locator(".frame > img")).toHaveCSS("image-rendering", "auto");
});

test("rapid stock changes do not queue obsolete native thumbnail requests", async ({ page }) => {
  await openEditor(page);
  await page.evaluate(() => { (window as any).__uiTest.thumbDelay = 2000; });
  await expect.poll(() => page.evaluate(() => (window as any).__uiTest.activeThumbs)).toBe(1);
  await page.locator('.strip.film [data-stock="kodak_gold_200"]').click();
  await page.waitForTimeout(230); // Allow each strip debounce to enqueue its refresh.
  await page.locator('.strip.film [data-stock="fuji_superia_400"]').click();
  await page.waitForTimeout(230);
  expect(await page.evaluate(() => (window as any).__uiTest.calls.filter((call: any) => call.command === "stock_thumb").length)).toBe(1);
  await page.evaluate(() => { (window as any).__uiTest.thumbDelay = 0; });
  await expect(page.locator('.strip [aria-busy="true"]')).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__uiTest.maxActiveThumbs)).toBe(1);
});

test("a failed request releases the UI and can be retried", async ({ page }) => {
  await openEditor(page);
  await page.evaluate(() => { (window as any).__uiTest.failPreview = true; });
  await expose(page);
  await expect(page.getByRole("alert")).toContainText("timed out");
  await page.evaluate(() => { (window as any).__uiTest.failPreview = false; });
  await expose(page);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".frame > img")).toBeVisible();
});

test("startup failure can reconnect without reloading the window", async ({ page }) => {
  await openEditor(page, { failThumbs: false, failBoot: true });
  await expect(page.getByRole("button", { name: "Reconnect" })).toBeVisible();
  await page.evaluate(() => { (window as any).__uiTest.failBoot = false; });
  await page.getByRole("button", { name: "Reconnect" }).click();
  await expect(page.locator(".expose")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Reconnect" })).toHaveCount(0);
});

test("minimum desktop window keeps the image and file controls accessible", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 720 });
  await openEditor(page);
  await page.getByRole("button", { name: "File", exact: true }).click();
  await page.getByRole("combobox", { name: "RGB space" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("combobox", { name: "RGB space" })).toBeInViewport();
  await expect(page.locator(".frame")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(1100);
});

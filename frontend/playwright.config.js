import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = path.dirname(fileURLToPath(import.meta.url));
const python = process.platform === "win32"
  ? `"${path.resolve(projectDir, "../backend/.venv/Scripts/python.exe")}"`
  : "python";
const backendScript = `"${path.resolve(projectDir, "../backend/run.py")}"`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:15173",
    trace: "retain-on-failure"
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${python} ${backendScript} --host 127.0.0.1 --port 18000`,
      url: "http://127.0.0.1:18000/api/health/ready",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ...process.env,
        NETTWIN_DATABASE_URL: "sqlite:///./e2e.db",
        NETTWIN_DISABLE_SCHEDULER: "1",
        NETTWIN_OPERATOR_API_KEY: "",
        NETTWIN_RELOAD: "0"
      }
    },
    {
      command: "npm run dev -- --port 15173",
      url: "http://127.0.0.1:15173",
      reuseExistingServer: false,
      timeout: 60_000,
      env: { ...process.env, VITE_API_URL: "http://127.0.0.1:18000" }
    }
  ]
});

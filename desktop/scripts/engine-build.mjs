// engine/.venv içindeki Python ile motoru paketler (bkz. engine/build.py).
import { spawnSync } from "node:child_process";
import { join } from "node:path";

const engineDir = join(import.meta.dirname, "..", "engine");
const python =
  process.env.BULUTBELGE_PYTHON ??
  (process.platform === "win32"
    ? join(engineDir, ".venv", "Scripts", "python.exe")
    : join(engineDir, ".venv", "bin", "python"));

const r = spawnSync(python, ["build.py"], { cwd: engineDir, stdio: "inherit" });
process.exit(r.status ?? 1);

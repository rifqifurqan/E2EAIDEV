// NFR-12: no outbound telemetry by default. Runs `next <args>` with Next.js telemetry forced off, whatever
// the caller's environment says. An operator who wants telemetry must edit this file on purpose.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

export function buildEnv(env) {
  return { ...env, NEXT_TELEMETRY_DISABLED: "1" };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const nextBin = createRequire(import.meta.url).resolve("next/dist/bin/next");
  const child = spawn(process.execPath, [nextBin, ...process.argv.slice(2)], {
    stdio: "inherit",
    env: buildEnv(process.env),
  });
  child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
}

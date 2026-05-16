#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

function parseArgs(argv) {
  const out = {};
  for (const arg of argv.slice(2)) {
    if (!arg.startsWith("--")) continue;
    const [k, v] = arg.replace(/^--/, "").split("=");
    out[k] = v ?? "true";
  }
  return out;
}

function nowStamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function parseServerArgs(outputDir) {
  if (process.env.MCP_SERVER_ARGS_JSON) {
    const parsed = JSON.parse(process.env.MCP_SERVER_ARGS_JSON);
    if (!Array.isArray(parsed)) {
      throw new Error("MCP_SERVER_ARGS_JSON must be a JSON array of strings.");
    }
    const args = parsed.map((v) => String(v));
    if (!args.includes("--output-dir")) {
      args.push("--output-dir", outputDir);
    }
    if (!args.includes("--save-session")) {
      args.push("--save-session");
    }
    if (!args.some((arg) => arg === "--caps=testing" || arg.startsWith("--caps="))) {
      args.push("--caps=testing");
    }
    return args;
  }

  return [
    "-y",
    "@playwright/mcp@latest",
    "--headless",
    "--isolated",
    "--caps=testing",
    "--output-dir",
    outputDir,
    "--save-session",
  ];
}

async function main() {
  const cli = parseArgs(process.argv);
  const state = (cli.state || process.env.GYM_STATE || "open").toLowerCase();
  if (!["open", "closed"].includes(state)) {
    throw new Error("Invalid state. Use --state=open or --state=closed.");
  }

  const baseURL = process.env.E2E_BASE_URL || "http://localhost:8501";
  const outputDir =
    process.env.MCP_OUTPUT_DIR ||
    path.resolve(process.cwd(), `mcp-artifacts/${state}-${nowStamp()}`);
  ensureDir(outputDir);
  const outputDirRelative = path.relative(process.cwd(), outputDir) || ".";

  const serverCommand = process.env.MCP_SERVER_COMMAND || "npx";
  const serverArgs = parseServerArgs(outputDir);

  const transport = new StdioClientTransport({
    command: serverCommand,
    args: serverArgs,
    cwd: process.cwd(),
    env: {
      ...process.env,
      PLAYWRIGHT_MCP_OUTPUT_DIR: outputDir,
    },
  });

  const client = new Client(
    {
      name: "theassembly-e2e-mcp-runner",
      version: "1.0.0",
    },
    {
      capabilities: {},
    }
  );

  const steps = [];

  async function callTool(name, args = {}) {
    const response = await client.callTool({ name, arguments: args });
    const text = (response.content || [])
      .filter((item) => item && item.type === "text" && typeof item.text === "string")
      .map((item) => item.text)
      .join("\n");

    steps.push({ name, args, isError: Boolean(response.isError), text });

    if (response.isError) {
      throw new Error(`Tool ${name} failed: ${text || "unknown error"}`);
    }

    return response;
  }

  async function verifyTextVisible(text, retries = 3) {
    let lastError;
    for (let i = 0; i < retries; i += 1) {
      try {
        await callTool("browser_verify_text_visible", { text });
        return;
      } catch (error) {
        lastError = error;
        await callTool("browser_wait_for", { time: 2 });
      }
    }
    throw lastError;
  }

  try {
    await client.connect(transport);

    const tools = await client.listTools();
    const names = (tools.tools || []).map((t) => t.name);
    for (const required of [
      "browser_navigate",
      "browser_wait_for",
      "browser_verify_text_visible",
      "browser_take_screenshot",
      "browser_snapshot",
    ]) {
      if (!names.includes(required)) {
        throw new Error(`Required MCP tool is unavailable: ${required}`);
      }
    }

    await callTool("browser_navigate", { url: baseURL });
    await callTool("browser_wait_for", { text: "TheAssembly" });
    await callTool("browser_wait_for", { time: 4 });

    // Core shared checks
    await verifyTextVisible("Athlete View");
    await verifyTextVisible("Joke of the Day");
    await verifyTextVisible("Gym Conversation Starter");


    if (state === "open") {
      await callTool("browser_wait_for", { text: "Today's Workout" });
      await verifyTextVisible("Today's Workout");
      await verifyTextVisible("WOD");
      await verifyTextVisible("Stimulus");
    } else {
      // Robust closed-state assertions
      // 1. Wait for "Today's Workout" and "WOD" to be gone
      await callTool("browser_wait_for", { textGone: "Today's Workout" });
      await callTool("browser_wait_for", { textGone: "WOD" });
      // 2. Assert closed-state messaging with tolerant fallback
      try {
        await verifyTextVisible("Next scheduled release");
      } catch {
        await verifyTextVisible("Garage Closed");
      }
      // 3. Keep a direct closed anchor as a final guard
      await verifyTextVisible("Garage Closed");
    }

    await callTool("browser_snapshot", {
      filename: path.join(outputDirRelative, `snapshot-${state}.md`),
    });
    await callTool("browser_take_screenshot", {
      type: "png",
      fullPage: true,
      filename: path.join(outputDirRelative, `pass-${state}.png`),
    });

    const resultPath = path.join(outputDir, "result.json");
    fs.writeFileSync(
      resultPath,
      JSON.stringify(
        {
          ok: true,
          state,
          baseURL,
          outputDir,
          steps,
        },
        null,
        2
      )
    );
    console.log(`MCP E2E passed for state=${state}. Artifacts: ${outputDir}`);
  } catch (error) {
    try {
      await callTool("browser_take_screenshot", {
        type: "png",
        fullPage: true,
        filename: path.join(outputDirRelative, `fail-${state}.png`),
      });
      await callTool("browser_snapshot", {
        filename: path.join(outputDirRelative, `fail-snapshot-${state}.md`),
      });
    } catch {
      // Best effort diagnostics only.
    }

    const resultPath = path.join(outputDir, "result.json");
    fs.writeFileSync(
      resultPath,
      JSON.stringify(
        {
          ok: false,
          state,
          baseURL,
          outputDir,
          error: String(error?.message || error),
          steps,
        },
        null,
        2
      )
    );

    console.error(`MCP E2E failed for state=${state}: ${error?.message || error}`);
    process.exitCode = 1;
  } finally {
    try {
      await client.callTool({ name: "browser_close", arguments: {} });
    } catch {
      // Ignore if browser is already gone.
    }

    try {
      await client.close();
    } catch {
      // Ignore transport shutdown issues.
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

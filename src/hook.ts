/**
 * Anti-Repeat-Errors Skill - Before Prompt Build Hook
 *
 * TypeScript hook handler that bridges to the Python injector.
 */

import type { PluginApi, BeforePromptBuildContext, HookResult } from "@openclaw/plugin-sdk";
import { spawn } from "child_process";
import * as path from "path";

/**
 * Injection result from Python injector
 */
interface InjectionResult {
  injected: boolean;
  rules_count: number;
  content?: string;
  matched_rules: string[];
  skipped_reason?: string;
  duration_ms: number;
  errors?: string[];
}

/**
 * Context passed to Python injector
 */
interface InjectorContext {
  session_key?: string;
  phase?: number;
  task_type?: string;
  recent_tools: string[];
  recent_files: string[];
  message_content?: string;
  project_dir?: string;
  workspace_dir?: string;
}

/**
 * Plugin configuration
 */
interface PluginConfig {
  enabled?: boolean;
  rulesDir?: string;
  logLevel?: "debug" | "info" | "warn" | "error";
  injectTimeout?: number;
  cacheEnabled?: boolean;
  cacheTtlSeconds?: number;
  guardrailEnabled?: boolean;
  guardrailTimeout?: number;
  guardrailRulesDir?: string;
}

/**
 * Register the before_prompt_build hook
 */
export function registerBeforePromptBuildHook(api: PluginApi, config: PluginConfig): void {
  const logger = api.logger;

  api.registerHook(
    "before_prompt_build",
    async (ctx: BeforePromptBuildContext): Promise<HookResult> => {
      const startTime = Date.now();

      try {
        // Check if injection is enabled
        if (config.enabled === false) {
          logger.debug("Injection disabled by config");
          return { continue: true };
        }

        // Build injection context
        const injectContext = buildInjectorContext(ctx);

        // Call Python injector
        const result = await callPythonInjector(injectContext, config, logger);

        // Handle result
        if (result.injected && result.content) {
          logger.info(
            `Injected ${result.rules_count} rules: ${result.matched_rules.join(", ")} (${result.duration_ms}ms)`
          );

          // Prepend to context
          ctx.prependContext = (ctx.prependContext || "") + "\n" + result.content;
        } else {
          logger.debug(`No injection: ${result.skipped_reason} (${result.duration_ms}ms)`);
        }

        // Record metrics (if available)
        recordInjectionMetric(result, startTime, api);

        return { continue: true };
      } catch (error) {
        logger.error(`Injection failed: ${error}`);
        // Don't block the agent flow on injection failure
        return { continue: true };
      }
    },
    {
      name: "anti-repeat-errors.before_prompt_build",
      description: "Injects proactive rules before prompt is built",
      priority: 100, // High priority to ensure early injection
    }
  );

  logger.info("Registered before_prompt_build hook");
}

/**
 * Build context for the Python injector
 */
function buildInjectorContext(ctx: BeforePromptBuildContext): InjectorContext {
  return {
    session_key: ctx.sessionKey,
    phase: getCurrentPhase(ctx),
    task_type: inferTaskType(ctx),
    recent_tools: getRecentTools(ctx),
    recent_files: getRecentFiles(ctx),
    message_content: getLastUserMessage(ctx),
    project_dir: getProjectDir(ctx),
    workspace_dir: getWorkspaceDir(ctx),
  };
}

/**
 * Get current phase from project state
 */
function getCurrentPhase(ctx: BeforePromptBuildContext): number | undefined {
  // Try to get phase from project state
  if (ctx.projectState?.phase) {
    return ctx.projectState.phase;
  }

  // Try to parse from environment
  const phaseEnv = process.env.ANTI_REPEAT_ERRORS_PHASE;
  if (phaseEnv) {
    const phase = parseInt(phaseEnv, 10);
    if (!isNaN(phase)) {
      return phase;
    }
  }

  return undefined;
}

/**
 * Infer task type from context
 */
function inferTaskType(ctx: BeforePromptBuildContext): string | undefined {
  // Check explicit task type
  if (ctx.taskType) {
    return ctx.taskType;
  }

  // Infer from recent tools
  const tools = ctx.sessionHistory?.recentTools || [];
  if (tools.includes("write") || tools.includes("edit")) {
    return "coding";
  }
  if (tools.includes("exec")) {
    return "shell";
  }
  if (tools.includes("read")) {
    return "review";
  }

  // Infer from message content
  const message = getLastUserMessage(ctx)?.toLowerCase() || "";
  if (message.includes("implement") || message.includes("fix") || message.includes("create")) {
    return "coding";
  }
  if (message.includes("review") || message.includes("check") || message.includes("analyze")) {
    return "review";
  }

  return undefined;
}

/**
 * Get recent tools from session history
 */
function getRecentTools(ctx: BeforePromptBuildContext): string[] {
  return ctx.sessionHistory?.recentTools || [];
}

/**
 * Get recent files from session history
 */
function getRecentFiles(ctx: BeforePromptBuildContext): string[] {
  return ctx.sessionHistory?.recentFiles || [];
}

/**
 * Get last user message
 */
function getLastUserMessage(ctx: BeforePromptBuildContext): string | undefined {
  const messages = ctx.messages || [];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      return messages[i].content;
    }
  }
  return undefined;
}

/**
 * Get project directory
 */
function getProjectDir(ctx: BeforePromptBuildContext): string | undefined {
  return ctx.projectDir || process.env.PROJECT_DIR;
}

/**
 * Get workspace directory
 */
function getWorkspaceDir(ctx: BeforePromptBuildContext): string | undefined {
  return ctx.workspaceDir || process.env.OPENCLAW_WORKSPACE;
}

/**
 * Call Python injector via CLI
 */
async function callPythonInjector(
  context: InjectorContext,
  config: PluginConfig,
  logger: any
): Promise<InjectionResult> {
  const scriptPath = path.join(__dirname, "injector_cli.py");

  // Build config for Python
  const pythonConfig = {
    enabled: config.enabled !== false,
    rules_dir: config.rulesDir || "~/.openclaw/skills/anti-repeat-errors/rules",
    log_level: config.logLevel || "info",
    inject_timeout_ms: config.injectTimeout || 1000,
    cache_enabled: config.cacheEnabled !== false,
    cache_ttl_seconds: config.cacheTtlSeconds || 300,
  };

  return new Promise((resolve, reject) => {
    const timeout = config.injectTimeout || 1000;
    let resolved = false;

    const proc = spawn("python3", [
      scriptPath,
      "--context",
      JSON.stringify(context),
      "--config",
      JSON.stringify(pythonConfig),
    ]);

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
      // Log Python debug output
      if (config.logLevel === "debug") {
        logger.debug(`[Python] ${data.toString().trim()}`);
      }
    });

    proc.on("close", (code) => {
      if (resolved) return;
      resolved = true;

      if (code === 0) {
        try {
          const result = JSON.parse(stdout.trim()) as InjectionResult;
          resolve(result);
        } catch (e) {
          logger.error(`Failed to parse injector output: ${stdout}`);
          resolve({
            injected: false,
            rules_count: 0,
            matched_rules: [],
            skipped_reason: `Parse error: ${e}`,
            duration_ms: 0,
            errors: [String(e)],
          });
        }
      } else {
        logger.error(`Injector failed with code ${code}: ${stderr}`);
        resolve({
          injected: false,
          rules_count: 0,
          matched_rules: [],
          skipped_reason: `Exit code ${code}`,
          duration_ms: 0,
          errors: [stderr],
        });
      }
    });

    proc.on("error", (error) => {
      if (resolved) return;
      resolved = true;
      logger.error(`Failed to spawn injector: ${error}`);
      resolve({
        injected: false,
        rules_count: 0,
        matched_rules: [],
        skipped_reason: `Spawn error: ${error}`,
        duration_ms: 0,
        errors: [String(error)],
      });
    });

    // Timeout handling
    setTimeout(() => {
      if (resolved) return;
      resolved = true;
      proc.kill();
      logger.warn(`Injector timeout after ${timeout}ms`);
      resolve({
        injected: false,
        rules_count: 0,
        matched_rules: [],
        skipped_reason: "Timeout",
        duration_ms: timeout,
        errors: ["Timeout"],
      });
    }, timeout);
  });
}

/**
 * Record injection metrics
 */
function recordInjectionMetric(result: InjectionResult, startTime: number, api: PluginApi): void {
  // If metrics API is available, record
  if (api.metrics) {
    api.metrics.record("anti_repeat_errors_injection", {
      injected: result.injected,
      rules_count: result.rules_count,
      duration_ms: result.duration_ms,
      matched_rules: result.matched_rules,
    });
  }
}

// Import before_tool_call hook
import { registerBeforeToolCallHook } from "./guardrail_hook";

/**
 * Register all hooks (before_prompt_build and before_tool_call)
 */
export function registerAllHooks(api: PluginApi, config: PluginConfig): void {
  // Register before_prompt_build hook
  registerBeforePromptBuildHook(api, config);
  
  // Register before_tool_call hook (if enabled)
  if (config.guardrailEnabled !== false) {
    registerBeforeToolCallHook(api, config);
  } else {
    api.logger.info("[anti-repeat-errors] before_tool_call hook disabled by config");
  }
}

// Export for plugin entry
export default registerBeforePromptBuildHook;
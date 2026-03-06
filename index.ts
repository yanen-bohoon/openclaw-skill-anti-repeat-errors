/**
 * Anti-Repeat-Errors Skill - Plugin Entry Point
 *
 * Registers before_prompt_build and before_tool_call hooks.
 */

import type { PluginApi } from "@openclaw/plugin-sdk";
import { registerAllHooks } from "./src/hook";

/**
 * Plugin configuration interface
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
 * Plugin registration function
 */
export default function register(api: PluginApi): void {
  // Get config from plugin settings
  const config: PluginConfig = api.config.plugins?.entries?.["anti-repeat-errors"]?.config || {};
  
  if (config.enabled === false) {
    api.logger.info("[anti-repeat-errors] All hooks disabled by config");
    return;
  }
  
  api.logger.info("[anti-repeat-errors] Registering hooks");
  registerAllHooks(api, config);
}

/**
 * Plugin metadata
 */
export const id = "anti-repeat-errors";
export const name = "Anti-Repeat-Errors";
export const version = "0.2.0";
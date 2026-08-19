/**
 * completeTask prompt 生成器
 * 負責將模板和參數組合成最終的 prompt
 * completeTask prompt generator
 * Responsible for combining templates and parameters into the final prompt
 */

import {
  loadPrompt,
  generatePrompt,
  loadPromptFromTemplate,
} from "../loader.js";
import { Task } from "../../types/index.js";

/**
 * completeTask prompt 參數介面
 * completeTask prompt parameter interface
 */
export interface CompleteTaskPromptParams {
  task: Task;
  completionTime: string;
}

/**
 * 獲取 completeTask 的完整 prompt
 * Get the complete prompt for completeTask
 * @param params prompt 參數
 * @param params prompt parameters
 * @returns 生成的 prompt
 * @returns generated prompt
 */
export async function getCompleteTaskPrompt(
  params: CompleteTaskPromptParams
): Promise<string> {
  const { task, completionTime } = params;

  const indexTemplate = await loadPromptFromTemplate("completeTask/index.md");

  // 開始構建基本 prompt
  // Start building the basic prompt
  let prompt = generatePrompt(indexTemplate, {
    name: task.name,
    id: task.id,
    completionTime: completionTime,
  });

  // 載入可能的自定義 prompt
  // Load possible custom prompt
  return loadPrompt(prompt, "COMPLETE_TASK");
}

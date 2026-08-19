/**
 * deleteTask prompt 生成器
 * 負責將模板和參數組合成最終的 prompt
 * deleteTask prompt generator
 * Responsible for combining templates and parameters into the final prompt
 */

import {
  loadPrompt,
  generatePrompt,
  loadPromptFromTemplate,
} from "../loader.js";
import { Task } from "../../types/index.js";

/**
 * deleteTask prompt 參數介面
 * deleteTask prompt parameter interface
 */
export interface DeleteTaskPromptParams {
  taskId: string;
  task?: Task;
  success?: boolean;
  message?: string;
  isTaskCompleted?: boolean;
}

/**
 * 獲取 deleteTask 的完整 prompt
 * Get the complete prompt for deleteTask
 * @param params prompt 參數
 * @param params prompt parameters
 * @returns 生成的 prompt
 * @returns generated prompt
 */
export async function getDeleteTaskPrompt(
  params: DeleteTaskPromptParams
): Promise<string> {
  const { taskId, task, success, message, isTaskCompleted } = params;

  // 處理任務不存在的情況
  // Handle case when task does not exist
  if (!task) {
    const notFoundTemplate = await loadPromptFromTemplate(
      "deleteTask/notFound.md"
    );
    return generatePrompt(notFoundTemplate, {
      taskId,
    });
  }

  // 處理任務已完成的情況
  // Handle case when task is already completed
  if (isTaskCompleted) {
    const completedTemplate = await loadPromptFromTemplate(
      "deleteTask/completed.md"
    );
    return generatePrompt(completedTemplate, {
      taskId: task.id,
      taskName: task.name,
    });
  }

  // 處理刪除成功或失敗的情況
  // Handle successful or failed deletion cases
  const responseTitle = success ? "Success" : "Failure";
  const indexTemplate = await loadPromptFromTemplate("deleteTask/index.md");
  const prompt = generatePrompt(indexTemplate, {
    responseTitle,
    message,
  });

  // 載入可能的自定義 prompt
  // Load possible custom prompt
  return loadPrompt(prompt, "DELETE_TASK");
}

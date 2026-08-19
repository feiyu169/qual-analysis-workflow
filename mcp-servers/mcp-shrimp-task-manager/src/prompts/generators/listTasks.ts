/**
 * listTasks prompt 生成器
 * listTasks prompt generator
 * 負責將模板和參數組合成最終的 prompt
 * Responsible for combining templates and parameters into the final prompt
 */

import {
  loadPrompt,
  generatePrompt,
  loadPromptFromTemplate,
} from "../loader.js";
import { Task, TaskStatus } from "../../types/index.js";

/**
 * listTasks prompt 參數介面
 * listTasks prompt parameters interface
 */
export interface ListTasksPromptParams {
  status: string;
  tasks: Record<string, Task[]>;
  allTasks: Task[];
}

/**
 * 獲取 listTasks 的完整 prompt
 * Get the complete prompt for listTasks
 * @param params prompt 參數
 * @param params prompt parameters
 * @returns 生成的 prompt
 * @returns generated prompt
 */
export async function getListTasksPrompt(
  params: ListTasksPromptParams
): Promise<string> {
  const { status, tasks, allTasks } = params;

  // 如果沒有任務，顯示通知
  // If there are no tasks, show notification
  if (allTasks.length === 0) {
    const notFoundTemplate = await loadPromptFromTemplate(
      "listTasks/notFound.md"
    );
    const statusText = status === "all" ? "任何" : `任何 ${status} 的`;
    // Set status text: "any" for all, or "any [status]" for specific status
    return generatePrompt(notFoundTemplate, {
      statusText: statusText,
    });
  }

  // 獲取所有狀態的計數
  // Get counts for all statuses
  const statusCounts = Object.values(TaskStatus)
    .map((statusType) => {
      const count = tasks[statusType]?.length || 0;
      return `- **${statusType}**: ${count} 個任務`;
      // Return formatted string showing task count for each status
    })
    .join("\n");

  let filterStatus = "all";
  switch (status) {
    case "pending":
      filterStatus = TaskStatus.PENDING;
      break;
    case "in_progress":
      filterStatus = TaskStatus.IN_PROGRESS;
      break;
    case "completed":
      filterStatus = TaskStatus.COMPLETED;
      break;
  }

  let taskDetails = "";
  let taskDetailsTemplate = await loadPromptFromTemplate(
    "listTasks/taskDetails.md"
  );
  // 添加每個狀態下的詳細任務
  // Add detailed tasks under each status
  for (const statusType of Object.values(TaskStatus)) {
    const tasksWithStatus = tasks[statusType] || [];
    if (
      tasksWithStatus.length > 0 &&
      (filterStatus === "all" || filterStatus === statusType)
    ) {
      for (const task of tasksWithStatus) {
        let dependencies = "沒有依賴";
        // Default dependency text when no dependencies exist
        if (task.dependencies && task.dependencies.length > 0) {
          dependencies = task.dependencies
            .map((d) => `\`${d.taskId}\``)
            .join(", ");
        }
        taskDetails += generatePrompt(taskDetailsTemplate, {
          name: task.name,
          id: task.id,
          description: task.description,
          createAt: task.createdAt,
          complatedSummary:
            (task.summary || "").substring(0, 100) +
            ((task.summary || "").length > 100 ? "..." : ""),
          dependencies: dependencies,
          complatedAt: task.completedAt,
        });
      }
    }
  }

  const indexTemplate = await loadPromptFromTemplate("listTasks/index.md");
  let prompt = generatePrompt(indexTemplate, {
    statusCount: statusCounts,
    taskDetailsTemplate: taskDetails,
  });

  // 載入可能的自定義 prompt
  // Load possible custom prompt
  return loadPrompt(prompt, "LIST_TASKS");
}

import { z } from "zod";
import { searchTasksWithCommand } from "../../models/taskModel.js";
import { getGetTaskDetailPrompt } from "../../prompts/index.js";

// 取得完整任務詳情的參數
// Get parameters for full task details
export const getTaskDetailSchema = z.object({
  taskId: z
    .string()
    .min(1, {
      message: "任務ID不能為空，請提供有效的任務ID",
      // Task ID cannot be empty, please provide a valid task ID
    })
    .describe("欲檢視詳情的任務ID"),
    // Task ID for which details are to be viewed
});

// 取得任務完整詳情
// Get complete task details
export async function getTaskDetail({
  taskId,
}: z.infer<typeof getTaskDetailSchema>) {
  try {
    // 使用 searchTasksWithCommand 替代 getTaskById，實現記憶區任務搜索
    // Use searchTasksWithCommand instead of getTaskById to implement memory area task search
    // 設置 isId 為 true，表示按 ID 搜索；頁碼為 1，每頁大小為 1
    // Set isId to true to indicate search by ID; page number is 1, page size is 1
    const result = await searchTasksWithCommand(taskId, true, 1, 1);

    // 檢查是否找到任務
    // Check if task was found
    if (result.tasks.length === 0) {
      return {
        content: [
          {
            type: "text" as const,
            text: `## 錯誤\n\n找不到ID為 \`${taskId}\` 的任務。請確認任務ID是否正確。`,
            // Error: Cannot find task with ID `${taskId}`. Please confirm the task ID is correct.
          },
        ],
        isError: true,
      };
    }

    // 獲取找到的任務（第一個也是唯一的一個）
    // Get the found task (the first and only one)
    const task = result.tasks[0];

    // 使用prompt生成器獲取最終prompt
    // Use prompt generator to get the final prompt
    const prompt = await getGetTaskDetailPrompt({
      taskId,
      task,
    });

    return {
      content: [
        {
          type: "text" as const,
          text: prompt,
        },
      ],
    };
  } catch (error) {
    // 使用prompt生成器獲取錯誤訊息
    // Use prompt generator to get error message
    const errorPrompt = await getGetTaskDetailPrompt({
      taskId,
      error: error instanceof Error ? error.message : String(error),
    });

    return {
      content: [
        {
          type: "text" as const,
          text: errorPrompt,
        },
      ],
    };
  }
}

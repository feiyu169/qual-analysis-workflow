import { z } from "zod";
import { UUID_V4_REGEX } from "../../utils/regex.js";
import {
  getTaskById,
  deleteTask as modelDeleteTask,
} from "../../models/taskModel.js";
import { TaskStatus } from "../../types/index.js";
import { getDeleteTaskPrompt } from "../../prompts/index.js";

// 刪除任務工具
// Delete task tool
export const deleteTaskSchema = z.object({
  taskId: z
    .string()
    .regex(UUID_V4_REGEX, {
      message: "任務ID格式無效，請提供有效的UUID v4格式",
      // Task ID format is invalid, please provide a valid UUID v4 format
    })
    .describe("待刪除任務的唯一標識符，必須是系統中存在且未完成的任務ID"),
    // Unique identifier of the task to be deleted, must be an existing and incomplete task ID in the system
});

export async function deleteTask({ taskId }: z.infer<typeof deleteTaskSchema>) {
  const task = await getTaskById(taskId);

  if (!task) {
    return {
      content: [
        {
          type: "text" as const,
          text: await getDeleteTaskPrompt({ taskId }),
        },
      ],
      isError: true,
    };
  }

  if (task.status === TaskStatus.COMPLETED) {
    return {
      content: [
        {
          type: "text" as const,
          text: await getDeleteTaskPrompt({
            taskId,
            task,
            isTaskCompleted: true,
          }),
        },
      ],
      isError: true,
    };
  }

  const result = await modelDeleteTask(taskId);

  return {
    content: [
      {
        type: "text" as const,
        text: await getDeleteTaskPrompt({
          taskId,
          task,
          success: result.success,
          message: result.message,
        }),
      },
    ],
    isError: !result.success,
  };
}

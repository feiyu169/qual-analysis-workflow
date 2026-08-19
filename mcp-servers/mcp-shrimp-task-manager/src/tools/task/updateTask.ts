import { z } from "zod";
import { UUID_V4_REGEX } from "../../utils/regex.js";
import {
  getTaskById,
  updateTaskContent as modelUpdateTaskContent,
} from "../../models/taskModel.js";
import { RelatedFileType } from "../../types/index.js";
import { getUpdateTaskContentPrompt } from "../../prompts/index.js";

// 更新任務內容工具
// Update task content tool
export const updateTaskContentSchema = z.object({
  taskId: z
    .string()
    .regex(UUID_V4_REGEX, {
      message: "任務ID格式無效，請提供有效的UUID v4格式",
      // Task ID format is invalid, please provide a valid UUID v4 format
    })
    .describe("待更新任務的唯一標識符，必須是系統中存在且未完成的任務ID"),
    // Unique identifier of the task to be updated, must be a task ID that exists in the system and is not completed
  name: z.string().optional().describe("任務的新名稱（選填）"),
  // New name of the task (optional)
  description: z.string().optional().describe("任務的新描述內容（選填）"),
  // New description content of the task (optional)
  notes: z.string().optional().describe("任務的新補充說明（選填）"),
  // New additional notes of the task (optional)
  dependencies: z
    .array(z.string())
    .optional()
    .describe("任務的新依賴關係（選填）"),
    // New dependency relationships of the task (optional)
  relatedFiles: z
    .array(
      z.object({
        path: z
          .string()
          .min(1, { message: "文件路徑不能為空，請提供有效的文件路徑" })
          // File path cannot be empty, please provide a valid file path
          .describe("文件路徑，可以是相對於項目根目錄的路徑或絕對路徑"),
          // File path, can be a path relative to the project root directory or an absolute path
        type: z
          .nativeEnum(RelatedFileType)
          .describe(
            "文件與任務的關係類型 (TO_MODIFY, REFERENCE, CREATE, DEPENDENCY, OTHER)"
            // File relationship type with task (TO_MODIFY, REFERENCE, CREATE, DEPENDENCY, OTHER)
          ),
        description: z.string().optional().describe("文件的補充描述（選填）"),
        // Additional description of the file (optional)
        lineStart: z
          .number()
          .int()
          .positive()
          .optional()
          .describe("相關代碼區塊的起始行（選填）"),
          // Starting line of the related code block (optional)
        lineEnd: z
          .number()
          .int()
          .positive()
          .optional()
          .describe("相關代碼區塊的結束行（選填）"),
          // Ending line of the related code block (optional)
      })
    )
    .optional()
    .describe(
      "與任務相關的文件列表，用於記錄與任務相關的代碼文件、參考資料、要建立的檔案等（選填）"
      // List of files related to the task, used to record code files, reference materials, files to be created, etc. related to the task (optional)
    ),
  implementationGuide: z
    .string()
    .optional()
    .describe("任務的新實現指南（選填）"),
    // New implementation guide for the task (optional)
  verificationCriteria: z
    .string()
    .optional()
    .describe("任務的新驗證標準（選填）"),
    // New verification criteria for the task (optional)
});

export async function updateTaskContent({
  taskId,
  name,
  description,
  notes,
  relatedFiles,
  dependencies,
  implementationGuide,
  verificationCriteria,
}: z.infer<typeof updateTaskContentSchema>) {
  if (relatedFiles) {
    for (const file of relatedFiles) {
      if (
        (file.lineStart && !file.lineEnd) ||
        (!file.lineStart && file.lineEnd) ||
        (file.lineStart && file.lineEnd && file.lineStart > file.lineEnd)
      ) {
        return {
          content: [
            {
              type: "text" as const,
              text: await getUpdateTaskContentPrompt({
                taskId,
                validationError:
                  "行號設置無效：必須同時設置起始行和結束行，且起始行必須小於結束行",
                  // Invalid line number settings: start line and end line must be set simultaneously, and start line must be less than end line
              }),
            },
          ],
        };
      }
    }
  }

  if (
    !(
      name ||
      description ||
      notes ||
      dependencies ||
      implementationGuide ||
      verificationCriteria ||
      relatedFiles
    )
  ) {
    return {
      content: [
        {
          type: "text" as const,
          text: await getUpdateTaskContentPrompt({
            taskId,
            emptyUpdate: true,
          }),
        },
      ],
    };
  }

  // 獲取任務以檢查它是否存在
  // Get task to check if it exists
  const task = await getTaskById(taskId);

  if (!task) {
    return {
      content: [
        {
          type: "text" as const,
          text: await getUpdateTaskContentPrompt({
            taskId,
          }),
        },
      ],
      isError: true,
    };
  }

  // 記錄要更新的任務和內容
  // Record the task and content to be updated
  let updateSummary = `準備更新任務：${task.name} (ID: ${task.id})`;
  // Preparing to update task: ${task.name} (ID: ${task.id})
  if (name) updateSummary += `，新名稱：${name}`;
  // , new name: ${name}
  if (description) updateSummary += `，更新描述`;
  // , update description
  if (notes) updateSummary += `，更新注記`;
  // , update notes
  if (relatedFiles)
    updateSummary += `，更新相關文件 (${relatedFiles.length} 個)`;
    // , update related files (${relatedFiles.length} files)
  if (dependencies)
    updateSummary += `，更新依賴關係 (${dependencies.length} 個)`;
    // , update dependencies (${dependencies.length} items)
  if (implementationGuide) updateSummary += `，更新實現指南`;
  // , update implementation guide
  if (verificationCriteria) updateSummary += `，更新驗證標準`;
  // , update verification criteria

  // 執行更新操作
  // Execute update operation
  const result = await modelUpdateTaskContent(taskId, {
    name,
    description,
    notes,
    relatedFiles,
    dependencies,
    implementationGuide,
    verificationCriteria,
  });

  return {
    content: [
      {
        type: "text" as const,
        text: await getUpdateTaskContentPrompt({
          taskId,
          task,
          success: result.success,
          message: result.message,
          updatedTask: result.task,
        }),
      },
    ],
    isError: !result.success,
  };
}

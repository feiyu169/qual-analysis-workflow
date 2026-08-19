/**
 * updateTaskContent prompt 生成器
 * updateTaskContent prompt generator
 * 負責將模板和參數組合成最終的 prompt
 * Responsible for combining templates and parameters into the final prompt
 */

import {
  loadPrompt,
  generatePrompt,
  loadPromptFromTemplate,
} from "../loader.js";
import { Task, RelatedFile } from "../../types/index.js";

/**
 * updateTaskContent prompt 參數介面
 * updateTaskContent prompt parameter interface
 */
export interface UpdateTaskContentPromptParams {
  taskId: string;
  task?: Task;
  success?: boolean;
  message?: string;
  validationError?: string;
  emptyUpdate?: boolean;
  updatedTask?: Task;
}

/**
 * 獲取 updateTaskContent 的完整 prompt
 * Get the complete updateTaskContent prompt
 * @param params prompt 參數
 * @param params prompt parameters
 * @returns 生成的 prompt
 * @returns generated prompt
 */
export async function getUpdateTaskContentPrompt(
  params: UpdateTaskContentPromptParams
): Promise<string> {
  const {
    taskId,
    task,
    success,
    message,
    validationError,
    emptyUpdate,
    updatedTask,
  } = params;

  // 處理任務不存在的情況
  // Handle case when task doesn't exist
  if (!task) {
    const notFoundTemplate = await loadPromptFromTemplate(
      "updateTaskContent/notFound.md"
    );
    return generatePrompt(notFoundTemplate, {
      taskId,
    });
  }

  // 處理驗證錯誤的情況
  // Handle validation error case
  if (validationError) {
    const validationTemplate = await loadPromptFromTemplate(
      "updateTaskContent/validation.md"
    );
    return generatePrompt(validationTemplate, {
      error: validationError,
    });
  }

  // 處理空更新的情況
  // Handle empty update case
  if (emptyUpdate) {
    const emptyUpdateTemplate = await loadPromptFromTemplate(
      "updateTaskContent/emptyUpdate.md"
    );
    return generatePrompt(emptyUpdateTemplate, {});
  }

  // 處理更新成功或失敗的情況
  // Handle successful or failed update case
  const responseTitle = success ? "Success" : "Failure";
  let content = message || "";

  // 更新成功且有更新後的任務詳情
  // Successful update with updated task details
  if (success && updatedTask) {
    const successTemplate = await loadPromptFromTemplate(
      "updateTaskContent/success.md"
    );

    // 編合相關文件信息
    // Compile related file information
    let filesContent = "";
    if (updatedTask.relatedFiles && updatedTask.relatedFiles.length > 0) {
      const fileDetailsTemplate = await loadPromptFromTemplate(
        "updateTaskContent/fileDetails.md"
      );

      // 按文件類型分組
      // Group by file type
      const filesByType = updatedTask.relatedFiles.reduce((acc, file) => {
        if (!acc[file.type]) {
          acc[file.type] = [];
        }
        acc[file.type].push(file);
        return acc;
      }, {} as Record<string, RelatedFile[]>);

      // 為每種文件類型生成內容
      // Generate content for each file type
      for (const [type, files] of Object.entries(filesByType)) {
        const filesList = files.map((file) => `\`${file.path}\``).join(", ");
        filesContent += generatePrompt(fileDetailsTemplate, {
          fileType: type,
          fileCount: files.length,
          filesList,
        });
      }
    }

    // 處理任務備註
    // Process task notes
    const taskNotesPrefix = "- **Notes:** ";
    const taskNotes = updatedTask.notes
      ? `${taskNotesPrefix}${
          updatedTask.notes.length > 100
            ? `${updatedTask.notes.substring(0, 100)}...`
            : updatedTask.notes
        }\n`
      : "";

    // 生成成功更新的詳細信息
    // Generate detailed information for successful update
    content += generatePrompt(successTemplate, {
      taskName: updatedTask.name,
      taskDescription:
        updatedTask.description.length > 100
          ? `${updatedTask.description.substring(0, 100)}...`
          : updatedTask.description,
      taskNotes: taskNotes,
      taskStatus: updatedTask.status,
      taskUpdatedAt: new Date(updatedTask.updatedAt).toISOString(),
      filesContent,
    });
  }

  const indexTemplate = await loadPromptFromTemplate(
    "updateTaskContent/index.md"
  );
  const prompt = generatePrompt(indexTemplate, {
    responseTitle,
    message: content,
  });

  // 載入可能的自定義 prompt
  // Load possible custom prompt
  return loadPrompt(prompt, "UPDATE_TASK_CONTENT");
}

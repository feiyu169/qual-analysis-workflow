import { RelatedFile, RelatedFileType } from "../types/index.js";

/**
 * 生成任務相關文件的內容摘要
 * Generate a content summary of task-related files
 *
 * 此函數根據提供的 RelatedFile 物件列表，生成文件的摘要信息，而不實際讀取檔案內容。
 * This function generates file summary information based on the provided RelatedFile object list without actually reading file contents.
 * 這是一個輕量級的實現，僅基於檔案元數據（如路徑、類型、描述等）生成格式化的摘要，
 * This is a lightweight implementation that generates formatted summaries based only on file metadata (such as paths, types, descriptions, etc.),
 * 適用於需要提供文件上下文信息但不需要訪問實際檔案內容的情境。
 * suitable for scenarios that need to provide file context information but don't need to access actual file contents.
 *
 * @param relatedFiles 相關文件列表 - RelatedFile 物件數組，包含文件的路徑、類型、描述等資訊
 * @param relatedFiles Related file list - Array of RelatedFile objects containing file paths, types, descriptions, and other information
 * @param maxTotalLength 摘要內容的最大總長度 - 控制生成摘要的總字符數，避免過大的返回內容
 * @param maxTotalLength Maximum total length of summary content - Controls the total character count of generated summaries to avoid overly large return content
 * @returns 包含兩個字段的物件：
 * @returns Object containing two fields:
 *   - content: 詳細的文件資訊，包含每個檔案的基本資訊和提示訊息
 *   - content: Detailed file information, including basic information and hint messages for each file
 *   - summary: 簡潔的檔案列表概覽，適合快速瀏覽
 *   - summary: Concise file list overview, suitable for quick browsing
 */
export async function loadTaskRelatedFiles(
  relatedFiles: RelatedFile[],
  maxTotalLength: number = 15000 // 控制生成內容的總長度
  // Control the total length of generated content
): Promise<{ content: string; summary: string }> {
  if (!relatedFiles || relatedFiles.length === 0) {
    return {
      content: "",
      summary: "無相關文件", // No related files
    };
  }

  let totalContent = "";
  let filesSummary = `## 相關文件內容摘要 (共 ${relatedFiles.length} 個文件)\n\n`;
  // Related file content summary (total of ${relatedFiles.length} files)
  let totalLength = 0;

  // 按文件類型優先級排序（首先處理待修改的文件）
  // Sort by file type priority (process files to be modified first)
  const priorityOrder: Record<RelatedFileType, number> = {
    [RelatedFileType.TO_MODIFY]: 1,
    [RelatedFileType.REFERENCE]: 2,
    [RelatedFileType.DEPENDENCY]: 3,
    [RelatedFileType.CREATE]: 4,
    [RelatedFileType.OTHER]: 5,
  };

  const sortedFiles = [...relatedFiles].sort(
    (a, b) => priorityOrder[a.type] - priorityOrder[b.type]
  );

  // 處理每個文件
  // Process each file
  for (const file of sortedFiles) {
    if (totalLength >= maxTotalLength) {
      filesSummary += `\n### 已達到上下文長度限制，部分文件未載入\n`;
      // Context length limit reached, some files not loaded
      break;
    }

    // 生成文件基本資訊
    // Generate basic file information
    const fileInfo = generateFileInfo(file);

    // 添加到總內容
    // Add to total content
    const fileHeader = `\n### ${file.type}: ${file.path}${
      file.description ? ` - ${file.description}` : ""
    }${
      file.lineStart && file.lineEnd
        ? ` (行 ${file.lineStart}-${file.lineEnd})` // (lines ${file.lineStart}-${file.lineEnd})
        : ""
    }\n\n`;

    totalContent += fileHeader + "```\n" + fileInfo + "\n```\n\n";
    filesSummary += `- **${file.path}**${
      file.description ? ` - ${file.description}` : ""
    } (${fileInfo.length} 字符)\n`; // characters

    totalLength += fileInfo.length + fileHeader.length + 8; // 8 for "```\n" and "\n```"
  }

  return {
    content: totalContent,
    summary: filesSummary,
  };
}

/**
 * 生成文件基本資訊摘要
 * Generate basic file information summary
 *
 * 根據檔案的元數據生成格式化的資訊摘要，包含檔案路徑、類型和相關提示。
 * Generate a formatted information summary based on file metadata, including file paths, types, and related hints.
 * 不讀取實際檔案內容，僅基於提供的 RelatedFile 物件生成信息。
 * Does not read actual file contents, generates information based only on the provided RelatedFile object.
 *
 * @param file 相關文件物件 - 包含檔案路徑、類型、描述等基本資訊
 * @param file Related file object - Contains basic information such as file path, type, description, etc.
 * @returns 格式化的檔案資訊摘要文字
 * @returns Formatted file information summary text
 */
function generateFileInfo(file: RelatedFile): string {
  let fileInfo = `檔案: ${file.path}\n`; // File:
  fileInfo += `類型: ${file.type}\n`; // Type:

  if (file.description) {
    fileInfo += `描述: ${file.description}\n`; // Description:
  }

  if (file.lineStart && file.lineEnd) {
    fileInfo += `行範圍: ${file.lineStart}-${file.lineEnd}\n`; // Line range:
  }

  fileInfo += `若需查看實際內容，請直接查看檔案: ${file.path}\n`;
  // To view actual content, please check the file directly:

  return fileInfo;
}

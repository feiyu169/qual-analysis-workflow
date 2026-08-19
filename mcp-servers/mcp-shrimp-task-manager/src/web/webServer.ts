import express, { Request, Response } from "express";
import getPort from "get-port";
import path from "path";
import fs from "fs";
import fsPromises from "fs/promises";
import { fileURLToPath } from "url";
import {
  getDataDir,
  getTasksFilePath,
  getWebGuiFilePath,
} from "../utils/paths.js";

export async function createWebServer() {
  // 創建 Express 應用
  // Create Express application
  const app = express();

  // 儲存 SSE 客戶端的列表
  // Store list of SSE clients
  let sseClients: Response[] = [];

  // 發送 SSE 事件的輔助函數
  // Helper function to send SSE events
  function sendSseUpdate() {
    sseClients.forEach((client) => {
      // 檢查客戶端是否仍然連接
      // Check if client is still connected
      if (!client.writableEnded) {
        client.write(
          `event: update\ndata: ${JSON.stringify({
            timestamp: Date.now(),
          })}\n\n`
        );
      }
    });
    // 清理已斷開的客戶端 (可選，但建議)
    // Clean up disconnected clients (optional, but recommended)
    sseClients = sseClients.filter((client) => !client.writableEnded);
  }

  // 設置靜態文件目錄
  // Set up static file directory
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const publicPath = path.join(__dirname, "..", "..", "src", "public");
  const TASKS_FILE_PATH = await getTasksFilePath(); // 使用工具函數取得檔案路徑
  // Use utility function to get file path

  app.use(express.static(publicPath));

  // 設置 API 路由
  // Set up API routes
  app.get("/api/tasks", async (req: Request, res: Response) => {
    try {
      // 使用 fsPromises 保持異步讀取
      // Use fsPromises to maintain async reading
      const tasksData = await fsPromises.readFile(TASKS_FILE_PATH, "utf-8");
      res.json(JSON.parse(tasksData));
    } catch (error) {
      // 確保檔案不存在時返回空任務列表
      // Ensure empty task list is returned when file doesn't exist
      if ((error as NodeJS.ErrnoException).code === "ENOENT") {
        res.json({ tasks: [] });
      } else {
        res.status(500).json({ error: "Failed to read tasks data" });
      }
    }
  });

  // 新增：SSE 端點
  // Add: SSE endpoint
  app.get("/api/tasks/stream", (req: Request, res: Response) => {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      // 可選: CORS 頭，如果前端和後端不在同一個 origin
      // Optional: CORS headers if frontend and backend are not on the same origin
      // "Access-Control-Allow-Origin": "*",
    });

    // 發送一個初始事件或保持連接
    // Send an initial event or maintain connection
    res.write("data: connected\n\n");

    // 將客戶端添加到列表
    // Add client to the list
    sseClients.push(res);

    // 當客戶端斷開連接時，將其從列表中移除
    // When client disconnects, remove it from the list
    req.on("close", () => {
      sseClients = sseClients.filter((client) => client !== res);
    });
  });

  // 定義 writeWebGuiFile 函數
  // Define writeWebGuiFile function
  async function writeWebGuiFile(port: number | string) {
    try {
      // 讀取 TEMPLATES_USE 環境變數並轉換為語言代碼
      // Read TEMPLATES_USE environment variable and convert to language code
      const templatesUse = process.env.TEMPLATES_USE || "en";
      const getLanguageFromTemplate = (template: string): string => {
        if (template === "zh") return "zh-TW";
        if (template === "en") return "en";
        // 自訂範本預設使用英文
        // Custom templates default to English
        return "en";
      };
      const language = getLanguageFromTemplate(templatesUse);

      const websiteUrl = `[Task Manager UI](http://localhost:${port}?lang=${language})`;
      const websiteFilePath = await getWebGuiFilePath();
      const DATA_DIR = await getDataDir();
      try {
        await fsPromises.access(DATA_DIR);
      } catch (error) {
        await fsPromises.mkdir(DATA_DIR, { recursive: true });
      }
      await fsPromises.writeFile(websiteFilePath, websiteUrl, "utf-8");
    } catch (error) {
      // Silently handle error - console not supported in MCP
    }
  }

  return {
    app,
    sendSseUpdate,
    async startServer() {
      // 獲取可用埠
      // Get available port
      const port = process.env.WEB_PORT || (await getPort());

      // 啟動 HTTP 伺服器
      // Start HTTP server
      const httpServer = app.listen(port, () => {
        // 在伺服器啟動後開始監聽檔案變化
        // Start monitoring file changes after server starts
        try {
          // 檢查檔案是否存在，如果不存在則不監聽 (避免 watch 報錯)
          // Check if file exists, don't monitor if it doesn't exist (to avoid watch errors)
          if (fs.existsSync(TASKS_FILE_PATH)) {
            fs.watch(TASKS_FILE_PATH, (eventType, filename) => {
              if (
                filename &&
                (eventType === "change" || eventType === "rename")
              ) {
                // 稍微延遲發送，以防短時間內多次觸發 (例如編輯器保存)
                // Slightly delay sending to prevent multiple triggers in a short time (e.g., editor saves)
                // debounce sendSseUpdate if needed
                // Debounce sendSseUpdate if needed
                sendSseUpdate();
              }
            });
          }
        } catch (watchError) {}

        // 將 URL 寫入 WebGUI.md
        // Write URL to WebGUI.md
        writeWebGuiFile(port).catch((error) => {});
      });

      // 設置進程終止事件處理 (確保移除 watcher)
      // Set up process termination event handling (ensure watcher removal)
      const shutdownHandler = async () => {
        // 關閉所有 SSE 連接
        // Close all SSE connections
        sseClients.forEach((client) => client.end());
        sseClients = [];

        // 關閉 HTTP 伺服器
        // Close HTTP server
        await new Promise<void>((resolve) => httpServer.close(() => resolve()));
      };

      process.on("SIGINT", shutdownHandler);
      process.on("SIGTERM", shutdownHandler);

      return httpServer;
    },
  };
}

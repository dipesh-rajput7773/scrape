import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod/v4";
import * as fs from "node:fs/promises";
import { glob } from "node:fs/promises";
import * as path from "node:path";
const BASE_DIR = process.env.FILESMETA_BASE_DIR || process.cwd();
const ALLOWED_PATTERNS = (process.env.FILESMETA_ALLOWED_PATTERNS || "*")
    .split(",")
    .map((s) => s.trim());
function isPathSafe(targetPath) {
    const resolved = path.resolve(BASE_DIR, targetPath);
    if (!resolved.startsWith(path.resolve(BASE_DIR))) {
        return false;
    }
    return true;
}
function resolvePath(targetPath) {
    return path.resolve(BASE_DIR, targetPath);
}
async function getFileMeta(filePath) {
    const stat = await fs.stat(filePath);
    return {
        name: path.basename(filePath),
        path: filePath,
        size: stat.size,
        created: stat.birthtime.toISOString(),
        modified: stat.mtime.toISOString(),
        accessed: stat.atime.toISOString(),
        isDirectory: stat.isDirectory(),
        isFile: stat.isFile(),
        isSymlink: stat.isSymbolicLink(),
        permissions: stat.mode.toString(8).slice(-3),
    };
}
const server = new McpServer({
    name: "filesmeta-mcp",
    version: "1.0.0",
});
server.registerTool("list_directory", {
    description: "List files and directories in a given directory with metadata",
    inputSchema: {
        dir: z
            .string()
            .default(".")
            .describe("Directory path relative to base (default: current dir)"),
        showHidden: z
            .boolean()
            .default(false)
            .describe("Include hidden files (starting with .)"),
    },
}, async ({ dir, showHidden }) => {
    if (!isPathSafe(dir)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const resolved = resolvePath(dir);
    try {
        const entries = await fs.readdir(resolved, { withFileTypes: true });
        const items = [];
        for (const entry of entries) {
            if (!showHidden && entry.name.startsWith("."))
                continue;
            const fullPath = path.join(resolved, entry.name);
            try {
                const meta = await getFileMeta(fullPath);
                items.push(meta);
            }
            catch {
                items.push({
                    name: entry.name,
                    path: fullPath,
                    error: "Could not read metadata",
                });
            }
        }
        return {
            content: [
                {
                    type: "text",
                    text: JSON.stringify(items, null, 2),
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error reading directory: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
server.registerTool("file_info", {
    description: "Get detailed metadata for a file or directory",
    inputSchema: {
        path: z.string().describe("Path to the file or directory"),
    },
}, async ({ path: filePath }) => {
    if (!isPathSafe(filePath)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const resolved = resolvePath(filePath);
    try {
        const meta = await getFileMeta(resolved);
        return {
            content: [
                {
                    type: "text",
                    text: JSON.stringify(meta, null, 2),
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
server.registerTool("search_files", {
    description: "Search for files using glob patterns",
    inputSchema: {
        pattern: z.string().describe("Glob pattern to search (e.g. **/*.ts, *.txt)"),
        dir: z
            .string()
            .default(".")
            .describe("Directory to search in (default: current dir)"),
    },
}, async ({ pattern, dir }) => {
    if (!isPathSafe(dir)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const resolved = resolvePath(dir);
    try {
        const results = [];
        for await (const entry of glob(pattern, { cwd: resolved, withFileTypes: true })) {
            if (typeof entry === "string") {
                results.push({ path: path.join(resolved, entry) });
            }
            else {
                results.push({
                    name: entry.name,
                    path: path.join(entry.parentPath, entry.name),
                });
            }
        }
        return {
            content: [
                {
                    type: "text",
                    text: JSON.stringify(results, null, 2),
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error searching files: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
server.registerTool("read_file", {
    description: "Read the contents of a text file",
    inputSchema: {
        path: z.string().describe("Path to the file to read"),
        encoding: z
            .enum(["utf-8", "ascii", "base64", "hex"])
            .default("utf-8")
            .describe("File encoding (default: utf-8)"),
        maxSize: z
            .number()
            .int()
            .positive()
            .default(1048576)
            .describe("Maximum file size in bytes (default: 1MB)"),
    },
}, async ({ path: filePath, encoding, maxSize }) => {
    if (!isPathSafe(filePath)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const resolved = resolvePath(filePath);
    try {
        const stat = await fs.stat(resolved);
        if (stat.isDirectory()) {
            return {
                content: [{ type: "text", text: "Error: Path is a directory" }],
                isError: true,
            };
        }
        if (stat.size > maxSize) {
            return {
                content: [
                    {
                        type: "text",
                        text: `Error: File is ${stat.size} bytes, exceeds max of ${maxSize} bytes`,
                    },
                ],
                isError: true,
            };
        }
        const content = await fs.readFile(resolved, encoding);
        return {
            content: [
                {
                    type: "text",
                    text: content,
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error reading file: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
server.registerTool("write_file", {
    description: "Write content to a file (creates parent directories if needed)",
    inputSchema: {
        path: z.string().describe("Path to the file to write"),
        content: z.string().describe("Content to write to the file"),
        encoding: z
            .enum(["utf-8", "ascii", "base64", "hex"])
            .default("utf-8")
            .describe("File encoding (default: utf-8)"),
    },
}, async ({ path: filePath, content, encoding }) => {
    if (!isPathSafe(filePath)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const resolved = resolvePath(filePath);
    try {
        await fs.mkdir(path.dirname(resolved), { recursive: true });
        await fs.writeFile(resolved, content, encoding);
        const meta = await getFileMeta(resolved);
        return {
            content: [
                {
                    type: "text",
                    text: `File written successfully:\n${JSON.stringify(meta, null, 2)}`,
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error writing file: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
server.registerTool("delete_file", {
    description: "Delete a file or empty directory",
    inputSchema: {
        path: z.string().describe("Path to the file or directory to delete"),
        recursive: z
            .boolean()
            .default(false)
            .describe("Recursively delete directory contents (default: false)"),
    },
}, async ({ path: filePath, recursive }) => {
    if (!isPathSafe(filePath)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const resolved = resolvePath(filePath);
    try {
        const meta = await getFileMeta(resolved);
        if (meta.isDirectory && !recursive) {
            return {
                content: [
                    {
                        type: "text",
                        text: "Error: Cannot delete directory without recursive flag",
                    },
                ],
                isError: true,
            };
        }
        await fs.rm(resolved, { recursive, force: true });
        return {
            content: [
                {
                    type: "text",
                    text: `Deleted: ${resolved}`,
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error deleting: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
server.registerTool("create_directory", {
    description: "Create a directory (like mkdir -p)",
    inputSchema: {
        path: z.string().describe("Path of the directory to create"),
    },
}, async ({ path: dirPath }) => {
    if (!isPathSafe(dirPath)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const resolved = resolvePath(dirPath);
    try {
        await fs.mkdir(resolved, { recursive: true });
        const meta = await getFileMeta(resolved);
        return {
            content: [
                {
                    type: "text",
                    text: `Directory created:\n${JSON.stringify(meta, null, 2)}`,
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error creating directory: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
server.registerTool("rename_move", {
    description: "Rename or move a file or directory",
    inputSchema: {
        source: z.string().describe("Current path of the file/directory"),
        destination: z.string().describe("New path for the file/directory"),
    },
}, async ({ source, destination }) => {
    if (!isPathSafe(source) || !isPathSafe(destination)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const srcResolved = resolvePath(source);
    const destResolved = resolvePath(destination);
    try {
        await fs.mkdir(path.dirname(destResolved), { recursive: true });
        await fs.rename(srcResolved, destResolved);
        const meta = await getFileMeta(destResolved);
        return {
            content: [
                {
                    type: "text",
                    text: `Moved/renamed:\n${JSON.stringify(meta, null, 2)}`,
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error renaming/moving: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
server.registerTool("copy_file", {
    description: "Copy a file to a new location (creates parent directories if needed)",
    inputSchema: {
        source: z.string().describe("Path of the source file"),
        destination: z.string().describe("Path for the copy"),
    },
}, async ({ source, destination }) => {
    if (!isPathSafe(source) || !isPathSafe(destination)) {
        return {
            content: [{ type: "text", text: "Error: Path traversal detected" }],
            isError: true,
        };
    }
    const srcResolved = resolvePath(source);
    const destResolved = resolvePath(destination);
    try {
        await fs.mkdir(path.dirname(destResolved), { recursive: true });
        await fs.cp(srcResolved, destResolved, { recursive: true });
        const meta = await getFileMeta(destResolved);
        return {
            content: [
                {
                    type: "text",
                    text: `Copied:\n${JSON.stringify(meta, null, 2)}`,
                },
            ],
        };
    }
    catch (err) {
        return {
            content: [
                {
                    type: "text",
                    text: `Error copying: ${err.message}`,
                },
            ],
            isError: true,
        };
    }
});
async function main() {
    console.error(`FilesMeta MCP server starting...`);
    console.error(`Base directory: ${BASE_DIR}`);
    const transport = new StdioServerTransport();
    await server.connect(transport);
}
main().catch((error) => {
    console.error("Server error:", error);
    process.exit(1);
});
//# sourceMappingURL=index.js.map
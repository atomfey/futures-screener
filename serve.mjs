import { createServer } from "http";
import { readFile } from "fs/promises";
import { join, extname } from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const DOCS = join(__dirname, "docs");
const PORT = process.env.PORT || 3001;

const MIME = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "application/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
};

createServer(async (req, res) => {
  let path = req.url === "/" ? "/index.html" : decodeURIComponent(req.url.split("?")[0]);
  try {
    const data = await readFile(join(DOCS, path));
    res.writeHead(200, {
      "Content-Type": MIME[extname(path)] || "application/octet-stream",
      "Access-Control-Allow-Origin": "*",
    });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
}).listen(PORT, () => console.log(`Futures Screener running on http://localhost:${PORT}`));

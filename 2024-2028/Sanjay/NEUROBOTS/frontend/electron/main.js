// electron/main.js
const { app, BrowserWindow } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

const isDev = !app.isPackaged;
let serverProcess;

function startServer() {
  if (isDev) return; // vite dev already running separately

  // Adjust this path to wherever your Nitro build output lands
  serverProcess = spawn("node", [path.join(__dirname, "../.output/server/index.mjs")], {
    stdio: "inherit",
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    icon: path.join(__dirname, "../public/favicon.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const url = isDev ? "http://localhost:3000" : "http://localhost:3000"; // same port, prod server serves it
  win.loadURL(url);

  if (isDev) win.webContents.openDevTools();
}

app.whenReady().then(() => {
  startServer();
  setTimeout(createWindow, isDev ? 0 : 1000); // give the spawned server a beat to boot in prod
});

app.on("window-all-closed", () => {
  if (serverProcess) serverProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

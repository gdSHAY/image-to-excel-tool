using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

static class Launcher
{
    public static readonly string Root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
    public const string Url = "http://127.0.0.1:8788/";
    static string PythonRuntime()
    {
        var portable = Path.Combine(Root, "runtime", "pythonw.exe");
        return File.Exists(portable) ? portable : Path.Combine(Root, ".venv", "Scripts", "pythonw.exe");
    }
    static JavaScriptSerializer Json = new JavaScriptSerializer();
    public static object Read(string route)
    {
        var request = (HttpWebRequest)WebRequest.Create(Url + route);
        request.Proxy = null; request.Timeout = 1500; request.ReadWriteTimeout = 1500;
        using (var response = request.GetResponse())
        using (var reader = new StreamReader(response.GetResponseStream()))
            return Json.DeserializeObject(reader.ReadToEnd());
    }
    public static Dictionary<string, object> Health()
    {
        Dictionary<string, object> state;
        try { state = Read("api/health") as Dictionary<string, object>; }
        catch (WebException) { return null; }
        if (state == null || !state.ContainsKey("application") || (string)state["application"] != "ScanTableStudio")
            throw new Exception("8788 端口被其他程序占用，未启动或关闭其他程序。");
        return state;
    }
    static void Resources()
    {
        if (!File.Exists(PythonRuntime())) throw new Exception("缺少内置运行环境，请完整解压 ZIP 后启动。");
        foreach (var file in new[] { "desktop_server.py", "app.py", "web\\index.html",
            "node_modules\\@camscanner-cli\\win32-x64\\bin\\camscanner-cli.exe" })
            if (!File.Exists(Path.Combine(Root, file)))
                throw new Exception("缺少项目文件：" + file + "\n请将 EXE 放在 ScanTableStudio 项目目录内，不要单独移动。首次安装可运行 setup.ps1。");
    }
    public static Dictionary<string, object> Start()
    {
        Resources();
        using (var gate = new Mutex(false, "Local\\ScanTableStudioStartup8788"))
        {
            if (!gate.WaitOne(35000)) throw new Exception("另一个启动器仍在启动，请稍后再试。");
            try
            {
                var existing = Health();
                if (existing != null) return existing;
                using (var socket = new TcpClient())
                {
                    try { socket.Connect(IPAddress.Loopback, 8788); throw new Exception("8788 端口被其他程序占用，未修改其他程序。"); }
                    catch (SocketException) { }
                }
                var process = Process.Start(new ProcessStartInfo {
                    FileName = PythonRuntime(),
                    Arguments = "\"" + Path.Combine(Root, "desktop_server.py") + "\"",
                    WorkingDirectory = Root, UseShellExecute = false, CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                });
                for (int i = 0; i < 120; i++)
                {
                    var state = Health();
                    if (state != null) return state;
                    if (process.HasExited) throw new Exception("服务启动失败。请查看 data\\desktop-server.log。");
                    Thread.Sleep(250);
                }
                throw new Exception("服务未在 30 秒内准备好，未重复启动。请查看 data\\desktop-server.log。");
            }
            finally { gate.ReleaseMutex(); }
        }
    }
    public static void Stop()
    {
        var state = Health();
        if (state == null) return;
        foreach (var item in (object[])Read("api/jobs"))
        {
            var job = item as Dictionary<string, object>;
            if (job != null && Convert.ToString(job["status"]) == "recognizing")
                throw new Exception("仍有任务正在识别，请等任务结束后再停止工具。");
        }
        int pid = Convert.ToInt32(state["pid"]);
        using (var process = Process.GetProcessById(pid)) { process.Kill(); process.WaitForExit(5000); }
    }
    public static void Browser() { Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true }); }

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length > 0)
        {
            try
            {
                if (args[0] == "--stop") { Stop(); return 0; }
                if (args[0] != "--verify-start") return 2;
                var state = Start();
                Directory.CreateDirectory(Path.Combine(Root, "verification"));
                File.WriteAllText(Path.Combine(Root, "verification", "launcher-check.json"),
                    Json.Serialize(new { passed = true, workspace = Root, application = state["application"], pid = state["pid"], url = Url }));
                return 0;
            }
            catch (Exception exc)
            {
                Directory.CreateDirectory(Path.Combine(Root, "verification"));
                File.WriteAllText(Path.Combine(Root, "verification", "launcher-check.json"), Json.Serialize(new { passed = false, error = exc.Message }));
                return 1;
            }
        }
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new LauncherWindow()); return 0;
    }
}

sealed class LauncherWindow : Form
{
    Label state;
    Button open, stop;
    public LauncherWindow()
    {
        Text = "图片表格工作台 · 启动器"; ClientSize = new Size(660, 350);
        StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
        Font = new Font("Microsoft YaHei UI", 12); BackColor = Color.FromArgb(245, 248, 252);
        var title = new Label { Text = "图片表格工作台", Font = new Font(Font.FontFamily, 22, FontStyle.Bold), Location = new Point(28, 24), AutoSize = true };
        state = new Label { Text = "正在启动，请稍候…", Location = new Point(30, 88), Size = new Size(598, 70), ForeColor = Color.FromArgb(35, 75, 140) };
        var steps = new Label { Text = "选择图片  →  增强识别  →  点格校对  →  导出 Excel", Location = new Point(30, 167), Size = new Size(598, 35) };
        open = new Button { Text = "打开工作台", Location = new Point(30, 218), Size = new Size(280, 50), BackColor = Color.FromArgb(37, 99, 235), ForeColor = Color.White, FlatStyle = FlatStyle.Flat, Enabled = false };
        stop = new Button { Text = "停止工具", Location = new Point(330, 218), Size = new Size(280, 50), Enabled = false };
        var hint = new Label { Text = "关闭启动器后，工作台仍在后台运行。退出时请点击“停止工具”。", Location = new Point(30, 287), Size = new Size(598, 42), Font = new Font(Font.FontFamily, 10), ForeColor = Color.DimGray };
        Controls.AddRange(new Control[] { title, state, steps, open, stop, hint });
        Shown += async (s, e) => await Launch();
        open.Click += async (s, e) => await Launch();
        stop.Click += async (s, e) => {
            open.Enabled = stop.Enabled = false;
            try { await Task.Run(() => Launcher.Stop()); state.Text = "工具已停止。点击“打开工作台”可重新启动。"; }
            catch (Exception exc) { state.Text = exc.Message; stop.Enabled = true; }
            finally { open.Enabled = true; }
        };
    }
    async Task Launch()
    {
        open.Enabled = stop.Enabled = false; state.Text = "正在启动并检查服务…";
        try {
            await Task.Run(() => Launcher.Start());
            Launcher.Browser(); state.Text = "工作台已启动，浏览器已打开。\n" + Launcher.Url; stop.Enabled = true;
        }
        catch (Exception exc) { state.Text = exc.Message; MessageBox.Show(this, exc.Message, "启动提示", MessageBoxButtons.OK, MessageBoxIcon.Information); }
        finally { open.Enabled = true; }
    }
}

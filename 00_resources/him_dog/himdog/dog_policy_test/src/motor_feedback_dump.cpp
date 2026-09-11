// motor_feedback_dump.cpp
// 订阅 /motor_feedback，按 y 启动 Web 展示 12 个电机实时扭矩+温度曲线
// 浏览器访问 http://<IP>:8080
//
// 依赖：无额外依赖，仅 POSIX socket + ROS2 + 内嵌 Chart.js (CDN)

#include <rclcpp/rclcpp.hpp>
#include "dog_control/msg/motor_feedback.hpp"

#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <deque>
#include <functional>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #pragma comment(lib, "ws2_32.lib")
  typedef int socklen_t;
  #define CLOSE_SOCKET closesocket
#else
  #include <netinet/in.h>
  #include <sys/socket.h>
  #include <unistd.h>
  #include <termios.h>
  #include <fcntl.h>
  #define CLOSE_SOCKET close
#endif

#include <atomic>

// ========================= 常量 =========================
constexpr std::size_t kNumDofs = 12;
constexpr std::size_t kHistoryLen = 300;      // 300 个点 @10Hz = 30 秒
constexpr int kWebPort = 8080;
constexpr int kDataPushMs = 100;               // 每 100ms 采样一次推到缓冲区
constexpr float kAlarmTemp = 45.0f;             // 温度报警阈值 (°C)
constexpr const char * kJointLabels[kNumDofs] = {
  "FL_hip", "FL_thigh", "FL_calf",
  "FR_hip", "FR_thigh", "FR_calf",
  "RL_hip", "RL_thigh", "RL_calf",
  "RR_hip", "RR_thigh", "RR_calf"
};

// 12 种颜色
constexpr const char * kColors[kNumDofs] = {
  "#e6194B", "#f58231", "#ffe119",
  "#3cb44b", "#42d4f4", "#4363d8",
  "#911eb4", "#f032e6", "#bfef45",
  "#fabed4", "#469990", "#dcbeff"
};

// ========================= HTML =========================
static std::string BuildHtmlPage()
{
  std::string html = R"rawliteral(<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Motor Torque & Temperature Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3"></script>
<style>
body{font-family:monospace;background:#1a1a2e;color:#eee;margin:20px}
h1{text-align:center;color:#0f0}
.info{text-align:center;margin:10px;color:#888;font-size:14px}
.alarm-bar{width:95%;max-width:1400px;margin:10px auto;padding:12px 20px;border-radius:8px;
  background:#2d1111;border:2px solid #ff4444;color:#ff4444;font-size:16px;font-weight:bold;
  text-align:center;display:none;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.4}}
.chart-container{width:95%;max-width:1400px;margin:20px auto;background:#16213e;
  padding:15px;border-radius:8px;position:relative;height:70vh}
canvas{width:100%!important;height:100%!important}
</style></head><body>
<h1>&#x1F4BE; Motor Torque & Temperature Realtime</h1>
<div class="info">Polling @ 100ms | Scroll: last 30s | Click legend to toggle</div>
<div class="chart-container" style="height:35vh"><canvas id="torqueChart"></canvas></div>
<div id="alarmBar" class="alarm-bar">&#9888; OVERHEAT: <span id="alarmMsg">-</span></div>
<h2 style="text-align:center;color:#0ff;margin-top:10px">Temperature (°C)</h2>
<div class="chart-container" style="height:35vh"><canvas id="tempChart"></canvas></div>
<script>
const LABELS=[)rawliteral";

  // 拼接标签名
  for (std::size_t i = 0; i < kNumDofs; ++i) {
    if (i > 0) html += ",";
    html += "'";
    html += kJointLabels[i];
    html += "'";
  }

  html += R"rawliteral(];
const COLORS=[)rawliteral";

  for (std::size_t i = 0; i < kNumDofs; ++i) {
    if (i > 0) html += ",";
    html += "'";
    html += kColors[i];
    html += "'";
  }

  html += R"rawliteral(];
function makeDatasets(){return LABELS.map((name,i)=>({
  label:name,data:[],borderColor:COLORS[i],backgroundColor:COLORS[i]+"33",
  borderWidth:1.5,pointRadius:0,tension:0.2,fill:false
}));}
const torqueChart=new Chart(document.getElementById('torqueChart'),{
  type:'line',data:{labels:[],datasets:makeDatasets()},
  options:{
    responsive:true,maintainAspectRatio:false,animation:false,
    scales:{
      x:{display:true,title:{display:true,text:'Time (s)',color:'#aaa'},
         ticks:{color:'#888',maxTicksLimit:10},grid:{color:'#333'}},
      y:{display:true,title:{display:true,text:'Torque (N\u00B7m)',color:'#aaa'},
         ticks:{color:'#888'},grid:{color:'#333'}}
    },
    plugins:{legend:{labels:{color:'#ccc',font:{size:11}}}},
    interaction:{mode:'index',intersect:false}
  }
});
const tempChart=new Chart(document.getElementById('tempChart'),{
  type:'line',data:{labels:[],datasets:makeDatasets()},
  options:{
    responsive:true,maintainAspectRatio:false,animation:false,
    scales:{
      x:{display:true,title:{display:true,text:'Time (s)',color:'#aaa'},
         ticks:{color:'#888',maxTicksLimit:10},grid:{color:'#333'}},
      y:{display:true,title:{display:true,text:'Temperature (\u00B0C)',color:'#aaa'},
         ticks:{color:'#888'},
         suggestedMin:20,suggestedMax:60,grid:{color:'#333'},
         annotations:{}},
    plugins:{legend:{labels:{color:'#ccc',font:{size:11}}},
      annotation:{annotations:{line45:{type:'line',yMin:45,yMax:45,
        borderColor:'#ff4444',borderWidth:2,borderDash:[6,4],
        label:{display:true,content:'ALARM 45\u00B0C',position:'end',
          backgroundColor:'#ff4444',color:'#fff',font:{size:10}}}}}},
    interaction:{mode:'index',intersect:false}
  }
});
let t0=Date.now();
async function poll(){
  try{
    const r=await fetch('/data?_='+Date.now());
    const d=await r.json();
    if(!d.torque)return;
    const t=((d.ts-t0)/1000).toFixed(1);
    torqueChart.data.labels.push(t);
    tempChart.data.labels.push(t);
    for(let i=0;i<d.torque.length;i++){
      torqueChart.data.datasets[i].data.push(d.torque[i]);
    }
    if(d.temperature){
      for(let i=0;i<d.temperature.length;i++){
        tempChart.data.datasets[i].data.push(d.temperature[i]);
      }
    }
    const maxPts=)rawliteral";

  html += std::to_string(kHistoryLen);

  html += R"rawliteral(;
    if(torqueChart.data.labels.length>maxPts){
      torqueChart.data.labels.shift();
      torqueChart.data.datasets.forEach(ds=>ds.data.shift());
      tempChart.data.labels.shift();
      tempChart.data.datasets.forEach(ds=>ds.data.shift());
    }
    // 温度报警
    const ALARM=45;
    if(d.temperature){
      const hot=[];
      for(let i=0;i<d.temperature.length;i++){
        if(d.temperature[i]>=ALARM) hot.push(LABELS[i]+'('+d.temperature[i].toFixed(1)+'\u00B0C)');
      }
      const bar=document.getElementById('alarmBar');
      const msg=document.getElementById('alarmMsg');
      if(hot.length>0){bar.style.display='block';msg.textContent=hot.join(', ');}
      else{bar.style.display='none';msg.textContent='-';}
    }
    torqueChart.update('none');
    tempChart.update('none');
  }catch(e){}
}
setInterval(poll,100);
</script></body></html>)rawliteral";

  return html;
}

// ========================= 节点 =========================
class MotorFeedbackDump : public rclcpp::Node
{
public:
  MotorFeedbackDump()
  : Node("motor_feedback_dump")
  {
    sub_ = this->create_subscription<dog_control::msg::MotorFeedback>(
      "/motor_feedback", 10,
      std::bind(&MotorFeedbackDump::callback, this, std::placeholders::_1));

    // 采样定时器：每 100ms 从最新消息中提取 torque 推入环形缓冲区
    data_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(kDataPushMs),
      std::bind(&MotorFeedbackDump::sampleData, this));

    html_page_ = BuildHtmlPage();

    // 启动键盘线程
    kb_running_ = true;
    kb_thread_ = std::thread(&MotorFeedbackDump::keyboardLoop, this);

    // 初始化 socket 系统
#ifdef _WIN32
    WSADATA wsa;
    WSAStartup(MAKEWORD(2,2), &wsa);
#endif

    // 默认自动启动 Web 服务器
    startWebServer();

    RCLCPP_INFO(this->get_logger(),
      "motor_feedback_dump started — Web 扭矩+温度展示已自动启动 (端口 %d)，按 y 切换开关", kWebPort);
  }

  ~MotorFeedbackDump()
  {
    stopWebServer();
    kb_running_ = false;
    if (kb_thread_.joinable()) kb_thread_.join();
#ifdef _WIN32
    WSACleanup();
#endif
  }

  bool IsKeyboardRunning() const { return kb_running_.load(); }

private:
  // ---------- 键盘 ----------
  void keyboardLoop()
  {
    struct termios orig, raw;
    tcgetattr(STDIN_FILENO, &orig);
    raw = orig;
    raw.c_lflag &= ~(ECHO | ICANON);
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSANOW, &raw);

    while (kb_running_) {
      char ch = 0;
      if (read(STDIN_FILENO, &ch, 1) <= 0) {
        usleep(10000);
        continue;
      }
      if (ch == 'y') {
        if (!web_running_) {
          startWebServer();
        } else {
          stopWebServer();
          printf("  [Web] 已停止\n");
        }
      }
    }
    tcsetattr(STDIN_FILENO, TCSANOW, &orig);
  }

  // ---------- ROS 回调 ----------
  void callback(const dog_control::msg::MotorFeedback::SharedPtr msg)
  {
    std::lock_guard<std::mutex> lock(data_mutex_);
    latest_msg_ = msg;
    ++msg_count_;
  }

  // ---------- 数据采样（10Hz）----------
  void sampleData()
  {
    std::lock_guard<std::mutex> lock(data_mutex_);
    if (!latest_msg_) return;

    auto now = std::chrono::steady_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
      now.time_since_epoch()).count();

    // 推入环形缓冲区
    std::array<float, kNumDofs> torque_sample{};
    std::array<float, kNumDofs> temp_sample{};
    bool alarm = false;
    for (std::size_t i = 0; i < kNumDofs; ++i) {
      torque_sample[i] = (i < latest_msg_->torque.size()) ? latest_msg_->torque[i] : 0.0f;
      temp_sample[i] = (i < latest_msg_->temperature.size()) ? latest_msg_->temperature[i] : 0.0f;

      // 温度超限检测
      if (temp_sample[i] >= kAlarmTemp) {
        if (!alarm) {
          printf("\033[31m  ⚠ [ALARM] ");
        }
        printf("%s=%.1f°C  ", kJointLabels[i], temp_sample[i]);
        alarm = true;
      }
    }
    if (alarm) {
      printf("\033[0m\n");
      fflush(stdout);
    }

    history_.push_back({ms, torque_sample, temp_sample});
    if (history_.size() > kHistoryLen) {
      history_.pop_front();
    }
  }

  // ---------- Web 服务器 ----------
  void startWebServer()
  {
    web_running_ = true;
    web_thread_ = std::thread(&MotorFeedbackDump::webServerLoop, this);
    printf("\n  ★ Web 扭矩+温度展示已启动 — 浏览器打开 http://localhost:%d ★\n\n", kWebPort);
  }

  void stopWebServer()
  {
    web_running_ = false;
    if (listen_fd_ >= 0) {
      CLOSE_SOCKET(listen_fd_);
      listen_fd_ = -1;
    }
    if (web_thread_.joinable()) web_thread_.join();
  }

  void webServerLoop()
  {
    listen_fd_ = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd_ < 0) {
      printf("  [Web] socket() 失败\n");
      web_running_ = false;
      return;
    }

    int opt = 1;
    setsockopt(listen_fd_, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(kWebPort);

    if (bind(listen_fd_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
      printf("  [Web] bind() 失败 (端口 %d 可能被占用)\n", kWebPort);
      CLOSE_SOCKET(listen_fd_);
      listen_fd_ = -1;
      web_running_ = false;
      return;
    }

    listen(listen_fd_, 5);
    printf("  [Web] Listening on port %d...\n", kWebPort);

    while (web_running_) {
      // 非阻塞 accept：设超时 500ms
      fd_set fds;
      FD_ZERO(&fds);
      FD_SET(listen_fd_, &fds);
      struct timeval tv{0, 500000};
      int sel = select(listen_fd_ + 1, &fds, nullptr, nullptr, &tv);
      if (sel <= 0) continue;

      struct sockaddr_in cli_addr{};
      socklen_t cli_len = sizeof(cli_addr);
      int client_fd = accept(listen_fd_, (struct sockaddr*)&cli_addr, &cli_len);
      if (client_fd < 0) continue;

      handleClient(client_fd);
      CLOSE_SOCKET(client_fd);
    }
  }

  void handleClient(int fd)
  {
    // 读请求（简单：读一行就够）
    char buf[1024]{};
    recv(fd, buf, sizeof(buf) - 1, 0);

    std::string response;

    if (std::strstr(buf, "GET /data")) {
      // JSON 数据响应
      response = buildDataJson();
    } else {
      // HTML 页面
      response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n"
                 + html_page_;
    }

    send(fd, response.c_str(), response.size(), 0);
  }

  std::string buildDataJson()
  {
    std::lock_guard<std::mutex> lock(data_mutex_);

    // 返回最新一个采样点
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(4);
    oss << "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
           "Access-Control-Allow-Origin: *\r\n"
           "Cache-Control: no-cache, no-store, must-revalidate\r\n"
           "Pragma: no-cache\r\nExpires: 0\r\n"
           "Connection: close\r\n\r\n";

    if (history_.empty()) {
      oss << "{}";
      return oss.str();
    }

    auto & latest = history_.back();
    oss << "{\"ts\":" << latest.ts << ",\"torque\":[";
    for (std::size_t i = 0; i < kNumDofs; ++i) {
      if (i > 0) oss << ",";
      oss << latest.torque[i];
    }
    oss << "],\"temperature\":[";
    for (std::size_t i = 0; i < kNumDofs; ++i) {
      if (i > 0) oss << ",";
      oss << latest.temperature[i];
    }
    oss << "]}";
    return oss.str();
  }

  // ---------- 成员 ----------
  rclcpp::Subscription<dog_control::msg::MotorFeedback>::SharedPtr sub_;
  rclcpp::TimerBase::SharedPtr data_timer_;

  dog_control::msg::MotorFeedback::SharedPtr latest_msg_;
  std::mutex data_mutex_;
  std::size_t msg_count_{0};

  struct MotorSample {
    int64_t ts;  // ms since epoch
    std::array<float, kNumDofs> torque;
    std::array<float, kNumDofs> temperature;
  };
  std::deque<MotorSample> history_;

  std::string html_page_;

  // 键盘
  std::atomic<bool> kb_running_{false};
  std::thread kb_thread_;

  // Web 服务器
  std::atomic<bool> web_running_{false};
  std::thread web_thread_;
  int listen_fd_{-1};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<MotorFeedbackDump>();

  while (rclcpp::ok()) {
    rclcpp::spin_some(node);
    if (!node->IsKeyboardRunning()) break;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  rclcpp::shutdown();
  return 0;
}
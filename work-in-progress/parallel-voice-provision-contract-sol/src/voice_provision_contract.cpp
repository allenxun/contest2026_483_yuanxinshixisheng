#include "voice_provision_contract.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <unordered_map>
#include <utility>

namespace vela::voice_provision {
namespace {
std::string compact(std::string s) {
  s.erase(std::remove_if(s.begin(), s.end(), [](unsigned char c) {
    return std::isspace(c) || c == ',' || c == '.' || c == '!' || c == '?';
  }), s.end());
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
    return static_cast<char>(std::tolower(c));
  });
  return s;
}
bool wake(const std::string& s) {
  const auto n = compact(s);
  return n == "openvela" || n == "helloopenvela" || n == "你好，openvela" ||
         n == "你好openvela";
}
bool cancelWord(const std::string& s) { const auto n=compact(s); return n=="取消" || n=="退出"; }
bool rescanWord(const std::string& s) { const auto n=compact(s); return n=="重新扫描" || n=="重扫"; }
bool finishWord(const std::string& s) { const auto n=compact(s); return n=="完成" || n=="输入完成"; }
bool confirmWord(const std::string& s) { const auto n=compact(s); return n=="确认提交" || n=="确认"; }
bool retryWord(const std::string& s) { const auto n=compact(s); return n=="重新输入" || n=="不确认" || n=="否"; }
std::optional<std::size_t> choice(const std::string& s) {
  const auto n=compact(s);
  static const char* names[]={"网络一","网络二","网络三","网络四","网络五"};
  for(std::size_t i=0;i<5;i++) if(n==names[i] || n==std::to_string(i+1)) return i;
  return std::nullopt;
}
std::optional<char> token(const std::string& s) {
  const auto n=compact(s);
  if(n.size()==1 && static_cast<unsigned char>(n[0])>=32 && static_cast<unsigned char>(n[0])<=126) return n[0];
  static const std::unordered_map<std::string,char> words{
    {"零",'0'},{"一",'1'},{"二",'2'},{"三",'3'},{"四",'4'},{"五",'5'},
    {"六",'6'},{"七",'7'},{"八",'8'},{"九",'9'},{"艾特",'@'},{"井号",'#'},
    {"下划线",'_'},{"减号",'-'},{"点",'.'},{"正斜杠",'/'},{"斜杠",'/'},
    {"反斜杠",'\\'},{"反斜线",'\\'}
  };
  const auto it=words.find(n); return it==words.end()?std::nullopt:std::optional<char>(it->second);
}
bool usableIpv4(const std::string& ip) {
  unsigned a,b,c,d; char tail;
  if(std::sscanf(ip.c_str(),"%u.%u.%u.%u%c",&a,&b,&c,&d,&tail)!=4) return false;
  return a>0 && a<224 && a!=127 && !(a==169 && b==254) && b<256 && c<256 && d<256;
}
}

Machine::Machine(VoiceOutput& v, WifiService& w, Clock& c, Config cfg)
  : voice_(v),wifi_(w),clock_(c),config_(std::move(cfg)) {
  config_.max_networks=std::min<std::size_t>(5,config_.max_networks);
  config_.max_password_length=std::min<std::size_t>(63,config_.max_password_length);
  config_.min_password_length=std::min(config_.min_password_length,config_.max_password_length);
  password_.reserve(config_.max_password_length);
}
Machine::~Machine(){ clearTransactions(); wipePassword(); }
void Machine::touch() noexcept { deadline_ms_=clock_.nowMs()+config_.input_timeout_ms; }
void Machine::wipePassword() noexcept {
  volatile char* p=password_.empty()?nullptr:password_.data();
  for(std::size_t i=0;i<password_.size();++i)p[i]=0;
  password_.clear(); view_.password_length=0;
}
void Machine::clearTransactions() noexcept {
  if(scan_id_)wifi_.cancelScan(scan_id_);
  if(link_id_)wifi_.cancelLink(link_id_);
  scan_id_=link_id_=0;
}
void Machine::say(const std::string& s){ if(!voice_.speak(s)){ clearTransactions();wipePassword();view_.state=State::Error; } }
void Machine::terminal(State s,const std::string& text){clearTransactions();wipePassword();view_.state=s;view_.grammar=Grammar::Wake;say(text);}
void Machine::start(){clearTransactions();wipePassword();view_={};voice_.stop();touch();}
void Machine::cancel(){terminal(State::Idle,"已取消配置");}

void Machine::ingest(const std::string& text){
  if(cancelWord(text)){cancel();return;}
  switch(view_.state){
    case State::WaitingWake: case State::Idle:
      if(wake(text)){say("你好，开始配置网络");if(view_.state!=State::Error)beginScan();} break;
    case State::ChoosingNetwork: choose(text); break;
    case State::EnteringPassword: password(text); break;
    case State::ConfirmingPassword: confirmation(text); break;
    default: break;
  }
}

void Machine::beginScan(){
  wipePassword(); if(scan_id_)wifi_.cancelScan(scan_id_); scan_id_=0;
  view_.candidates.clear();view_.selected_index.reset();view_.state=State::Scanning;view_.grammar=Grammar::CancelOnly;
  deadline_ms_=clock_.nowMs()+config_.scan_timeout_ms;
  applyScan(wifi_.beginScan());
}
void Machine::applyScan(ScanEvent e){
  if(!e.request_id){terminal(State::Error,"扫描接口错误");return;}
  if(!scan_id_)scan_id_=e.request_id;
  if(e.request_id!=scan_id_)return;
  if(e.status==ScanStatus::Accepted || e.status==ScanStatus::Running)return;
  if(e.status!=ScanStatus::Ready || e.access_points.size()>64){
    const auto status=e.status;wifi_.cancelScan(scan_id_);scan_id_=0;
    view_.state=State::Idle;view_.grammar=Grammar::Wake;
    if(status==ScanStatus::Busy)say("网络服务忙，请稍后重新唤醒");
    else if(status==ScanStatus::Unsupported)say("当前不支持扫描");
    else if(status==ScanStatus::Timeout)say("扫描超时");
    else if(status==ScanStatus::Cancelled)say("扫描已取消");
    else {terminal(State::Error,"扫描失败");return;}
    return;
  }
  scan_id_=0;
  std::unordered_map<std::string,AccessPoint> best;
  for(auto& ap:e.access_points)if(!ap.ssid.empty() && (best.find(ap.ssid)==best.end() || best[ap.ssid].rssi<ap.rssi))best[ap.ssid]=ap;
  for(auto& p:best)view_.candidates.push_back(std::move(p.second));
  std::sort(view_.candidates.begin(),view_.candidates.end(),[](const auto&a,const auto&b){return a.rssi>b.rssi;});
  if(view_.candidates.size()>config_.max_networks)view_.candidates.resize(config_.max_networks);
  view_.state=State::ChoosingNetwork;view_.grammar=Grammar::NetworkChoice;touch();
  if(view_.candidates.empty()){say("没有发现网络，请说重新扫描或取消");return;}
  std::string msg="发现网络。";for(std::size_t i=0;i<view_.candidates.size();++i)msg+="网络"+std::to_string(i+1)+"，"+view_.candidates[i].ssid+"。";
  say(msg+"请选择编号");
}
void Machine::choose(const std::string& text){
  if(rescanWord(text)){beginScan();return;}
  auto c=choice(text);if(!c || *c>=view_.candidates.size()){say("编号无效，请重新选择");touch();return;}
  view_.selected_index=*c;view_.state=State::EnteringPassword;view_.grammar=Grammar::PasswordToken;touch();
  if(view_.candidates[*c].secured)say("请逐个输入密码字符，完成后说完成");
  else {view_.state=State::ConfirmingPassword;view_.grammar=Grammar::Confirmation;say("这是开放网络。确认连接请说确认提交");}
}
void Machine::password(const std::string& text){
  const auto n=compact(text);
  if(finishWord(text)){
    if(password_.size()<config_.min_password_length){say("密码长度不足，请继续输入");touch();return;}
    view_.state=State::ConfirmingPassword;view_.grammar=Grammar::Confirmation;touch();
    say("密码共"+std::to_string(password_.size())+"个字符。确认无误请说确认提交，重新输入请说重新输入");return;
  }
  if(n=="删除") {if(!password_.empty()){password_.back()=0;password_.pop_back();}view_.password_length=password_.size();say("当前长度"+std::to_string(password_.size()));touch();return;}
  if(n=="清空" || n=="重新输入"){wipePassword();say("已清空，请重新输入");touch();return;}
  auto ch=token(text);if(!ch){say("只接受单个字母、数字或支持的符号，请重说当前字符");touch();return;}
  if(password_.size()>=config_.max_password_length){say("已达到最大长度");touch();return;}
  password_.push_back(*ch);view_.password_length=password_.size();touch();say("已输入第"+std::to_string(password_.size())+"个字符");
}
void Machine::confirmation(const std::string& text){
  if(retryWord(text)){wipePassword();view_.state=State::EnteringPassword;view_.grammar=Grammar::PasswordToken;touch();say("已清空，请重新输入密码");return;}
  if(!confirmWord(text)){say("没有提交。确认请说确认提交，修改请说重新输入");touch();return;}
  if(!view_.selected_index || *view_.selected_index>=view_.candidates.size()){terminal(State::Error,"选网状态无效");return;}
  const auto& ap=view_.candidates[*view_.selected_index];
  const auto e=wifi_.submitCredentials(ap.ssid,password_.empty()?nullptr:password_.data(),password_.size());
  wipePassword();
  if(!e.request_id){terminal(State::Error,"凭据提交失败");return;}
  link_id_=e.request_id;deadline_ms_=clock_.nowMs()+config_.connect_timeout_ms;view_.grammar=Grammar::CancelOnly;applyLink(e);
}
void Machine::applyLink(LinkEvent e){
  if(!link_id_ || e.request_id!=link_id_)return;
  switch(e.status){
    case LinkStatus::CredentialsAccepted:view_.state=State::CredentialsAccepted;say("凭据已提交，正在连接");break;
    case LinkStatus::Wpa2Authenticating:view_.state=State::AuthenticatingWpa2;say("正在进行无线认证");break;
    case LinkStatus::Wpa2Authenticated:view_.state=State::AcquiringDhcp;say("无线认证成功，正在获取网络地址");break;
    case LinkStatus::DhcpAcquiring:view_.state=State::AcquiringDhcp;say("正在获取网络地址");break;
    case LinkStatus::IpReady:
      if(!usableIpv4(e.ipv4)){terminal(State::Error,"收到无效网络地址，连接结果未确认");break;}
      link_id_=0;wipePassword();view_.state=State::Completed;view_.grammar=Grammar::Wake;say("网络连接成功，地址为"+e.ipv4);break;
    case LinkStatus::WrongPassword:
      link_id_=0;wipePassword();view_.state=State::EnteringPassword;view_.grammar=Grammar::PasswordToken;touch();say("密码错误，请重新输入");break;
    case LinkStatus::NetworkNotFound:
      link_id_=0;wipePassword();view_.selected_index.reset();view_.state=State::ChoosingNetwork;view_.grammar=Grammar::NetworkChoice;touch();say("没有找到所选网络，请重新选择或重新扫描");break;
    case LinkStatus::Timeout:terminal(State::Idle,"连接超时");break;
    case LinkStatus::Cancelled:terminal(State::Idle,"连接已取消");break;
    case LinkStatus::Busy:terminal(State::Idle,"网络服务忙，请稍后重新唤醒");break;
    case LinkStatus::Unsupported:terminal(State::Idle,"当前不支持连接");break;
    case LinkStatus::Failed:terminal(State::Error,"网络连接失败");break;
  }
}
void Machine::poll(){
  const auto now=clock_.nowMs();
  if(deadline_ms_ && now>=deadline_ms_){
    if(scan_id_){wifi_.cancelScan(scan_id_);scan_id_=0;terminal(State::Idle,"扫描超时");}
    else if(link_id_){wifi_.cancelLink(link_id_);link_id_=0;terminal(State::Idle,"连接超时");}
    else if(view_.state!=State::WaitingWake && view_.state!=State::Idle && view_.state!=State::Completed && view_.state!=State::Error)terminal(State::Idle,"等待输入超时，已取消配置");
    return;
  }
  if(scan_id_)applyScan(wifi_.pollScan(scan_id_));
  else if(link_id_)applyLink(wifi_.pollLink(link_id_));
}
}

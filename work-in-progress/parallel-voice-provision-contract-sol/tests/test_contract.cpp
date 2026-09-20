#include "voice_provision_contract.hpp"
#include <cassert>
#include <iostream>

using namespace vela::voice_provision;
struct ClockFake:Clock{std::uint64_t now{};std::uint64_t nowMs()const noexcept override{return now;}};
struct VoiceFake:VoiceOutput{std::vector<std::string> out;bool speak(const std::string&s)override{out.push_back(s);return true;}void stop()noexcept override{}};
struct WifiFake:WifiService{
  ScanEvent scan{11,ScanStatus::Accepted,{}};LinkEvent link{21,LinkStatus::CredentialsAccepted,{}};
  int submits{},scan_cancels{},link_cancels{};std::size_t copied_len{};
  ScanEvent beginScan()noexcept override{return scan;}ScanEvent pollScan(std::uint64_t)noexcept override{return scan;}
  void cancelScan(std::uint64_t)noexcept override{++scan_cancels;}
  LinkEvent submitCredentials(const std::string&,const char*p,std::size_t n)noexcept override{++submits;copied_len=n;assert((n==0)==(p==nullptr));return link;}
  LinkEvent pollLink(std::uint64_t)noexcept override{return link;}void cancelLink(std::uint64_t)noexcept override{++link_cancels;}
};
struct F{ClockFake c;VoiceFake v;WifiFake w;Machine m{v,w,c};void choose(){m.start();m.ingest("你好，openvela");w.scan={11,ScanStatus::Ready,{{"Lab",-20,true},{"Guest",-50,false}}};m.poll();m.ingest("网络一");assert(m.snapshot().state==State::EnteringPassword);}void enter(){choose();for(auto*s:{"a","b","c","d","一","二","三","四"})m.ingest(s);m.ingest("完成");assert(m.snapshot().state==State::ConfirmingPassword);}};
int main(){
  {F f;f.enter();assert(f.w.submits==0);f.m.ingest("随便");assert(f.w.submits==0);f.m.ingest("确认提交");assert(f.w.submits==1&&f.w.copied_len==8);assert(f.m.snapshot().password_length==0);for(const auto&s:f.v.out)assert(s.find("abcd1234")==std::string::npos);}
  {F f;f.enter();f.m.ingest("否");assert(f.w.submits==0&&f.m.snapshot().state==State::EnteringPassword&&f.m.snapshot().password_length==0);}
  {F f;f.enter();f.m.ingest("确认");f.w.link={999,LinkStatus::IpReady,"192.0.2.8"};f.m.poll();assert(f.m.snapshot().state==State::CredentialsAccepted);f.w.link={21,LinkStatus::Wpa2Authenticating,{}};f.m.poll();assert(f.m.snapshot().state==State::AuthenticatingWpa2);f.w.link={21,LinkStatus::Wpa2Authenticated,{}};f.m.poll();assert(f.m.snapshot().state==State::AcquiringDhcp);f.w.link={21,LinkStatus::IpReady,"192.0.2.8"};f.m.poll();assert(f.m.snapshot().state==State::Completed);}
  {F f;f.enter();f.m.ingest("确认提交");f.w.link={21,LinkStatus::WrongPassword,{}};f.m.poll();assert(f.m.snapshot().state==State::EnteringPassword&&f.m.snapshot().password_length==0);}
  {F f;f.choose();f.c.now=60000;f.m.poll();assert(f.m.snapshot().state==State::Idle&&f.w.submits==0);}
  {F f;f.m.start();f.m.ingest("你好，openvela");f.m.ingest("取消");assert(f.w.scan_cancels==1&&f.m.snapshot().state==State::Idle);}
  {F f;f.enter();f.m.ingest("确认提交");f.c.now=30000;f.w.link={21,LinkStatus::IpReady,"192.0.2.8"};f.m.poll();assert(f.m.snapshot().state==State::Idle&&f.w.link_cancels==1);}
  {F f;f.m.start();f.m.ingest("你好，openvela");f.w.scan={11,ScanStatus::Ready,{{"Open",-10,false}}};f.m.poll();f.m.ingest("网络一");assert(f.m.snapshot().state==State::ConfirmingPassword&&f.w.submits==0);f.m.ingest("确认提交");assert(f.w.submits==1&&f.w.copied_len==0);}
  {F f;f.enter();f.m.ingest("确认提交");f.w.link={21,LinkStatus::IpReady,"0.0.0.0"};f.m.poll();assert(f.m.snapshot().state==State::Error);}
  {F f;f.enter();f.m.ingest("确认提交");f.w.link={21,LinkStatus::NetworkNotFound,{}};f.m.poll();assert(f.m.snapshot().state==State::ChoosingNetwork&&!f.m.snapshot().selected_index);}
  std::cout<<"10 contract scenarios passed; ports simulated; no credential value printed\n";
}

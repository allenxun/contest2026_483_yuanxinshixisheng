#include "tool_json.hpp"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string>
static unsigned allocations=0;
void* operator new(std::size_t n) {++allocations;if(auto p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void operator delete(void* p)noexcept{std::free(p);}
void operator delete(void* p,std::size_t)noexcept{std::free(p);}
#define CHECK(x) do { ++checks;if(!(x)){std::printf("FAIL line=%d\n",__LINE__);return 1;} }while(0)
int main() {
  unsigned checks=0;
  const std::string good=R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":1000})";
  const unsigned before=allocations;
  const auto first=robot_json::parse(good,42);
  CHECK(allocations==before);
  CHECK(first.request&&first.request->owner==42&&first.request->ttlMs==1000);
  CHECK(first.parse==robot_json::ParseError::None&&first.validation==robot::Error::None);
  CHECK(!robot_json::parse(good,0).request);
  std::array<std::string,4> parts={R"("version":1)",R"("tool":"WifiStatus")",R"("args":{})",R"("ttl_ms":30000)"};
  std::array<unsigned,4> order={0,1,2,3};
  do {
    std::string text="{ ";for(unsigned i=0;i<4;i++){if(i)text+=",\n";text+=parts[order[i]];}text+=" }\r\n";
    const auto r=robot_json::parse(text,99);
    CHECK(r.request&&r.request->tool==robot::Tool::WifiStatus&&r.request->owner==99);
  }while(std::next_permutation(order.begin(),order.end()));
  const char* bad[]={
    "", "{}", "[]", "null", "true", "1", "\"x\"",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":1,})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":1} {})",
    R"({"version":2,"tool":"Capabilities","args":{},"ttl_ms":1})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":0})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":30001})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":18446744073709551616})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":-1})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":-0})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":01})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":1.0})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":1e3})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":true})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":"1"})",
    R"({"version":1,"tool":"Capabilities","args":null,"ttl_ms":1})",
    R"({"version":1,"tool":"Capabilities","args":[],"ttl_ms":1})",
    R"({"version":1,"tool":"Capabilities","args":{"x":1},"ttl_ms":1})",
    R"({"version":1,"tool":"Capabilities","args":{"password":"secret"},"ttl_ms":1})",
    R"({"version":1,"version":1,"tool":"Capabilities","args":{}})",
    R"({"version":1,"tool":"Capabilities","owner":42,"ttl_ms":1})",
    R"({"version":1,"tool":"Capabilities","id":42,"ttl_ms":1})",
    R"({"version":1,"tool":"Capabilities","state":"Completed","ttl_ms":1})",
    R"({"version":1,"tool":"Capabilities","DeviceEvent":{},"ttl_ms":1})",
    R"({"version":1,"tool":"capabilities","args":{},"ttl_ms":1})",
    R"({"version":1,"tool":"\u0043apabilities","args":{},"ttl_ms":1})",
    R"({"version":1,"tool":"Capabilities","args":{},"ttl_ms":1}garbage)",
    R"({"version":1,"tool":"GimbalTarget","args":{"x":0,"x":1},"ttl_ms":1})",
    R"({"version":1,"tool":"GimbalTarget","args":{"x":801,"y":0},"ttl_ms":1})",
    R"({"version":1,"tool":"GimbalTarget","args":{"x":0,"y":-121},"ttl_ms":1})"
  };
  for(auto text:bad)CHECK(!robot_json::parse(text,42).request);
  for(auto tool: {"Photo","WifiScan","WifiConnect"}) {
    const auto r=robot_json::parse(std::string("{\"version\":1,\"tool\":\"")+tool+"\",\"args\":{},\"ttl_ms\":1}",42);
    CHECK(!r.request&&r.parse==robot_json::ParseError::None&&r.validation==robot::Error::Unsupported);
  }
  const auto disabled=robot_json::parse(R"({"version":1,"tool":"GimbalTarget","args":{"y":1030,"x":-800},"ttl_ms":1})",42);
  CHECK(!disabled.request&&disabled.validation==robot::Error::Disabled);
  CHECK(!robot_json::parse(std::string(257,' '),42).request);
  CHECK(robot_json::parse(good+std::string(256-good.size(),' '),42).request);
  CHECK(!robot_json::parse(good+std::string(1,'\0'),42).request);
  for(std::size_t n=0;n<good.size();++n)CHECK(!robot_json::parse(std::string_view(good.data(),n),42).request);
  // Every byte substitution: successful parses must still validate and retain owner.
  for(std::size_t i=0;i<good.size();++i)for(unsigned c=0;c<256;++c) {
    auto text=good;text[i]=static_cast<char>(c);const auto r=robot_json::parse(text,1234);
    CHECK(!r.request||(r.request->owner==1234&&robot::validate(*r.request).error==robot::Error::None));
  }
  robot::Dispatcher dispatcher;
  auto admitted=dispatcher.submit(*first.request,10);
  CHECK(admitted.key&&admitted.key->owner==42&&admitted.key->id==1);
  CHECK(dispatcher.inspect(*admitted.key)->state==robot::State::Accepted);
  CHECK(dispatcher.take(*admitted.key,11).has_value());
  CHECK(dispatcher.inspect(*admitted.key)->state==robot::State::Accepted);
  std::printf("tool JSON PASS checks=%u; parser allocated zero; no backend/event execution\n",checks);
}

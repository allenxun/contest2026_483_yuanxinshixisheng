#include "voicelink/parsers.hpp"
#include <cassert>
int main() {
  assert(voicelink::parseNetworkIndex("选择一")==1);
  assert(voicelink::parseNetworkIndex("选第二个")==2);
  assert(voicelink::parseNetworkIndex("选择网络三")==3);
  assert(!voicelink::parseNetworkIndex("选择一或者二"));
  assert(!voicelink::parseNetworkIndex("选择六"));
}

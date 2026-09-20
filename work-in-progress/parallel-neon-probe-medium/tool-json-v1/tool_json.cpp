#include "tool_json.hpp"
#include <limits>
namespace robot_json {
namespace {
struct Parser {
  std::string_view s; std::size_t p=0; ParseError e=ParseError::None;
  bool fail(ParseError x) { if(e==ParseError::None)e=x; return false; }
  void ws() { while(p<s.size() && (s[p]==' '||s[p]=='\t'||s[p]=='\r'||s[p]=='\n')) ++p; }
  bool take(char c) { ws();if(p==s.size()||s[p]!=c)return fail(ParseError::Syntax);++p;return true; }
  bool at(char c) { ws(); return p<s.size() && s[p]==c; }
  bool word(std::string_view& out) {
    if(!take('"'))return false;
    const auto start=p;
    while(p<s.size() && s[p]!='"') {
      const char c=s[p];
      if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_') || p-start>=32)
        return fail(ParseError::String);
      ++p;
    }
    if(p==s.size() || p==start)return fail(ParseError::String);
    out=s.substr(start,p-start);++p;return true;
  }
  bool integer(std::uint64_t& value, bool& negative) {
    ws();negative=false;value=0;
    if(p<s.size()&&s[p]=='-') {negative=true;++p;}
    if(p==s.size()||s[p]<'0'||s[p]>'9')return fail(ParseError::Number);
    const auto start=p;
    while(p<s.size()&&s[p]>='0'&&s[p]<='9') {
      const unsigned digit=static_cast<unsigned>(s[p]-'0');
      if(value>(std::numeric_limits<std::uint64_t>::max()-digit)/10)
        return fail(ParseError::Overflow);
      value=value*10+digit;++p;
    }
    if((p-start>1&&s[start]=='0')||(negative&&value==0))return fail(ParseError::Number);
    if(p<s.size()&&(s[p]=='.'||s[p]=='e'||s[p]=='E'))return fail(ParseError::Number);
    return true;
  }
  bool args(unsigned& fields, int& x, int& y) {
    if(!take('{'))return false;
    if(at('}'))return take('}');
    for(unsigned n=0;n<2;++n) {
      std::string_view key;
      if(!word(key)||!take(':'))return false;
      const unsigned bit=key=="x"?1:key=="y"?2:0;
      if(!bit)return fail(ParseError::UnknownField);
      if(fields&bit)return fail(ParseError::Duplicate);
      fields|=bit;
      std::uint64_t value;bool negative;
      if(!integer(value,negative))return false;
      // Bounds below are dispatcher target bounds and avoid narrowing overflow.
      const unsigned limit=bit==1?800:negative?120:1030;
      if(value>limit)return fail(ParseError::Schema);
      int v=static_cast<int>(value);if(negative)v=-v;
      if(bit==1)x=v;else y=v;
      if(at('}'))return take('}');
      if(!take(','))return false;
    }
    return fail(ParseError::Schema);
  }
};
} // namespace
Result parse(std::string_view input,std::uint64_t owner) noexcept {
  if(input.empty()||input.size()>maxInput)return {ParseError::Length,robot::Error::Invalid,{}};
  Parser p{input};unsigned fields=0,argFields=0;int x=0,y=0;
  std::uint64_t version=0,ttl=0;std::string_view tool;
  if(p.take('{')&&!p.at('}')) {
    for(unsigned n=0;n<4;++n) {
      std::string_view key;
      if(!p.word(key)||!p.take(':'))break;
      const unsigned bit=key=="version"?1:key=="tool"?2:key=="args"?4:key=="ttl_ms"?8:0;
      if(!bit){p.fail(ParseError::UnknownField);break;}
      if(fields&bit){p.fail(ParseError::Duplicate);break;}
      fields|=bit;
      bool ok=false;
      if(bit==2)ok=p.word(tool);
      else if(bit==4)ok=p.args(argFields,x,y);
      else {
        bool negative=false;std::uint64_t value=0;
        ok=p.integer(value,negative);
        if(ok&&negative)ok=p.fail(ParseError::Schema);
        if(bit==1)version=value;else ttl=value;
      }
      if(!ok)break;
      if(p.at('}'))break;
      if(n==3){p.fail(ParseError::Syntax);break;}
      if(!p.take(','))break;
    }
  }
  if(p.e==ParseError::None)p.take('}');
  p.ws();
  if(p.e==ParseError::None&&p.p!=input.size())p.fail(ParseError::Syntax);
  if(p.e==ParseError::None&&fields!=15)p.fail(ParseError::MissingField);
  if(p.e==ParseError::None&&version!=1)p.fail(ParseError::Version);
  if(p.e!=ParseError::None)return {p.e,robot::Error::Invalid,{}};
  robot::Tool selected;
  if(tool=="Capabilities")selected=robot::Tool::Capabilities;
  else if(tool=="WifiStatus")selected=robot::Tool::WifiStatus;
  else if(tool=="GimbalTarget")selected=robot::Tool::GimbalTarget;
  else if(tool=="Photo")selected=robot::Tool::Photo;
  else if(tool=="WifiScan")selected=robot::Tool::WifiScan;
  else if(tool=="WifiConnect")selected=robot::Tool::WifiConnect;
  else return {ParseError::UnknownTool,robot::Error::Unsupported,{}};
  if((selected==robot::Tool::GimbalTarget&&argFields!=3)||
     (selected!=robot::Tool::GimbalTarget&&argFields!=0))
    return {ParseError::Schema,robot::Error::Invalid,{}};
  robot::Args args=robot::NoArgs{};
  if(selected==robot::Tool::GimbalTarget)args=robot::Target{x,y};
  const robot::Request request{owner,selected,args,ttl};
  const auto validation=robot::validate(request);
  if(validation.error!=robot::Error::None)return {ParseError::None,validation.error,{}};
  return {ParseError::None,robot::Error::None,request};
}
} // namespace robot_json

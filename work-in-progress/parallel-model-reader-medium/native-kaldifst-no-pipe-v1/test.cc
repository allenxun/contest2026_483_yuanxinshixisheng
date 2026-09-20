#include "kaldifst/csrc/kaldi-io.h"
#include <cassert>
#include <cstdio>
#include <stdexcept>
#include <string>
int main() {
  kaldifst::Input in;
  kaldifst::Output out;
  assert(!in.Open("do-not-execute |")); assert(!in.IsOpen());
  assert(!out.Open("|do-not-execute", true, false)); assert(!out.IsOpen());
  bool caught=false;
  try { kaldifst::Input bad("do-not-execute |"); }
  catch(const std::runtime_error&) { caught=true; }
  assert(caught);
  caught=false;
  try { kaldifst::Output bad("|do-not-execute",true); }
  catch(const std::runtime_error&) { caught=true; }
  assert(caught);
  assert(out.Open("small.bin", true, false)); out.Stream()<<"abc123";
  assert(out.Close()); assert(!out.IsOpen());
  assert(in.Open("small.bin")); std::string s; in.Stream()>>s; assert(s=="abc123");
  assert(in.Close()==0); assert(!in.IsOpen());
  assert(!in.Open("absent-file.bin")); assert(!in.IsOpen());
  assert(in.Open("small.bin")); assert(!in.Open("do-not-execute |")); assert(!in.IsOpen());
  assert(out.Open("small.bin", true, false)); assert(!out.Open("|do-not-execute",true,false)); assert(!out.IsOpen());
  std::remove("small.bin");
  std::puts("PASS real Input/Output pipe rejection, constructor exceptions, ordinary file, reopen cleanup");
}

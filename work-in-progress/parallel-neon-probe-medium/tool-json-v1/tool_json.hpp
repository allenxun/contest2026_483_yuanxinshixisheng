#pragma once
#include "dispatcher.hpp"
#include <string_view>
#include <optional>
namespace robot_json {
enum class ParseError { None, Length, Syntax, String, Number, Overflow,
                        Duplicate, UnknownField, MissingField, Version, UnknownTool, Schema };
struct Result {
  ParseError parse;
  robot::Error validation;
  std::optional<robot::Request> request;
};
// No IDs/events are accepted or emitted. owner comes from trusted caller.
Result parse(std::string_view input, std::uint64_t trustedOwner) noexcept;
constexpr std::size_t maxInput = 256;
} // namespace robot_json

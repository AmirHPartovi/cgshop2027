#pragma once

#include <charconv>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace cgshop2027::json {

struct Value {
    enum Type { NUL, BOOL, NUMBER, STRING, ARRAY, OBJECT } type{NUL};
    double number{0};
    bool boolean{false};
    std::string string;
    std::string numberText;
    std::vector<Value> array;
    std::map<std::string, Value> object;

    const Value& at(const std::string& key) const {
        if (type != OBJECT) {
            throw std::runtime_error("expected JSON object while reading key: " + key);
        }
        const auto item = object.find(key);
        if (item == object.end()) {
            throw std::runtime_error("missing JSON key: " + key);
        }
        return item->second;
    }
};

class Parser {
    const std::string& source_;
    size_t position_{0};

    void whitespace() {
        while (position_ < source_.size() &&
               (source_[position_] == ' ' || source_[position_] == '\t' ||
                source_[position_] == '\n' || source_[position_] == '\r')) {
            ++position_;
        }
    }

    char peek() {
        if (position_ >= source_.size()) {
            throw std::runtime_error("unexpected end of JSON");
        }
        return source_[position_];
    }

    bool consume(char expected) {
        if (position_ < source_.size() && source_[position_] == expected) {
            ++position_;
            return true;
        }
        return false;
    }

    static void appendUtf8(std::string& output, uint32_t codepoint) {
        if (codepoint <= 0x7fU) {
            output.push_back(static_cast<char>(codepoint));
        } else if (codepoint <= 0x7ffU) {
            output.push_back(static_cast<char>(0xc0U | (codepoint >> 6U)));
            output.push_back(static_cast<char>(0x80U | (codepoint & 0x3fU)));
        } else if (codepoint <= 0xffffU) {
            output.push_back(static_cast<char>(0xe0U | (codepoint >> 12U)));
            output.push_back(static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3fU)));
            output.push_back(static_cast<char>(0x80U | (codepoint & 0x3fU)));
        } else {
            output.push_back(static_cast<char>(0xf0U | (codepoint >> 18U)));
            output.push_back(static_cast<char>(0x80U | ((codepoint >> 12U) & 0x3fU)));
            output.push_back(static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3fU)));
            output.push_back(static_cast<char>(0x80U | (codepoint & 0x3fU)));
        }
    }

    uint32_t hexQuad() {
        if (position_ + 4U > source_.size()) {
            throw std::runtime_error("incomplete JSON unicode escape");
        }
        uint32_t value = 0;
        for (int digit = 0; digit < 4; ++digit) {
            const char c = source_[position_++];
            value <<= 4U;
            if (c >= '0' && c <= '9') value |= static_cast<uint32_t>(c - '0');
            else if (c >= 'a' && c <= 'f') value |= static_cast<uint32_t>(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') value |= static_cast<uint32_t>(c - 'A' + 10);
            else throw std::runtime_error("invalid JSON unicode escape");
        }
        return value;
    }

    Value stringValue() {
        Value result;
        result.type = Value::STRING;
        ++position_;
        while (position_ < source_.size()) {
            const unsigned char c = static_cast<unsigned char>(source_[position_++]);
            if (c == '"') return result;
            if (c < 0x20U) throw std::runtime_error("unescaped control character in JSON string");
            if (c != '\\') {
                if (c < 0x80U) {
                    result.string.push_back(static_cast<char>(c));
                    continue;
                }
                uint32_t codepoint = 0;
                uint32_t minimum = 0;
                size_t continuationCount = 0;
                if (c >= 0xc2U && c <= 0xdfU) {
                    codepoint = c & 0x1fU;
                    minimum = 0x80U;
                    continuationCount = 1U;
                } else if (c >= 0xe0U && c <= 0xefU) {
                    codepoint = c & 0x0fU;
                    minimum = 0x800U;
                    continuationCount = 2U;
                } else if (c >= 0xf0U && c <= 0xf4U) {
                    codepoint = c & 0x07U;
                    minimum = 0x10000U;
                    continuationCount = 3U;
                } else {
                    throw std::runtime_error("invalid UTF-8 in JSON string");
                }
                if (position_ + continuationCount > source_.size()) {
                    throw std::runtime_error("incomplete UTF-8 in JSON string");
                }
                result.string.push_back(static_cast<char>(c));
                for (size_t i = 0; i < continuationCount; ++i) {
                    const unsigned char continuation =
                        static_cast<unsigned char>(source_[position_++]);
                    if ((continuation & 0xc0U) != 0x80U) {
                        throw std::runtime_error("invalid UTF-8 continuation byte");
                    }
                    result.string.push_back(static_cast<char>(continuation));
                    codepoint = (codepoint << 6U) | (continuation & 0x3fU);
                }
                if (codepoint < minimum || codepoint > 0x10ffffU ||
                    (codepoint >= 0xd800U && codepoint <= 0xdfffU)) {
                    throw std::runtime_error("invalid UTF-8 code point in JSON string");
                }
                continue;
            }
            if (position_ >= source_.size()) {
                throw std::runtime_error("incomplete JSON escape");
            }
            const char escaped = source_[position_++];
            switch (escaped) {
                case '"': result.string.push_back('"'); break;
                case '\\': result.string.push_back('\\'); break;
                case '/': result.string.push_back('/'); break;
                case 'b': result.string.push_back('\b'); break;
                case 'f': result.string.push_back('\f'); break;
                case 'n': result.string.push_back('\n'); break;
                case 'r': result.string.push_back('\r'); break;
                case 't': result.string.push_back('\t'); break;
                case 'u': {
                    uint32_t codepoint = hexQuad();
                    if (codepoint >= 0xd800U && codepoint <= 0xdbffU) {
                        if (position_ + 2U > source_.size() ||
                            source_[position_] != '\\' || source_[position_ + 1U] != 'u') {
                            throw std::runtime_error("unpaired JSON high surrogate");
                        }
                        position_ += 2U;
                        const uint32_t low = hexQuad();
                        if (low < 0xdc00U || low > 0xdfffU) {
                            throw std::runtime_error("invalid JSON surrogate pair");
                        }
                        codepoint = 0x10000U + ((codepoint - 0xd800U) << 10U) +
                                    (low - 0xdc00U);
                    } else if (codepoint >= 0xdc00U && codepoint <= 0xdfffU) {
                        throw std::runtime_error("unpaired JSON low surrogate");
                    }
                    appendUtf8(result.string, codepoint);
                    break;
                }
                default: throw std::runtime_error("invalid JSON escape");
            }
        }
        throw std::runtime_error("unterminated JSON string");
    }

    Value numberValue() {
        const size_t start = position_;
        consume('-');
        if (consume('0')) {
            if (position_ < source_.size() && source_[position_] >= '0' &&
                source_[position_] <= '9') {
                throw std::runtime_error("leading zero in JSON number");
            }
        } else {
            if (position_ >= source_.size() || source_[position_] < '1' ||
                source_[position_] > '9') {
                throw std::runtime_error("invalid JSON number");
            }
            while (position_ < source_.size() && source_[position_] >= '0' &&
                   source_[position_] <= '9') ++position_;
        }
        if (consume('.')) {
            const size_t fraction = position_;
            while (position_ < source_.size() && source_[position_] >= '0' &&
                   source_[position_] <= '9') ++position_;
            if (fraction == position_) throw std::runtime_error("invalid JSON fraction");
        }
        if (position_ < source_.size() &&
            (source_[position_] == 'e' || source_[position_] == 'E')) {
            ++position_;
            if (position_ < source_.size() &&
                (source_[position_] == '+' || source_[position_] == '-')) ++position_;
            const size_t exponent = position_;
            while (position_ < source_.size() && source_[position_] >= '0' &&
                   source_[position_] <= '9') ++position_;
            if (exponent == position_) throw std::runtime_error("invalid JSON exponent");
        }
        Value result;
        result.type = Value::NUMBER;
        result.numberText = source_.substr(start, position_ - start);
        try {
            size_t parsed = 0;
            result.number = std::stod(result.numberText, &parsed);
            if (parsed != result.numberText.size() || !std::isfinite(result.number)) {
                throw std::runtime_error("non-finite JSON number");
            }
        } catch (const std::exception&) {
            throw std::runtime_error("invalid or out-of-range JSON number");
        }
        return result;
    }

    Value value() {
        whitespace();
        const char c = peek();
        if (c == '{') return objectValue();
        if (c == '[') return arrayValue();
        if (c == '"') return stringValue();
        if (c == '-' || (c >= '0' && c <= '9')) return numberValue();
        for (const auto& literal : {std::string_view("true"), std::string_view("false"),
                                    std::string_view("null")}) {
            if (source_.compare(position_, literal.size(), literal) == 0) {
                position_ += literal.size();
                Value result;
                if (literal == "true" || literal == "false") {
                    result.type = Value::BOOL;
                    result.boolean = literal == "true";
                }
                return result;
            }
        }
        throw std::runtime_error("invalid JSON value");
    }

    Value arrayValue() {
        Value result;
        result.type = Value::ARRAY;
        ++position_;
        whitespace();
        if (consume(']')) return result;
        for (;;) {
            result.array.push_back(value());
            whitespace();
            if (consume(']')) return result;
            if (!consume(',')) throw std::runtime_error("expected comma in JSON array");
        }
    }

    Value objectValue() {
        Value result;
        result.type = Value::OBJECT;
        ++position_;
        whitespace();
        if (consume('}')) return result;
        for (;;) {
            whitespace();
            if (peek() != '"') throw std::runtime_error("expected JSON object key");
            std::string key = stringValue().string;
            whitespace();
            if (!consume(':')) throw std::runtime_error("expected colon in JSON object");
            auto inserted = result.object.emplace(std::move(key), value());
            if (!inserted.second) throw std::runtime_error("duplicate JSON object key");
            whitespace();
            if (consume('}')) return result;
            if (!consume(',')) throw std::runtime_error("expected comma in JSON object");
        }
    }

public:
    explicit Parser(const std::string& source) : source_(source) {}

    Value parse() {
        Value result = value();
        whitespace();
        if (position_ != source_.size()) throw std::runtime_error("trailing data after JSON value");
        return result;
    }
};

inline int integer(const Value& value, const std::string& field) {
    if (value.type != Value::NUMBER) {
        throw std::runtime_error(field + " must be an integer");
    }
    const std::string& token = value.numberText;
    const size_t exponentPosition = token.find_first_of("eE");
    const std::string_view mantissa(token.data(),
                                    exponentPosition == std::string::npos
                                        ? token.size()
                                        : exponentPosition);
    int exponent = 0;
    if (exponentPosition != std::string::npos) {
        std::string_view exponentText(token.data() + exponentPosition + 1U,
                                     token.size() - exponentPosition - 1U);
        if (!exponentText.empty() && exponentText.front() == '+') {
            exponentText.remove_prefix(1U);
        }
        const auto parsed = std::from_chars(exponentText.data(),
                                            exponentText.data() + exponentText.size(),
                                            exponent);
        if (parsed.ec != std::errc{} ||
            parsed.ptr != exponentText.data() + exponentText.size()) {
            throw std::runtime_error(field + " is outside the supported integer range");
        }
    }
    const bool negative = !mantissa.empty() && mantissa.front() == '-';
    std::string digits;
    digits.reserve(mantissa.size());
    size_t fractionalDigits = 0;
    bool afterDecimal = false;
    for (const char c : mantissa) {
        if (c == '-') continue;
        if (c == '.') {
            afterDecimal = true;
            continue;
        }
        digits.push_back(c);
        if (afterDecimal) ++fractionalDigits;
    }
    const size_t firstNonZero = digits.find_first_not_of('0');
    if (firstNonZero == std::string::npos) return 0;
    digits.erase(0, firstNonZero);
    const int64_t scale = static_cast<int64_t>(exponent) -
                          static_cast<int64_t>(fractionalDigits);
    if (scale < 0) {
        const auto trailingZeros = static_cast<size_t>(-scale);
        if (trailingZeros > digits.size() ||
            digits.compare(digits.size() - trailingZeros, trailingZeros,
                           std::string(trailingZeros, '0')) != 0) {
            throw std::runtime_error(field + " must be an integer");
        }
        digits.resize(digits.size() - trailingZeros);
    } else {
        if (scale > 10 ||
            digits.size() + static_cast<size_t>(scale) > 11U) {
            throw std::runtime_error(field + " is outside the supported integer range");
        }
        digits.append(static_cast<size_t>(scale), '0');
    }
    const std::string normalized = (negative ? "-" : "") + digits;
    int64_t parsedValue = 0;
    const auto parsed = std::from_chars(normalized.data(),
                                        normalized.data() + normalized.size(),
                                        parsedValue);
    if (parsed.ec != std::errc{} ||
        parsed.ptr != normalized.data() + normalized.size() ||
        parsedValue < std::numeric_limits<int>::min() ||
        parsedValue > std::numeric_limits<int>::max()) {
        throw std::runtime_error(field + " is outside the supported integer range");
    }
    return static_cast<int>(parsedValue);
}

inline std::string escapeString(const std::string& value) {
    static constexpr char hex[] = "0123456789abcdef";
    std::string result = "\"";
    for (const unsigned char c : value) {
        switch (c) {
            case '"': result += "\\\""; break;
            case '\\': result += "\\\\"; break;
            case '\b': result += "\\b"; break;
            case '\f': result += "\\f"; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default:
                if (c < 0x20U) {
                    result += "\\u00";
                    result.push_back(hex[c >> 4U]);
                    result.push_back(hex[c & 0x0fU]);
                } else {
                    result.push_back(static_cast<char>(c));
                }
        }
    }
    result.push_back('"');
    return result;
}

inline std::string stringify(const Value& value) {
    switch (value.type) {
        case Value::NUL: return "null";
        case Value::BOOL: return value.boolean ? "true" : "false";
        case Value::NUMBER: return value.numberText;
        case Value::STRING: return escapeString(value.string);
        case Value::ARRAY: {
            std::string result = "[";
            for (size_t i = 0; i < value.array.size(); ++i) {
                if (i != 0U) result += ',';
                result += stringify(value.array[i]);
            }
            result += ']';
            return result;
        }
        case Value::OBJECT: {
            std::string result = "{";
            size_t i = 0;
            for (const auto& item : value.object) {
                if (i++ != 0U) result += ',';
                result += escapeString(item.first);
                result += ':';
                result += stringify(item.second);
            }
            result += '}';
            return result;
        }
    }
    throw std::runtime_error("unknown JSON value type");
}

inline Value parseFile(const std::string& filename) {
    std::ifstream input(filename, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open " + filename);
    return Parser(std::string((std::istreambuf_iterator<char>(input)), {})).parse();
}

}  // namespace cgshop2027::json

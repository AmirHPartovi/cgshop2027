#include "utils/Logger.h"

#include <chrono>
#include <cstdlib>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <thread>
#include <utility>

namespace cgshop2027 {

Logger& Logger::instance() {
    static Logger logger;
    return logger;
}

Logger::Logger() {
    const char* configuredLevel = std::getenv("CGSHOP_LOG_LEVEL");
    if (configuredLevel == nullptr) return;
    const std::string level(configuredLevel);
    if (level == "debug" || level == "DEBUG") {
        minimum_level_ = LogLevel::Debug;
    } else if (level == "warning" || level == "warn" || level == "WARN") {
        minimum_level_ = LogLevel::Warning;
    } else if (level == "error" || level == "ERROR") {
        minimum_level_ = LogLevel::Error;
    } else if (level == "info" || level == "INFO") {
        minimum_level_ = LogLevel::Info;
    }
}

Logger& Logger::getInstance() { return instance(); }

void Logger::setLevel(LogLevel level) {
    std::lock_guard<std::mutex> lock(mutex_);
    minimum_level_ = level;
}

void Logger::setLogLevel(LogLevel level) { setLevel(level); }
LogLevel Logger::level() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return minimum_level_;
}
void Logger::debug(const std::string& message) {
    log(LogLevel::Debug, "", message);
}
void Logger::info(const std::string& message) {
    log(LogLevel::Info, "", message);
}
void Logger::warning(const std::string& message) {
    log(LogLevel::Warning, "", message);
}
void Logger::error(const std::string& message) {
    log(LogLevel::Error, "", message);
}
void Logger::debug(const std::string& component, const std::string& message) {
    log(LogLevel::Debug, component, message);
}
void Logger::info(const std::string& component, const std::string& message) {
    log(LogLevel::Info, component, message);
}
void Logger::warning(const std::string& component,
                     const std::string& message) {
    log(LogLevel::Warning, component, message);
}
void Logger::error(const std::string& component, const std::string& message) {
    log(LogLevel::Error, component, message);
}

void Logger::log(LogLevel level, const std::string& component,
                 const std::string& message) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (static_cast<int>(level) < static_cast<int>(minimum_level_)) {
        return;
    }
    std::ostream& output = level == LogLevel::Error ? std::cerr : std::clog;
    const char* label = level == LogLevel::Debug
                            ? "DEBUG"
                            : (level == LogLevel::Info
                                   ? "INFO"
                                   : (level == LogLevel::Warning ? "WARN"
                                                                 : "ERROR"));
    const auto now = std::chrono::system_clock::now();
    const std::time_t time = std::chrono::system_clock::to_time_t(now);
    std::tm localTime{};
#if defined(_WIN32)
    localtime_s(&localTime, &time);
#else
    localtime_r(&time, &localTime);
#endif
    output << '[' << std::put_time(&localTime, "%Y-%m-%dT%H:%M:%S") << ']'
           << '[' << label << ']'
           << "[tid=" << std::this_thread::get_id() << ']';
    if (!component.empty()) output << '[' << component << ']';
    output << ' ' << message << '\n';
}

LogScope::LogScope(std::string component, std::string operation)
    : component_(std::move(component)),
      operation_(std::move(operation)),
      started_(std::chrono::steady_clock::now()) {
    Logger::instance().debug(component_, "begin " + operation_);
}

LogScope::~LogScope() {
    const double elapsed = std::chrono::duration<double>(
                               std::chrono::steady_clock::now() - started_)
                               .count();
    std::ostringstream message;
    message << "end " << operation_ << " duration=" << std::fixed
            << std::setprecision(3) << elapsed << "s";
    Logger::instance().debug(component_, message.str());
}

}  // namespace cgshop2027

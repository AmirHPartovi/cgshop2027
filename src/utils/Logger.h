#pragma once

#include <chrono>
#include <mutex>
#include <string>

namespace cgshop2027 {

enum class LogLevel { Debug, Info, Warning, Error };

class Logger {
public:
    static Logger& instance();
    static Logger& getInstance();
    void setLevel(LogLevel level);
    void setLogLevel(LogLevel level);
    LogLevel level() const;
    void debug(const std::string& message);
    void info(const std::string& message);
    void warning(const std::string& message);
    void error(const std::string& message);
    void debug(const std::string& component, const std::string& message);
    void info(const std::string& component, const std::string& message);
    void warning(const std::string& component, const std::string& message);
    void error(const std::string& component, const std::string& message);

private:
    Logger();
    void log(LogLevel level, const std::string& component,
             const std::string& message);
    mutable std::mutex mutex_;
    LogLevel minimum_level_{LogLevel::Info};
};

class LogScope {
public:
    LogScope(std::string component, std::string operation);
    ~LogScope();

    LogScope(const LogScope&) = delete;
    LogScope& operator=(const LogScope&) = delete;

private:
    std::string component_;
    std::string operation_;
    std::chrono::steady_clock::time_point started_;
};

}  // namespace cgshop2027

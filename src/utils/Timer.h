#pragma once

#include <chrono>

namespace cgshop2027 {

class Timer {
public:
    Timer() : start_(Clock::now()) {}
    double elapsedSeconds() const {
        return std::chrono::duration<double>(Clock::now() - start_).count();
    }
    bool expired(double timeout_seconds) const {
        return timeout_seconds >= 0.0 && elapsedSeconds() >= timeout_seconds;
    }

private:
    using Clock = std::chrono::steady_clock;
    Clock::time_point start_;
};

}  // namespace cgshop2027

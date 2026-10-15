#pragma once

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <stdexcept>

namespace cgshop2027 {

class ExecutionCancelled final : public std::runtime_error {
public:
    ExecutionCancelled()
        : std::runtime_error("execution deadline reached or cancellation requested") {}
};

class ExecutionControl {
public:
    using Clock = std::chrono::steady_clock;

    static ExecutionControl& instance();

    void setDeadline(Clock::time_point deadline) noexcept;
    void clearDeadline() noexcept;
    void cancel() noexcept;
    void setActiveChildProcess(int processId) noexcept;
    static void killActiveChildProcess() noexcept;
    bool cancelled() const noexcept;
    double remainingSeconds() const noexcept;
    void checkpoint() const;

private:
    ExecutionControl() = default;
    std::atomic<int64_t> deadlineNanoseconds_{0};
    mutable std::atomic<bool> cancelled_{false};
};

}  // namespace cgshop2027

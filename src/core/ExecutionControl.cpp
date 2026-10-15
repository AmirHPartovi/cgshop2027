#include "core/ExecutionControl.h"

#include <algorithm>
#ifndef _WIN32
#include <signal.h>
#include <sys/types.h>
#endif

namespace cgshop2027 {
namespace {
#ifndef _WIN32
volatile std::sig_atomic_t activeChildProcess = 0;
#endif
}

ExecutionControl& ExecutionControl::instance() {
    static ExecutionControl control;
    return control;
}

void ExecutionControl::setDeadline(Clock::time_point deadline) noexcept {
    deadlineNanoseconds_.store(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            deadline.time_since_epoch()).count(),
        std::memory_order_release);
    cancelled_.store(false, std::memory_order_release);
}

void ExecutionControl::clearDeadline() noexcept {
    deadlineNanoseconds_.store(0, std::memory_order_release);
    cancelled_.store(false, std::memory_order_release);
}

void ExecutionControl::cancel() noexcept {
    cancelled_.store(true, std::memory_order_release);
}

void ExecutionControl::setActiveChildProcess(int processId) noexcept {
#ifndef _WIN32
    activeChildProcess = static_cast<std::sig_atomic_t>(processId);
#else
    (void)processId;
#endif
}

void ExecutionControl::killActiveChildProcess() noexcept {
#ifndef _WIN32
    const std::sig_atomic_t processId = activeChildProcess;
    if (processId > 0) {
        (void)kill(-static_cast<pid_t>(processId), SIGKILL);
        (void)kill(static_cast<pid_t>(processId), SIGKILL);
    }
#endif
}

bool ExecutionControl::cancelled() const noexcept {
    if (cancelled_.load(std::memory_order_acquire)) return true;
    const int64_t deadline = deadlineNanoseconds_.load(std::memory_order_acquire);
    if (deadline == 0) return false;
    const int64_t now = std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now().time_since_epoch()).count();
    if (now < deadline) return false;
    cancelled_.store(true, std::memory_order_release);
    return true;
}

double ExecutionControl::remainingSeconds() const noexcept {
    const int64_t deadline = deadlineNanoseconds_.load(std::memory_order_acquire);
    if (deadline == 0) return -1.0;
    const int64_t now = std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now().time_since_epoch()).count();
    if (now >= deadline || cancelled_.load(std::memory_order_acquire)) return 0.0;
    return static_cast<double>(deadline - now) / 1'000'000'000.0;
}

void ExecutionControl::checkpoint() const {
    if (cancelled()) throw ExecutionCancelled();
}

}  // namespace cgshop2027

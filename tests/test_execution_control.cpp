#include "core/ExecutionControl.h"

#include <cassert>
#include <atomic>
#include <chrono>
#include <thread>
#ifndef _WIN32
#include <cerrno>
#include <csignal>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

int main() {
    using namespace std::chrono_literals;
    auto& control = cgshop2027::ExecutionControl::instance();

    control.clearDeadline();
    control.setDeadline(cgshop2027::ExecutionControl::Clock::now() + 15ms);
    assert(control.remainingSeconds() > 0.0);
    std::atomic<bool> loopInterrupted{false};
    std::atomic<unsigned int> iterations{0};
    std::thread worker([&] {
        try {
            for (;;) {
                control.checkpoint();
                ++iterations;
            }
        } catch (const cgshop2027::ExecutionCancelled&) {
            loopInterrupted.store(true);
        }
    });
    worker.join();
    assert(loopInterrupted.load());
    assert(iterations.load() > 0);
    assert(control.cancelled());

    control.setDeadline(cgshop2027::ExecutionControl::Clock::now() + 1s);
    control.cancel();
    assert(control.cancelled());
    bool cancellationCheckpointThrew = false;
    try {
        control.checkpoint();
    } catch (const cgshop2027::ExecutionCancelled&) {
        cancellationCheckpointThrew = true;
    }
    assert(cancellationCheckpointThrew);

    control.clearDeadline();
    assert(!control.cancelled());
#ifndef _WIN32
    const pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        (void)setpgid(0, 0);
        for (;;) pause();
    }
    (void)setpgid(child, child);
    control.setActiveChildProcess(static_cast<int>(child));
    cgshop2027::ExecutionControl::killActiveChildProcess();
    int status = 0;
    pid_t waited = -1;
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    control.setActiveChildProcess(0);
    assert(waited == child);
    assert(WIFSIGNALED(status));
    assert(WTERMSIG(status) == SIGKILL);
#endif
    return 0;
}

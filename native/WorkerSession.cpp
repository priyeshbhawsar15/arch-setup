#include "WorkerSession.h"
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/eventfd.h>
#include <sys/wait.h>
#include <signal.h>
#include <variant>
#include <deque>
#include <map>
#include <vector>
#include <iostream>
#include <cstring>
#include <cerrno>

namespace locklive {

struct ReleaseCmd {
    FrameRef frame;
    ConsumerKey key;
    uint32_t consumerIdx = 0;
    SampleState sampled = SampleState::Unsampled;
    lockframe::Fd fence;
};

struct VisibilityCmd {
    uint32_t enabledStreamsMask = 0;
    bool freeze = false;
};

struct StopCmd {};

using Command = std::variant<ReleaseCmd, VisibilityCmd, StopCmd>;

struct WorkerSession::Impl : public std::enable_shared_from_this<WorkerSession::Impl> {
    EpochId epochId = 0;
    SessionConfig config;
    SessionTimeouts timeouts;

    std::weak_ptr<WorkerSession> selfSession;

    std::atomic<SessionState> state{SessionState::Pending};
    std::atomic<bool> stopped{false};
    std::atomic<bool> queueOverflow{false};

    int socketFd = -1;
    int wakeFd = -1;
    pid_t pid = -1;

    std::thread ipcThread;

    std::mutex queueMutex;
    std::deque<Command> commandQueue;

    mutable std::mutex bufferMutex;
    struct StoredBuffer {
        lockframe::Buffer desc{};
        int fd = -1;
    };
    std::map<std::pair<uint32_t, uint32_t>, StoredBuffer> buffers;

    struct Obligation {
        uint32_t stream = 0;
        uint32_t slot = 0;
        uint64_t sequence = 0;
        uint32_t expectedConsumers = 0;
        uint32_t releasedConsumers = 0;
    };
    std::mutex obligationMutex;
    std::map<std::tuple<uint32_t, uint32_t, uint64_t>, Obligation> obligations;

    struct TrackedFence {
        int fd = -1;
        std::chrono::steady_clock::time_point deadline;
    };
    std::vector<TrackedFence> trackedFences;

    WorkerSession::FrameCallback frameCallback;
    WorkerSession::StateCallback stateCallback;

    Impl(EpochId id, SessionConfig cfg, SessionTimeouts to)
        : epochId(id), config(std::move(cfg)), timeouts(to) {
        wakeFd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
    }

    ~Impl() {
        requestStop();
        detachThreadIfRunning();
        cleanup();
    }

    void wake() {
        if (wakeFd >= 0) {
            uint64_t val = 1;
            (void)write(wakeFd, &val, sizeof(val));
        }
    }

    void requestStop() {
        if (stopped.exchange(true)) return;
        {
            std::lock_guard<std::mutex> lock(queueMutex);
            commandQueue.push_back(StopCmd{});
        }
        wake();
    }

    void detachThreadIfRunning() {
        if (ipcThread.joinable()) {
            ipcThread.detach();
        }
    }

    void failEpoch(SessionState errState, const std::string& err) {
        state = errState;
        if (stateCallback) {
            stateCallback(errState, err);
        }
        stopped = true;
    }

    void cleanup() {
        if (socketFd >= 0) {
            try {
                // Try sending Stop packet
                auto stopPkt = lockframe::packet(lockframe::Type::Stop, lockframe::Header{}, epochId);
                stopPkt.header.size = 0;
                stopPkt.payload.clear();
                lockframe::sendPacket(socketFd, stopPkt);
            } catch (...) {}
            shutdown(socketFd, SHUT_RDWR);
            close(socketFd);
            socketFd = -1;
        }

        if (wakeFd >= 0) {
            close(wakeFd);
            wakeFd = -1;
        }

        for (auto& tf : trackedFences) {
            if (tf.fd >= 0) {
                close(tf.fd);
                tf.fd = -1;
            }
        }
        trackedFences.clear();

        {
            std::lock_guard<std::mutex> lock(bufferMutex);
            for (auto& kv : buffers) {
                if (kv.second.fd >= 0) {
                    close(kv.second.fd);
                    kv.second.fd = -1;
                }
            }
            buffers.clear();
        }

        if (pid > 0) {
            int status = 0;
            pid_t res = waitpid(pid, &status, WNOHANG);
            if (res != pid) {
                kill(pid, SIGTERM);
                auto termDeadline = std::chrono::steady_clock::now() + timeouts.stopGraceTimeout;
                while (std::chrono::steady_clock::now() < termDeadline) {
                    res = waitpid(pid, &status, WNOHANG);
                    if (res == pid) break;
                    std::this_thread::sleep_for(std::chrono::milliseconds(20));
                }
                if (res != pid) {
                    kill(pid, SIGKILL);
                    auto killDeadline = std::chrono::steady_clock::now() + timeouts.stopKillTimeout;
                    while (std::chrono::steady_clock::now() < killDeadline) {
                        res = waitpid(pid, &status, WNOHANG);
                        if (res == pid) break;
                        std::this_thread::sleep_for(std::chrono::milliseconds(20));
                    }
                    if (res != pid) {
                        waitpid(pid, &status, 0);
                    }
                }
            }
            pid = -1;
        }

        state = SessionState::Retired;
        if (stateCallback) {
            stateCallback(SessionState::Retired, "");
        }
    }

    void handleWakeQueue() {
        if (wakeFd >= 0) {
            uint64_t val = 0;
            while (read(wakeFd, &val, sizeof(val)) > 0) {}
        }

        std::deque<Command> localQueue;
        {
            std::lock_guard<std::mutex> lock(queueMutex);
            localQueue.swap(commandQueue);
        }

        for (auto& cmd : localQueue) {
            if (std::holds_alternative<StopCmd>(cmd)) {
                stopped = true;
                return;
            } else if (std::holds_alternative<VisibilityCmd>(cmd)) {
                auto& v = std::get<VisibilityCmd>(cmd);
                lockframe::Visibility payload{v.enabledStreamsMask, v.freeze ? 1u : 0u};
                auto p = lockframe::packet(lockframe::Type::Visibility, payload, epochId);
                try {
                    lockframe::sendPacket(socketFd, p);
                } catch (...) {
                    failEpoch(SessionState::Error, "Visibility send failed");
                    return;
                }
            } else if (std::holds_alternative<ReleaseCmd>(cmd)) {
                auto& r = std::get<ReleaseCmd>(cmd);
                auto oblKey = std::make_tuple(r.frame.stream, r.frame.slot, r.frame.sequence);
                bool validObligation = false;
                {
                    std::lock_guard<std::mutex> lock(obligationMutex);
                    auto it = obligations.find(oblKey);
                    if (it != obligations.end()) {
                        if (!(it->second.releasedConsumers & (1u << r.consumerIdx))) {
                            it->second.releasedConsumers |= (1u << r.consumerIdx);
                            validObligation = true;
                            if (it->second.releasedConsumers == it->second.expectedConsumers) {
                                obligations.erase(it);
                            }
                        }
                    }
                }

                if (!validObligation) {
                    // Stale or duplicate release: drop and close FD
                    continue;
                }

                lockframe::Release payload{r.frame.stream, r.frame.slot, r.consumerIdx,
                                           (r.sampled == SampleState::Sampled ? 1u : 0u),
                                           r.frame.sequence};
                auto p = lockframe::packet(lockframe::Type::Release, payload, epochId);
                if (r.sampled == SampleState::Sampled) {
                    int trackFd = dup(r.fence.get());
                    trackedFences.push_back({trackFd, std::chrono::steady_clock::now() + timeouts.fenceTimeout});
                    p.fds.push_back(std::move(r.fence));
                }
                try {
                    lockframe::sendPacket(socketFd, p);
                } catch (...) {
                    failEpoch(SessionState::Error, "Release send failed");
                    return;
                }
            }
        }
    }

    void runIpcLoop() {
        state = SessionState::Starting;
        if (stateCallback) stateCallback(SessionState::Starting, "");

        // Phase 1: Handshake
        auto handshakeDeadline = std::chrono::steady_clock::now() + timeouts.handshakeTimeout;
        while (!stopped.load()) {
            auto now = std::chrono::steady_clock::now();
            if (now >= handshakeDeadline) {
                failEpoch(SessionState::Error, "Handshake timeout");
                cleanup();
                return;
            }
            int timeoutMs = static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(handshakeDeadline - now).count());
            if (timeoutMs < 0) timeoutMs = 0;

            pollfd pfd[2] = {
                {socketFd, POLLIN, 0},
                {wakeFd, POLLIN, 0}
            };
            int pr = poll(pfd, 2, timeoutMs);
            if (pr < 0) {
                if (errno == EINTR) continue;
                failEpoch(SessionState::Error, "Poll failed in handshake");
                cleanup();
                return;
            }
            if (pr == 0) {
                failEpoch(SessionState::Error, "Handshake timeout");
                cleanup();
                return;
            }
            if (pfd[1].revents & POLLIN) {
                handleWakeQueue();
                if (stopped.load()) { cleanup(); return; }
            }
            if (pfd[0].revents & (POLLIN | POLLERR | POLLHUP)) {
                break;
            }
        }

        if (stopped.load()) { cleanup(); return; }

        lockframe::Packet helloPkt;
        try {
            helloPkt = lockframe::receivePacket(socketFd);
        } catch (const std::exception& e) {
            failEpoch(SessionState::Error, std::string("Receive Hello failed: ") + e.what());
            cleanup();
            return;
        }

        if (helloPkt.header.type != lockframe::Type::Hello) {
            failEpoch(SessionState::Error, "Expected Hello packet");
            cleanup();
            return;
        }

        // Send Configure packet
        lockframe::Configure cfg{};
        cfg.count = config.streams.size();
        cfg.fps = config.fps;
        for (size_t i = 0; i < config.streams.size(); ++i) {
            cfg.streams[i].id = config.streams[i].id;
            cfg.streams[i].width = config.streams[i].width;
            cfg.streams[i].height = config.streams[i].height;
            cfg.streams[i].consumers = config.streams[i].consumers;
        }
        auto cfgPkt = lockframe::packet(lockframe::Type::Configure, cfg, epochId);
        try {
            lockframe::sendPacket(socketFd, cfgPkt);
        } catch (const std::exception& e) {
            failEpoch(SessionState::Error, std::string("Send Configure failed: ") + e.what());
            cleanup();
            return;
        }

        // Phase 2: Buffers
        uint32_t expectedBuffers = config.streams.size() * 3;
        uint32_t receivedBuffers = 0;
        auto buffersDeadline = std::chrono::steady_clock::now() + timeouts.buffersTimeout;

        while (receivedBuffers < expectedBuffers && !stopped.load()) {
            auto now = std::chrono::steady_clock::now();
            if (now >= buffersDeadline) {
                failEpoch(SessionState::Error, "Buffers timeout");
                cleanup();
                return;
            }
            int timeoutMs = static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(buffersDeadline - now).count());
            if (timeoutMs < 0) timeoutMs = 0;

            pollfd pfd[2] = {
                {socketFd, POLLIN, 0},
                {wakeFd, POLLIN, 0}
            };
            int pr = poll(pfd, 2, timeoutMs);
            if (pr < 0) {
                if (errno == EINTR) continue;
                failEpoch(SessionState::Error, "Poll failed in buffers phase");
                cleanup();
                return;
            }
            if (pr == 0) {
                failEpoch(SessionState::Error, "Buffers timeout");
                cleanup();
                return;
            }
            if (pfd[1].revents & POLLIN) {
                handleWakeQueue();
                if (stopped.load()) { cleanup(); return; }
            }
            if (pfd[0].revents & (POLLIN | POLLERR | POLLHUP)) {
                lockframe::Packet bufPkt;
                try {
                    bufPkt = lockframe::receivePacket(socketFd);
                } catch (const std::exception& e) {
                    failEpoch(SessionState::Error, std::string("Receive Buffer failed: ") + e.what());
                    cleanup();
                    return;
                }

                if (bufPkt.header.type == lockframe::Type::Error) {
                    failEpoch(SessionState::Error, "Worker sent Error during buffer import");
                    cleanup();
                    return;
                }
                if (bufPkt.header.type != lockframe::Type::Buffer) {
                    failEpoch(SessionState::Error, "Expected Buffer packet");
                    cleanup();
                    return;
                }

                auto b = bufPkt.as<lockframe::Buffer>();
                if (bufPkt.fds.empty() || bufPkt.fds[0].get() < 0) {
                    failEpoch(SessionState::Error, "Buffer packet missing FD");
                    cleanup();
                    return;
                }

                {
                    std::lock_guard<std::mutex> lock(bufferMutex);
                    buffers[{b.stream, b.slot}] = StoredBuffer{b, dup(bufPkt.fds[0].get())};
                }
                receivedBuffers++;
            }
        }

        if (stopped.load()) { cleanup(); return; }

        // Phase 3: Live Frames & Releases
        state = SessionState::Live;
        if (stateCallback) stateCallback(SessionState::Live, "");

        auto firstFrameDeadline = std::chrono::steady_clock::now() + timeouts.firstFrameTimeout;
        bool receivedFirstFrame = false;

        while (!stopped.load()) {
            if (queueOverflow.load()) {
                failEpoch(SessionState::Error, "Queue overflow (> 64 packets)");
                break;
            }

            auto now = std::chrono::steady_clock::now();
            if (!receivedFirstFrame && now >= firstFrameDeadline) {
                failEpoch(SessionState::Error, "First visible frame timeout");
                break;
            }

            // Check tracked fences deadlines
            bool fenceTimedOut = false;
            for (const auto& tf : trackedFences) {
                if (now >= tf.deadline) {
                    fenceTimedOut = true;
                    break;
                }
            }
            if (fenceTimedOut) {
                failEpoch(SessionState::Error, "Submitted release fence deadline expired");
                break;
            }

            std::vector<pollfd> pfds;
            pfds.push_back({socketFd, POLLIN, 0});
            pfds.push_back({wakeFd, POLLIN, 0});
            for (const auto& tf : trackedFences) {
                pfds.push_back({tf.fd, POLLIN, 0});
            }

            // Calculate poll timeout
            int minTimeoutMs = 100;
            if (!receivedFirstFrame) {
                int ms = static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(firstFrameDeadline - now).count());
                if (ms >= 0 && ms < minTimeoutMs) minTimeoutMs = ms;
            }
            for (const auto& tf : trackedFences) {
                int ms = static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(tf.deadline - now).count());
                if (ms >= 0 && ms < minTimeoutMs) minTimeoutMs = ms;
            }

            int pr = poll(pfds.data(), pfds.size(), minTimeoutMs);
            if (pr < 0) {
                if (errno == EINTR) continue;
                failEpoch(SessionState::Error, "Poll failed in live phase");
                break;
            }

            // Check wakeFd
            if (pfds[1].revents & POLLIN) {
                handleWakeQueue();
                if (stopped.load()) break;
            }

            // Check tracked fences
            std::vector<TrackedFence> remainingFences;
            for (size_t i = 0; i < trackedFences.size(); ++i) {
                size_t pfdIdx = 2 + i;
                if (pfds[pfdIdx].revents & POLLIN) {
                    // Fence signaled cleanly!
                    close(trackedFences[i].fd);
                } else if (pfds[pfdIdx].revents & (POLLERR | POLLHUP | POLLNVAL)) {
                    failEpoch(SessionState::Error, "Release fence error");
                    stopped = true;
                    close(trackedFences[i].fd);
                    break;
                } else {
                    remainingFences.push_back(trackedFences[i]);
                }
            }
            trackedFences.swap(remainingFences);
            if (stopped.load()) break;

            // Check socketFd
            if (pfds[0].revents & (POLLIN | POLLERR | POLLHUP)) {
                lockframe::Packet pkt;
                try {
                    pkt = lockframe::receivePacket(socketFd);
                } catch (...) {
                    failEpoch(SessionState::Error, "Worker connection closed or error");
                    break;
                }

                if (pkt.header.type == lockframe::Type::Frame) {
                    receivedFirstFrame = true;
                    auto f = pkt.as<lockframe::Frame>();

                    if (!pkt.fds.empty() && pkt.fds[0].get() >= 0) {
                        int rFence = pkt.fds[0].get();
                        pollfd rfPfd{rFence, POLLIN, 0};
                        int rfRes = poll(&rfPfd, 1, static_cast<int>(timeouts.fenceTimeout.count()));
                        if (rfRes <= 0 || (rfPfd.revents & (POLLERR | POLLNVAL))) {
                            failEpoch(SessionState::Error, "Ready fence timeout or error");
                            break;
                        }
                    }

                    // Check obligations bound
                    {
                        std::lock_guard<std::mutex> lock(obligationMutex);
                        if (obligations.size() >= 48) {
                            failEpoch(SessionState::Error, "Obligations overflow (> 48)");
                            break;
                        }

                        uint32_t expMask = 0;
                        for (const auto& c : config.consumers) {
                            if (c.stream == f.stream) {
                                expMask |= (1u << c.id);
                            }
                        }
                        obligations[{f.stream, f.slot, pkt.header.sequence}] =
                            Obligation{f.stream, f.slot, pkt.header.sequence, expMask, 0};
                    }

                    StoredBuffer sb;
                    {
                        std::lock_guard<std::mutex> lock(bufferMutex);
                        auto it = buffers.find({f.stream, f.slot});
                        if (it != buffers.end()) sb = it->second;
                    }

                    if (frameCallback && sb.fd >= 0) {
                        FrameRef fr{selfSession.lock(), f.stream, f.slot, pkt.header.sequence};
                        frameCallback(fr, dup(sb.fd), sb.desc);
                    }
                } else if (pkt.header.type == lockframe::Type::Error) {
                    failEpoch(SessionState::Error, "Worker error packet");
                    break;
                } else if (pkt.header.type == lockframe::Type::Stop) {
                    stopped = true;
                    break;
                }
            }
        }

        cleanup();
    }
};

WorkerSession::WorkerSession(EpochId id, SessionConfig config, SessionTimeouts timeouts)
    : m_impl(std::make_shared<Impl>(id, std::move(config), timeouts)) {}

WorkerSession::~WorkerSession() {
    if (m_impl) {
        m_impl->requestStop();
        m_impl->detachThreadIfRunning();
    }
}

EpochId WorkerSession::epochId() const {
    return m_impl ? m_impl->epochId : 0;
}

const SessionConfig& WorkerSession::config() const {
    static const SessionConfig emptyConfig{};
    return m_impl ? m_impl->config : emptyConfig;
}

SessionState WorkerSession::state() const {
    return m_impl ? m_impl->state.load() : SessionState::Retired;
}

size_t WorkerSession::pendingObligations() const {
    if (!m_impl) return 0;
    std::lock_guard<std::mutex> lock(m_impl->obligationMutex);
    return m_impl->obligations.size();
}

bool WorkerSession::start(int socketFd, pid_t pid) {
    if (!m_impl || socketFd < 0) return false;
    m_impl->socketFd = socketFd;
    m_impl->pid = pid;
    m_impl->selfSession = shared_from_this();

    // Set socket to non-blocking
    int flags = fcntl(socketFd, F_GETFL, 0);
    if (flags >= 0) {
        fcntl(socketFd, F_SETFL, flags | O_NONBLOCK);
    }

    std::shared_ptr<Impl> impl = m_impl;
    m_impl->ipcThread = std::thread([impl]() {
        impl->runIpcLoop();
    });
    return true;
}

void WorkerSession::release(FrameRef frame, ConsumerKey key, SampleState sampled, lockframe::Fd fence) {
    if (!m_impl) return;

    if (!frame.epoch || frame.epoch.get() != this) {
        // Frame does not belong to this epoch: reject and close fence
        return;
    }
    if (m_impl->stopped.load()) {
        // Endpoint stopped: close fence
        return;
    }
    if (frame.stream >= 2 || frame.slot >= 3) {
        // Invalid stream or slot
        return;
    }

    bool validConsumer = false;
    uint32_t consumerIdx = 0;
    for (const auto& c : m_impl->config.consumers) {
        if (c.key == key && c.stream == frame.stream) {
            validConsumer = true;
            consumerIdx = c.id;
            break;
        }
    }
    if (!validConsumer) {
        // Unknown consumer: reject and close fence
        return;
    }

    if (sampled == SampleState::Sampled && fence.get() < 0) {
        // Sampled must carry valid native fence! Never convert to unsampled!
        return;
    }

    std::lock_guard<std::mutex> lock(m_impl->queueMutex);
    if (m_impl->commandQueue.size() >= 64) {
        m_impl->queueOverflow = true;
        m_impl->wake();
        return;
    }

    m_impl->commandQueue.push_back(ReleaseCmd{frame, key, consumerIdx, sampled, std::move(fence)});
    m_impl->wake();
}

void WorkerSession::requestStop() {
    if (m_impl) m_impl->requestStop();
}

void WorkerSession::updateVisibility(uint32_t enabledStreamsMask, bool freeze) {
    if (!m_impl || m_impl->stopped.load()) return;
    std::lock_guard<std::mutex> lock(m_impl->queueMutex);
    if (m_impl->commandQueue.size() >= 64) {
        m_impl->queueOverflow = true;
        m_impl->wake();
        return;
    }

    // Coalesce visibility update if one is already queued
    for (auto& cmd : m_impl->commandQueue) {
        if (std::holds_alternative<VisibilityCmd>(cmd)) {
            std::get<VisibilityCmd>(cmd) = VisibilityCmd{enabledStreamsMask, freeze};
            m_impl->wake();
            return;
        }
    }

    m_impl->commandQueue.push_back(VisibilityCmd{enabledStreamsMask, freeze});
    m_impl->wake();
}

void WorkerSession::setFrameCallback(FrameCallback cb) {
    if (m_impl) m_impl->frameCallback = std::move(cb);
}

void WorkerSession::setStateCallback(StateCallback cb) {
    if (m_impl) m_impl->stateCallback = std::move(cb);
}

bool WorkerSession::getBuffer(uint32_t stream, uint32_t slot, lockframe::Buffer& outDesc, int& outFd) const {
    if (!m_impl) return false;
    std::lock_guard<std::mutex> lock(m_impl->bufferMutex);
    auto it = m_impl->buffers.find({stream, slot});
    if (it != m_impl->buffers.end() && it->second.fd >= 0) {
        outDesc = it->second.desc;
        outFd = dup(it->second.fd);
        return true;
    }
    outFd = -1;
    return false;
}

} // namespace locklive

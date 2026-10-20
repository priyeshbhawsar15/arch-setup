#include "SessionHarness.h"
#include <QCoreApplication>
#include <unistd.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/mman.h>
#include <sys/eventfd.h>

namespace locklive {

SessionConfig fullTopology() {
    SessionConfig cfg;
    cfg.revision = 1;
    cfg.sourceId = "test-wallpaper-id";
    cfg.sourcePath = "/usr/share/omarchy/test-wallpaper";
    cfg.fps = 30;

    StreamConfig s0{0, 3840, 2160, 1}; // mask 1
    StreamConfig s1{1, 3840, 2160, 3}; // mask 3
    cfg.streams = {s0, s1};

    ConsumerConfig c0{"main", 0, 0};
    ConsumerConfig c1{"side-left", 1, 0};
    ConsumerConfig c2{"side-right", 1, 1};
    cfg.consumers = {c0, c1, c2};

    return cfg;
}

DeviceReport measuredDevice() {
    DeviceReport d;
    d.renderNode = "/dev/dri/renderD128";
    d.major = 226;
    d.minor = 128;
    d.contextSerial = 1001;
    d.openGlEgl = true;
    return d;
}

SessionHarness::SessionHarness(MockBehavior behavior, SessionTimeouts timeouts)
    : m_mockBehavior(behavior) {
    m_coordinator.setTimeouts(timeouts);
    m_coordinator.setLauncher([this](const LaunchOptions& options) -> pid_t {
        std::lock_guard<std::mutex> lock(m_mockMutex);
        int sockFd = options.socketFd;
        EpochId currentEpoch = m_coordinator.activeEpochId();
        MockBehavior b = m_mockBehavior;
        m_mockThreads.emplace_back([this, sockFd, b, currentEpoch]() {
            runMockWorker(sockFd, b, currentEpoch);
        });
        return 99999;
    });
    m_lastHeartbeat = std::chrono::steady_clock::now();
}

SessionHarness::~SessionHarness() {
    m_stopMocks = true;
    for (auto& t : m_mockThreads) {
        if (t.joinable()) {
            t.join();
        }
    }
}

void SessionHarness::stage(SessionConfig config) {
    m_coordinator.stageDesired(std::move(config));
}

RegistrationToken SessionHarness::attach(ConsumerKey key, DeviceReport device) {
    auto token = m_coordinator.registerConsumer(key, device);
    m_tokens[key] = token;
    m_coordinator.setVisible(token, true);
    return token;
}

void SessionHarness::advance(int steps) {
    for (int i = 0; i < steps; ++i) {
        auto now = std::chrono::steady_clock::now();
        double gap = std::chrono::duration<double, std::milli>(now - m_lastHeartbeat).count();
        m_lastHeartbeat = now;
        if (gap > m_maxHeartbeatGapMs) {
            m_maxHeartbeatGapMs = gap;
        }

        m_coordinator.evaluateCohort();
        QCoreApplication::processEvents();
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
}

uint32_t SessionHarness::spawnCount() const {
    return m_coordinator.spawnCount();
}

lockframe::Configure SessionHarness::wireConfig() const {
    std::lock_guard<std::mutex> lock(m_mockMutex);
    return m_wireConfig;
}

EpochId SessionHarness::epochId() const {
    return m_coordinator.activeEpochId();
}

void SessionHarness::retry() {
    m_coordinator.retry();
}

void SessionHarness::hide(ConsumerKey key) {
    auto it = m_tokens.find(key);
    if (it != m_tokens.end()) {
        m_coordinator.setVisible(it->second, false);
    }
}

void SessionHarness::show(ConsumerKey key) {
    auto it = m_tokens.find(key);
    if (it != m_tokens.end()) {
        m_coordinator.setVisible(it->second, true);
    }
}

void SessionHarness::detach(ConsumerKey key) {
    auto it = m_tokens.find(key);
    if (it != m_tokens.end()) {
        m_coordinator.detachConsumer(it->second);
        m_tokens.erase(it);
    }
}

double SessionHarness::guiHeartbeatMaxGapMs() const {
    return m_maxHeartbeatGapMs;
}

size_t SessionHarness::pendingObligations() const {
    auto session = m_coordinator.activeSession();
    return session ? session->pendingObligations() : 0;
}

std::vector<lockframe::Release> SessionHarness::capturedReleases() const {
    std::lock_guard<std::mutex> lock(m_mockMutex);
    return m_capturedReleases;
}

void SessionHarness::clearCapturedReleases() {
    std::lock_guard<std::mutex> lock(m_mockMutex);
    m_capturedReleases.clear();
}

void SessionHarness::runMockWorker(int socketFd, MockBehavior behavior, EpochId epoch) {
    if (socketFd < 0) return;

    if (behavior == MockBehavior::StalledHandshake) {
        while (!m_stopMocks) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        close(socketFd);
        return;
    }

    if (behavior == MockBehavior::MalformedPacket) {
        // Send invalid data
        uint8_t garbage[64] = {0xFF};
        (void)write(socketFd, garbage, sizeof(garbage));
        close(socketFd);
        return;
    }

    try {
        // Send Hello
        lockframe::Hello h{226, 128, 0x34325241, 0, 0};
        lockframe::sendPacket(socketFd, lockframe::packet(lockframe::Type::Hello, h, epoch));

        if (behavior == MockBehavior::StalledBuffers) {
            auto cfgPkt = lockframe::receivePacket(socketFd);
            {
                std::lock_guard<std::mutex> lock(m_mockMutex);
                m_wireConfig = cfgPkt.as<lockframe::Configure>();
                m_hasWireConfig = true;
            }
            while (!m_stopMocks) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
            close(socketFd);
            return;
        }

        auto cfgPkt = lockframe::receivePacket(socketFd);
        lockframe::Configure cfg = cfgPkt.as<lockframe::Configure>();
        {
            std::lock_guard<std::mutex> lock(m_mockMutex);
            m_wireConfig = cfg;
            m_hasWireConfig = true;
        }

        if (behavior == MockBehavior::CrashAfterConfigure) {
            close(socketFd);
            return;
        }

        // Send Buffers (3 per stream)
        for (uint32_t s = 0; s < cfg.count; ++s) {
            for (uint32_t slot = 0; slot < 3; ++slot) {
                int mfd = memfd_create("mock_buf", MFD_CLOEXEC);
                if (mfd >= 0) {
                    (void)ftruncate(mfd, 4096);
                }
                lockframe::Buffer b{};
                b.stream = cfg.streams[s].id;
                b.slot = slot;
                b.width = cfg.streams[s].width;
                b.height = cfg.streams[s].height;
                b.fourcc = 0x34325241;
                b.pitch = cfg.streams[s].width * 4;
                auto bpkt = lockframe::packet(lockframe::Type::Buffer, b, epoch);
                bpkt.fds.push_back(lockframe::Fd(mfd));
                lockframe::sendPacket(socketFd, bpkt);
            }
        }

        if (behavior == MockBehavior::StalledReadyFence) {
            int eventFd = eventfd(0, EFD_CLOEXEC); // unsignaled
            lockframe::Frame f{cfg.streams[0].id, 0, 1};
            auto fpkt = lockframe::packet(lockframe::Type::Frame, f, epoch, 1);
            fpkt.fds.push_back(lockframe::Fd(eventFd));
            lockframe::sendPacket(socketFd, fpkt);
            while (!m_stopMocks) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
            close(socketFd);
            return;
        }

        // Normal Frame
        int readyFence = eventfd(1, EFD_CLOEXEC); // signaled
        lockframe::Frame f{cfg.streams[0].id, 0, 1};
        auto fpkt = lockframe::packet(lockframe::Type::Frame, f, epoch, 1);
        fpkt.fds.push_back(lockframe::Fd(readyFence));
        lockframe::sendPacket(socketFd, fpkt);

        // Listen for incoming packets (Release, Visibility, Stop)
        while (!m_stopMocks) {
            pollfd pfd{socketFd, POLLIN, 0};
            int pr = poll(&pfd, 1, 50);
            if (pr > 0 && (pfd.revents & POLLIN)) {
                auto pkt = lockframe::receivePacket(socketFd);
                if (pkt.header.type == lockframe::Type::Release) {
                    auto rel = pkt.as<lockframe::Release>();
                    std::lock_guard<std::mutex> lock(m_mockMutex);
                    m_capturedReleases.push_back(rel);
                } else if (pkt.header.type == lockframe::Type::Stop) {
                    break;
                }
            } else if (pr > 0 && (pfd.revents & (POLLERR | POLLHUP))) {
                break;
            }
        }
    } catch (...) {}

    close(socketFd);
}

} // namespace locklive

#include "SessionCoordinator.h"
#include <QCoreApplication>
#include <algorithm>
#include <sys/socket.h>
#include <unistd.h>
#include <iostream>

namespace locklive {

static EpochId allocateEpochId() {
    static std::atomic<EpochId> s_nextEpochId{1};
    EpochId id = s_nextEpochId.fetch_add(1, std::memory_order_relaxed);
    if (id == 0) {
        throw std::overflow_error("EpochId space exhausted");
    }
    return id;
}

SessionCoordinator::SessionCoordinator(QObject* parent)
    : QObject(parent) {}

SessionCoordinator::SessionCoordinator(LauncherFn launcher, SessionTimeouts timeouts, QObject* parent)
    : QObject(parent), m_launcher(std::move(launcher)), m_timeouts(timeouts) {}

SessionCoordinator::~SessionCoordinator() {
    if (m_activeSession) {
        m_activeSession->requestStop();
    }
    if (m_retiringSession) {
        m_retiringSession->requestStop();
    }
}

void SessionCoordinator::stageDesired(SessionConfig config) {
    // Normalize streams by ID ascending
    std::sort(config.streams.begin(), config.streams.end(),
              [](const StreamConfig& a, const StreamConfig& b) { return a.id < b.id; });

    // Normalize consumers by key ascending
    std::sort(config.consumers.begin(), config.consumers.end(),
              [](const ConsumerConfig& a, const ConsumerConfig& b) { return a.key < b.key; });

    std::string err;
    if (!validateSessionConfig(config, &err)) {
        failWith("Invalid session config: " + err);
        return;
    }

    if (m_hasDesiredConfig && config.revision == m_desiredConfig.revision) {
        if (config == m_desiredConfig) {
            // Idempotent same revision
            return;
        } else {
            // Conflicting same revision
            failWith("Conflicting snapshot with same revision");
            return;
        }
    }

    if (m_activeSession) {
        if (m_activeSession->config().sourcePath != config.sourcePath ||
            m_activeSession->config().streams != config.streams ||
            m_activeSession->config().consumers != config.consumers) {
            m_retiringSession = m_activeSession;
            m_activeSession->requestStop();
            m_activeSession.reset();
        }
    }

    m_desiredConfig = std::move(config);
    m_hasDesiredConfig = true;

    evaluateCohort();
}

RegistrationToken SessionCoordinator::registerConsumer(ConsumerKey key, DeviceReport device) {
    RegistrationToken token = ++m_nextToken;
    m_registrations[token] = ConsumerRegistration{token, std::move(key), std::move(device), false};

    // Staging startup until a queued GUI turn
    QMetaObject::invokeMethod(this, &SessionCoordinator::evaluateCohort, Qt::QueuedConnection);

    return token;
}

void SessionCoordinator::setVisible(RegistrationToken token, bool visible) {
    auto it = m_registrations.find(token);
    if (it == m_registrations.end()) return;
    if (it->second.visible == visible) return;

    it->second.visible = visible;
    updateSessionVisibility();
    evaluateCohort();
}

void SessionCoordinator::detachConsumer(RegistrationToken token) {
    auto it = m_registrations.find(token);
    if (it == m_registrations.end()) return;

    m_registrations.erase(it);

    if (m_activeSession) {
        bool anyConsumerRemaining = false;
        for (const auto& kv : m_registrations) {
            for (const auto& c : m_desiredConfig.consumers) {
                if (kv.second.key == c.key) {
                    anyConsumerRemaining = true;
                    break;
                }
            }
            if (anyConsumerRemaining) break;
        }

        if (!anyConsumerRemaining) {
            m_retiringSession = m_activeSession;
            m_activeSession->requestStop();
            m_activeSession.reset();
        } else {
            updateSessionVisibility();
        }
    }

    evaluateCohort();
}

void SessionCoordinator::retry() {
    if (!m_hasDesiredConfig) return;
    if (m_retriedSources.count(m_desiredConfig.sourcePath) > 0) {
        // At most once per source per lock session
        return;
    }
    m_retriedSources.insert(m_desiredConfig.sourcePath);

    if (m_activeSession) {
        m_retiringSession = m_activeSession;
        m_activeSession->requestStop();
        m_activeSession.reset();
    }

    evaluateCohort();
}

EpochId SessionCoordinator::activeEpochId() const {
    return m_currentEpochId;
}

void SessionCoordinator::evaluateCohort() {
    if (!m_hasDesiredConfig) return;
    if (m_state == SessionState::Error) return;

    // Check completeness of cohort
    std::vector<const ConsumerRegistration*> cohort;
    for (const auto& expected : m_desiredConfig.consumers) {
        const ConsumerRegistration* found = nullptr;
        for (const auto& kv : m_registrations) {
            if (kv.second.key == expected.key) {
                found = &kv.second;
                break;
            }
        }
        if (!found) {
            // Cohort incomplete
            return;
        }
        cohort.push_back(found);
    }

    // Check device compatibility across all registered consumers in cohort
    const auto& firstDev = cohort[0]->device;
    for (const auto* reg : cohort) {
        if (!reg->device.openGlEgl) {
            failWith("Consumer device does not support OpenGL/EGL");
            return;
        }
        if (reg->device.renderNode.empty() ||
            reg->device.renderNode != firstDev.renderNode ||
            reg->device.major != firstDev.major ||
            reg->device.minor != firstDev.minor) {
            failWith("Device mismatch among consumers in cohort");
            return;
        }
    }

    // Check visibility: at least one consumer must be visible
    bool anyVisible = false;
    for (const auto* reg : cohort) {
        if (reg->visible) {
            anyVisible = true;
            break;
        }
    }
    if (!anyVisible) {
        // All-hidden initial state remains pending without a producer
        return;
    }

    if (m_activeSession) {
        // Active producer already running
        return;
    }

    // Cohort complete and validated -> Launch producer!
    m_currentEpochId = allocateEpochId();
    m_spawnCount++;

    int sockets[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sockets) != 0) {
        failWith("socketpair failed");
        return;
    }

    LaunchOptions opts;
    opts.socketFd = sockets[1];
    opts.renderNode = firstDev.renderNode;
    opts.sourcePath = m_desiredConfig.sourcePath;
    opts.fps = m_desiredConfig.fps;

    pid_t pid = -1;
    if (m_launcher) {
        pid = m_launcher(opts);
    } else {
        pid = SandboxLauncher::launch(opts);
    }
    close(sockets[1]); // Close child end in parent

    m_activeSession = std::make_shared<WorkerSession>(m_currentEpochId, m_desiredConfig, m_timeouts);
    m_activeSession->setFrameCallback([this](FrameRef frame, int dmaBufFd, lockframe::Buffer desc) {
        emit frameReady(frame, dmaBufFd, desc);
    });
    m_activeSession->setStateCallback([this](SessionState state, const std::string& err) {
        m_state = state;
        emit sessionStateChanged(state);
        if (state == SessionState::Error) {
            emit errorOccurred(QString::fromStdString(err));
        }
    });

    m_activeSession->start(sockets[0], pid);
    m_state = SessionState::Starting;
    emit epochStarted(m_currentEpochId);
    emit sessionStateChanged(m_state);

    updateSessionVisibility();
}

void SessionCoordinator::failWith(const std::string& errorMsg) {
    m_state = SessionState::Error;
    emit errorOccurred(QString::fromStdString(errorMsg));
}

void SessionCoordinator::updateSessionVisibility() {
    if (!m_activeSession || !m_hasDesiredConfig) return;

    uint32_t enabledMask = 0;
    for (const auto& stream : m_desiredConfig.streams) {
        bool streamVisible = false;
        for (const auto& kv : m_registrations) {
            if (kv.second.visible) {
                for (const auto& c : m_desiredConfig.consumers) {
                    if (c.key == kv.second.key && c.stream == stream.id) {
                        streamVisible = true;
                        break;
                    }
                }
            }
            if (streamVisible) break;
        }
        if (streamVisible) {
            enabledMask |= (1u << stream.id);
        }
    }

    bool freeze = (enabledMask == 0);
    m_activeSession->updateVisibility(enabledMask, freeze);
}

} // namespace locklive

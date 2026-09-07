import SwiftUI
import ButtonKit

/// What the button is doing, and the five ways to talk to it.
struct NowView: View {
    @Environment(HostStore.self) private var store

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    LightView(look: store.status?.currentLook)
                        .padding(.top, 12)
                    headline
                    notices
                    gestures
                }
                .padding(.horizontal)
                .padding(.bottom, 32)
            }
            .navigationTitle(store.status?.deviceName ?? "The button")
            .refreshable { await store.refreshStatus() }
            .sensoryFeedback(.impact, trigger: store.fireCount)
        }
    }

    private var headline: some View {
        VStack(spacing: 6) {
            Text(store.status?.ledState ?? "—")
                .font(.title3.weight(.semibold))
            if let status = store.status, let mode = status.lastMode,
               let trigger = status.lastTrigger {
                Text("Last: \(Gesture.label(trigger)) reached \(mode)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            if let message = store.status?.lastMessage {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .multilineTextAlignment(.center)
    }

    /// Everything that would otherwise make the app look broken when it is
    /// working exactly as designed.
    @ViewBuilder private var notices: some View {
        if let error = store.lastError {
            NoticeBanner(text: error, tone: .red, systemImage: "wifi.exclamationmark")
        } else if store.status == nil {
            ProgressView("Reaching \(store.address)")
                .font(.footnote)
        }
        if let status = store.status {
            if status.mock {
                NoticeBanner(text: "No hardware attached - the service is running a "
                       + "virtual button.", tone: .orange, systemImage: "cube.transparent")
            } else if !status.deviceConnected {
                NoticeBanner(text: "The service is running, but the button is out of "
                       + "range or unplugged.", tone: .orange, systemImage: "antenna.radiowaves.left.and.right.slash")
            }
            if status.storeDegraded {
                NoticeBanner(text: "History is in memory only - the log empties on the "
                       + "next restart.", tone: .orange, systemImage: "externaldrive.badge.exclamationmark")
            }
            if status.clockOverride {
                NoticeBanner(text: "The service is running on a test clock.",
                       tone: .orange, systemImage: "clock.badge.exclamationmark")
            }
        }
    }

    @ViewBuilder private var gestures: some View {
        if let status = store.status, !status.gestures.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("Press")
                    .font(.headline)
                ForEach(status.gestures, id: \.self) { gesture in
                    GestureButton(gesture: gesture,
                                  reaches: status.activeModes[gesture],
                                  busy: store.firing == gesture) {
                        Task { await store.fire(gesture) }
                    }
                }
                Text("Fired through the service, which resolves it exactly as a "
                     + "real press - so this does what the button would do.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct GestureButton: View {
    let gesture: String
    let reaches: String?
    let busy: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(Gesture.label(gesture))
                        .font(.body.weight(.medium))
                    Text(reaches ?? "nothing is bound to this right now")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if busy { ProgressView() }
            }
            .contentShape(Rectangle())
            .padding(.vertical, 10)
            .padding(.horizontal, 14)
        }
        .buttonStyle(.bordered)
        .frame(maxWidth: .infinity)
    }
}

struct NoticeBanner: View {
    let text: String
    let tone: Color
    let systemImage: String

    var body: some View {
        Label(text, systemImage: systemImage)
            .font(.footnote)
            .foregroundStyle(tone)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(tone.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
    }
}

#Preview {
    NowView().environment(HostStore(client: PreviewHost()))
}

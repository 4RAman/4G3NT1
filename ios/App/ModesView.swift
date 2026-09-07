import SwiftUI
import ButtonKit

/// The modes the config holds, and which of them a press would reach now.
///
/// "Modes" rather than "Menus and apps" on purpose: telling one from the other
/// means knowing which templates are takeovers, and that set lives in Python
/// and in schema.js already. A third copy on the phone would be a mirrored
/// table with nothing testing it - so the phone shows what the host said the
/// template is and stays out of the argument. "Mode" is the umbrella noun in
/// generic chrome anyway (CLAUDE.md).
struct ModesView: View {
    @Environment(HostStore.self) private var store

    private var activeNow: Set<String> {
        Set((store.status?.activeModes ?? [:]).values)
    }

    var body: some View {
        NavigationStack {
            List {
                if let warnings = store.config?.warnings, !warnings.isEmpty {
                    Section("What the parser complained about") {
                        ForEach(warnings, id: \.self) { warning in
                            Text(warning)
                                .font(.footnote)
                                .foregroundStyle(.orange)
                        }
                    }
                }
                Section {
                    ForEach(store.config?.modes ?? []) { mode in
                        row(mode)
                    }
                } header: {
                    Text(store.config?.modes.isEmpty ?? true
                         ? "" : "\(store.config?.modes.count ?? 0) modes")
                } footer: {
                    footer
                }
            }
            .navigationTitle("Modes")
            .task { await store.loadConfig() }
            .refreshable { await store.loadConfig() }
            .overlay {
                if store.config == nil && store.lastError == nil {
                    ProgressView()
                }
            }
        }
    }

    private func row(_ mode: ModeSummary) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(mode.name).font(.body.weight(.medium))
                if activeNow.contains(mode.name) {
                    Text("active now")
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.green.opacity(0.18), in: Capsule())
                        .foregroundStyle(.green)
                }
            }
            Text("\(mode.template) · \(mode.activationSummary)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder private var footer: some View {
        if let config = store.config {
            VStack(alignment: .leading, spacing: 4) {
                if let scene = config.scene {
                    Text("Scene: \(scene)")
                }
                Text("Editing is the web UI's job for now - open "
                     + "http://\(store.address) in a browser.")
            }
            .font(.caption)
        }
    }
}

#Preview {
    ModesView().environment(HostStore(client: PreviewHost()))
}
